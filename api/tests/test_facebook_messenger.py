"""Facebook Messenger dual-Page token selection and inbound lead creation."""
import json
import os
from unittest.mock import patch

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

from app.messenger_service import (
    get_messenger_page_token,
    get_page_access_token,
    parse_webhook_payload,
    send_messenger_message,
)
from app.models import LeadSource, MessengerDirection


CSGB_PAGE_ID = "485666198220603"
CHESHIRE_PAGE_ID = "1806797756222550"


class _FakeResponse:
    def __init__(self, status_code=200, payload=None, text=""):
        self.status_code = status_code
        self._payload = payload or {}
        self.text = text

    def json(self):
        return self._payload


class _FakeClient:
    def __init__(self, handler):
        self._handler = handler

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def get(self, url, params=None):
        return self._handler("GET", url, params)

    def post(self, url, json=None, params=None):
        return self._handler("POST", url, params, json)


def test_parse_webhook_payload_includes_page_id():
    events = parse_webhook_payload(
        {
            "object": "page",
            "entry": [
                {
                    "id": CSGB_PAGE_ID,
                    "messaging": [
                        {
                            "sender": {"id": "psid-1"},
                            "message": {"mid": "m1", "text": "How much is a stable?"},
                        }
                    ],
                }
            ],
        }
    )
    assert len(events) == 1
    assert events[0]["sender_id"] == "psid-1"
    assert events[0]["text"] == "How much is a stable?"
    assert events[0]["page_id"] == CSGB_PAGE_ID


def test_messenger_page_token_prefers_map_over_default(monkeypatch):
    monkeypatch.setenv("FACEBOOK_PAGE_ACCESS_TOKEN", "default-token")
    monkeypatch.setenv(
        "FACEBOOK_MESSENGER_PAGE_TOKENS",
        json.dumps(
            {
                CSGB_PAGE_ID: "csgb-token",
                CHESHIRE_PAGE_ID: "cheshire-token",
            }
        ),
    )
    assert get_messenger_page_token(CSGB_PAGE_ID) == "csgb-token"
    assert get_messenger_page_token(CHESHIRE_PAGE_ID) == "cheshire-token"
    assert get_messenger_page_token(None) == "default-token"
    assert get_messenger_page_token("unknown-page") == "default-token"
    assert get_page_access_token() == "default-token"


def test_messenger_page_token_falls_back_when_map_missing(monkeypatch):
    monkeypatch.delenv("FACEBOOK_MESSENGER_PAGE_TOKENS", raising=False)
    monkeypatch.setenv("FACEBOOK_PAGE_ACCESS_TOKEN", "default-token")
    assert get_messenger_page_token(CSGB_PAGE_ID) == "default-token"


def test_messenger_page_token_unknown_page_without_default(monkeypatch):
    monkeypatch.setenv(
        "FACEBOOK_MESSENGER_PAGE_TOKENS",
        json.dumps({CSGB_PAGE_ID: "csgb-token"}),
    )
    monkeypatch.delenv("FACEBOOK_PAGE_ACCESS_TOKEN", raising=False)
    assert get_messenger_page_token(CHESHIRE_PAGE_ID) is None
    ok, mid, err = send_messenger_message("psid-1", "hello", page_id=CHESHIRE_PAGE_ID)
    assert ok is False
    assert mid is None
    assert "page_id=" + CHESHIRE_PAGE_ID in (err or "")


def test_send_messenger_uses_token_for_page_id(monkeypatch):
    monkeypatch.setenv("FACEBOOK_PAGE_ACCESS_TOKEN", "default-token")
    monkeypatch.setenv(
        "FACEBOOK_MESSENGER_PAGE_TOKENS",
        json.dumps({CHESHIRE_PAGE_ID: "cheshire-token"}),
    )
    captured = {}

    def handler(method, url, params, json=None):
        captured["params"] = params
        return _FakeResponse(payload={"message_id": "mid.ok"})

    with patch("app.messenger_service.httpx.Client", return_value=_FakeClient(handler)):
        ok, mid, err = send_messenger_message(
            "psid-1",
            "We can help",
            page_id=CHESHIRE_PAGE_ID,
        )

    assert ok is True
    assert mid == "mid.ok"
    assert err is None
    assert captured["params"]["access_token"] == "cheshire-token"


def _build_messenger_app(engine):
    from fastapi import FastAPI
    from sqlmodel import Session

    from app.auth import get_current_user
    from app.database import get_session
    from app.models import User, UserRole
    from app.routers import messenger as messenger_router
    from app.routers import webhooks as webhooks_router

    def _override_session():
        with Session(engine) as session:
            yield session

    app = FastAPI()
    app.include_router(webhooks_router.router)
    app.include_router(messenger_router.router)
    app.dependency_overrides[get_session] = _override_session

    with Session(engine) as session:
        user = User(
            email="sales@example.com",
            full_name="Sales User",
            hashed_password="x",
            role=UserRole.DIRECTOR,
            is_active=True,
        )
        session.add(user)
        session.commit()
        session.refresh(user)
        user_id = user.id

    def _override_user():
        with Session(engine) as session:
            return session.get(User, user_id)

    app.dependency_overrides[get_current_user] = _override_user
    return app


def test_inbound_creates_lead_and_reply_uses_matching_page_token(monkeypatch):
    from fastapi.testclient import TestClient
    from sqlalchemy.pool import StaticPool
    from sqlmodel import Session, SQLModel, create_engine, select

    from app.models import Customer, Lead, MessengerMessage

    monkeypatch.setenv("FACEBOOK_PAGE_ACCESS_TOKEN", "default-token")
    monkeypatch.setenv(
        "FACEBOOK_MESSENGER_PAGE_TOKENS",
        json.dumps(
            {
                CSGB_PAGE_ID: "csgb-token",
                CHESHIRE_PAGE_ID: "cheshire-token",
            }
        ),
    )

    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    app = _build_messenger_app(engine)
    client = TestClient(app)

    with patch(
        "app.routers.webhooks.get_user_profile",
        return_value=(True, "Alex", "Buyer", None, None),
    ), patch(
        "app.customer_outreach_service.try_customer_outreach_for_new_lead",
        return_value=None,
    ):
        inbound = client.post(
            "/api/webhooks/facebook/messenger",
            json={
                "object": "page",
                "entry": [
                    {
                        "id": CSGB_PAGE_ID,
                        "messaging": [
                            {
                                "sender": {"id": "psid-csgb-1"},
                                "message": {
                                    "mid": "m-in-1",
                                    "text": "Do you build American barns?",
                                },
                            }
                        ],
                    }
                ],
            },
        )
    assert inbound.status_code == 200

    with Session(engine) as session:
        customer = session.exec(select(Customer)).first()
        lead = session.exec(select(Lead)).first()
        msg = session.exec(select(MessengerMessage)).first()
        assert customer is not None
        assert customer.messenger_psid == "psid-csgb-1"
        assert customer.messenger_page_id == CSGB_PAGE_ID
        assert lead is not None
        assert lead.lead_source == LeadSource.FACEBOOK
        assert lead.description == "Do you build American barns?"
        assert msg is not None
        assert msg.direction == MessengerDirection.RECEIVED
        assert msg.body == "Do you build American barns?"
        assert msg.to_psid == CSGB_PAGE_ID
        customer_id = customer.id

    captured = {}

    def handler(method, url, params, json=None):
        captured["params"] = params
        return _FakeResponse(payload={"message_id": "m-out-1"})

    with patch("app.messenger_service.httpx.Client", return_value=_FakeClient(handler)):
        reply = client.post(
            "/api/messenger",
            json={"customer_id": customer_id, "body": "Yes — happy to help."},
        )
    assert reply.status_code == 200
    assert captured["params"]["access_token"] == "csgb-token"


def test_both_pages_inbound_use_distinct_reply_tokens(monkeypatch):
    from fastapi.testclient import TestClient
    from sqlalchemy.pool import StaticPool
    from sqlmodel import Session, SQLModel, create_engine, select

    from app.models import Customer

    monkeypatch.setenv("FACEBOOK_PAGE_ACCESS_TOKEN", "default-token")
    monkeypatch.setenv(
        "FACEBOOK_MESSENGER_PAGE_TOKENS",
        json.dumps(
            {
                CSGB_PAGE_ID: "csgb-token",
                CHESHIRE_PAGE_ID: "cheshire-token",
            }
        ),
    )

    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    app = _build_messenger_app(engine)
    client = TestClient(app)

    with patch(
        "app.routers.webhooks.get_user_profile",
        return_value=(True, "Sam", "Lead", None, None),
    ), patch(
        "app.customer_outreach_service.try_customer_outreach_for_new_lead",
        return_value=None,
    ):
        for page_id, psid, text in (
            (CSGB_PAGE_ID, "psid-a", "Question for CSGB"),
            (CHESHIRE_PAGE_ID, "psid-b", "Question for Cheshire"),
        ):
            resp = client.post(
                "/api/webhooks/facebook/messenger",
                json={
                    "object": "page",
                    "entry": [
                        {
                            "id": page_id,
                            "messaging": [
                                {
                                    "sender": {"id": psid},
                                    "message": {"mid": f"m-{psid}", "text": text},
                                }
                            ],
                        }
                    ],
                },
            )
            assert resp.status_code == 200

    with Session(engine) as session:
        customers = list(session.exec(select(Customer)).all())
        by_page = {c.messenger_page_id: c for c in customers}
        assert set(by_page) == {CSGB_PAGE_ID, CHESHIRE_PAGE_ID}
        csgb_id = by_page[CSGB_PAGE_ID].id
        cheshire_id = by_page[CHESHIRE_PAGE_ID].id

    tokens_used = []

    def handler(method, url, params, json=None):
        tokens_used.append(params["access_token"])
        return _FakeResponse(payload={"message_id": "mid"})

    with patch("app.messenger_service.httpx.Client", return_value=_FakeClient(handler)):
        r1 = client.post("/api/messenger", json={"customer_id": csgb_id, "body": "CSGB reply"})
        r2 = client.post(
            "/api/messenger",
            json={"customer_id": cheshire_id, "body": "Cheshire reply"},
        )
    assert r1.status_code == 200
    assert r2.status_code == 200
    assert tokens_used == ["csgb-token", "cheshire-token"]
