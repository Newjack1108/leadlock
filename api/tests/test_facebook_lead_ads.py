"""Facebook Lead Ads token split and case-insensitive field mapping."""
import os
from unittest.mock import patch

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

from app.messenger_service import (
    fetch_leadgen_lead,
    get_leads_access_token,
    get_page_access_token,
    get_user_profile,
    send_messenger_message,
    _join_leadgen_field_values,
)
from app.routers.webhooks import (
    _leadgen_field_map_to_lead_data,
    _parse_leadgen_events,
    _resolve_leadgen_advert_metadata,
)


CHESHIRE_STABLES_FIELDS = {
    "first_name": "Kelvin",
    "last_name": "Newman",
    "email": "test@example.com",
    "phone_number": "07123456789",
    "post_code": "CW7 3BS",
}

CSGB_GROUP_FIELDS = {
    "Name": "Kelvin Newman",
    "Email": "test@example.com",
    "Phone": "07123456789",
    "Postcode": "CW7 3BS",
}

EXPECTED_CORE_LEAD = {
    "name": "Kelvin Newman",
    "email": "test@example.com",
    "phone": "07123456789",
    "postcode": "CW7 3BS",
}

CUSTOM_FORM_FIELDS = {
    "what_type_of_building_are_you_interested_in?": "American Barn",
    "which_size_do_you_require?": "36ft x 24ft",
    "how_quickly_would_you_like_your_new_building?": "Within 4 weeks",
}

CUSTOM_DESCRIPTION = (
    "what_type_of_building_are_you_interested_in?: American Barn\n"
    "which_size_do_you_require?: 36ft x 24ft\n"
    "how_quickly_would_you_like_your_new_building?: Within 4 weeks"
)


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


def _leadgen_webhook_body(ad_id=None, include_ad_id_key=True):
    value = {
        "leadgen_id": "123",
        "page_id": "456",
        "form_id": "789",
        "created_time": 1710000000,
    }
    if include_ad_id_key:
        value["ad_id"] = ad_id
    return {
        "object": "page",
        "entry": [{"changes": [{"field": "leadgen", "value": value}]}],
    }


def test_parse_leadgen_events_captures_webhook_ad_id():
    events = _parse_leadgen_events(_leadgen_webhook_body(ad_id="120330000000"))
    assert len(events) == 1
    assert events[0]["leadgen_id"] == "123"
    assert events[0]["page_id"] == "456"
    assert events[0]["form_id"] == "789"
    assert events[0]["ad_id"] == "120330000000"


def test_parse_leadgen_events_ad_id_is_optional_and_coerced():
    missing = _parse_leadgen_events(_leadgen_webhook_body(include_ad_id_key=False))
    assert missing[0]["ad_id"] is None

    blank = _parse_leadgen_events(_leadgen_webhook_body(ad_id="   "))
    assert blank[0]["ad_id"] is None

    numeric = _parse_leadgen_events(_leadgen_webhook_body(ad_id=120330000000))
    assert numeric[0]["ad_id"] == "120330000000"


def test_graph_ad_id_and_ad_name_preferred_over_webhook_ad_id():
    ad_name, ad_id = _resolve_leadgen_advert_metadata(
        graph_ad_name="Stables Carousel - August Offer",
        graph_ad_id="111",
        webhook_ad_id="999",
    )
    data = _leadgen_field_map_to_lead_data(CSGB_GROUP_FIELDS, ad_name=ad_name, ad_id=ad_id)
    for key, value in EXPECTED_CORE_LEAD.items():
        assert data[key] == value
    assert data["description"] == (
        "Facebook Advert: Stables Carousel - August Offer\n"
        "Facebook Ad ID: 111"
    )


def test_webhook_ad_id_fills_facebook_ad_id_when_graph_omits_ad_id():
    ad_name, ad_id = _resolve_leadgen_advert_metadata(
        graph_ad_name=None,
        graph_ad_id=None,
        webhook_ad_id="120330000000",
    )
    data = _leadgen_field_map_to_lead_data(
        {**CSGB_GROUP_FIELDS, **CUSTOM_FORM_FIELDS},
        ad_name=ad_name,
        ad_id=ad_id,
    )
    for key, value in EXPECTED_CORE_LEAD.items():
        assert data[key] == value
    assert data["description"].startswith("Facebook Ad ID: 120330000000\n\n")
    assert "Facebook Advert:" not in data["description"]
    assert CUSTOM_DESCRIPTION in data["description"]


def test_no_advert_lines_when_graph_and_webhook_omit_advert_fields():
    ad_name, ad_id = _resolve_leadgen_advert_metadata(
        graph_ad_name=None,
        graph_ad_id=None,
        webhook_ad_id=None,
    )
    data = _leadgen_field_map_to_lead_data(
        {**CHESHIRE_STABLES_FIELDS, **CUSTOM_FORM_FIELDS},
        ad_name=ad_name,
        ad_id=ad_id,
    )
    for key, value in EXPECTED_CORE_LEAD.items():
        assert data[key] == value
    assert data["description"] == CUSTOM_DESCRIPTION
    assert "Facebook Advert:" not in data["description"]
    assert "Facebook Ad ID:" not in data["description"]


def test_join_leadgen_field_values_keeps_all_parts():
    assert _join_leadgen_field_values(["Field shelter", "12x14"]) == "Field shelter, 12x14"
    assert _join_leadgen_field_values(["field_shelter"]) == "field_shelter"
    assert _join_leadgen_field_values([None, "  ", "12x14"]) == "12x14"
    assert _join_leadgen_field_values([]) == ""


def test_multipart_facebook_answer_is_kept_in_full():
    data = _leadgen_field_map_to_lead_data(
        {
            **CSGB_GROUP_FIELDS,
            "what_type_of_building_are_you_interested_in?": "Field shelter, 12x14",
        }
    )
    for key, value in EXPECTED_CORE_LEAD.items():
        assert data[key] == value
    assert (
        "what_type_of_building_are_you_interested_in?: Field shelter, 12x14"
        in data["description"]
    )


def test_snake_case_option_and_size_question_both_kept():
    data = _leadgen_field_map_to_lead_data(
        {
            **CSGB_GROUP_FIELDS,
            "what_type_of_building_are_you_interested_in?": "field_shelter",
            "which_size_do_you_require?": "12x14",
        }
    )
    assert (
        "what_type_of_building_are_you_interested_in?: Field shelter"
        in data["description"]
    )
    assert "which_size_do_you_require?: 12x14" in data["description"]


def test_fetch_leadgen_lead_joins_all_field_values(monkeypatch):
    monkeypatch.setenv("FACEBOOK_LEADS_ACCESS_TOKEN", "leads-token")

    def handler(method, url, params, json=None):
        return _FakeResponse(
            payload={
                "id": "123",
                "field_data": [
                    {
                        "name": "what_type_of_building_are_you_interested_in?",
                        "values": ["Field shelter", "12x14"],
                    },
                    {"name": "email", "values": ["a@b.c"]},
                ],
            }
        )

    with patch("app.messenger_service.httpx.Client", return_value=_FakeClient(handler)):
        ok, payload, err = fetch_leadgen_lead("123")

    assert ok is True
    assert err is None
    assert payload["field_map"]["what_type_of_building_are_you_interested_in?"] == (
        "Field shelter, 12x14"
    )
    assert payload["field_map"]["email"] == "a@b.c"


def test_cheshire_stables_style_fields_map_to_leadlock():
    data = _leadgen_field_map_to_lead_data(CHESHIRE_STABLES_FIELDS)
    for key, value in EXPECTED_CORE_LEAD.items():
        assert data[key] == value
    assert data["description"] is None


def test_csgb_group_style_fields_are_case_insensitive():
    data = _leadgen_field_map_to_lead_data(CSGB_GROUP_FIELDS)
    for key, value in EXPECTED_CORE_LEAD.items():
        assert data[key] == value
    assert data["description"] is None


def test_padded_and_mixed_case_field_names_are_normalised():
    data = _leadgen_field_map_to_lead_data(
        {
            "  Email  ": "test@example.com",
            "PHONE_NUMBER": "07123456789",
            "Post_Code": "CW7 3BS",
            "FULL_NAME": "Kelvin Newman",
        }
    )
    assert data == {
        **EXPECTED_CORE_LEAD,
        "description": None,
    }


def test_custom_facebook_questions_remain_in_description():
    data = _leadgen_field_map_to_lead_data(
        {
            **CSGB_GROUP_FIELDS,
            "what_type_of_building_are_you_interested_in?": "Stable",
            "how_quick_would_you_like_your_new_building?": "ASAP",
            "which_size_do_you_require?": "12x24",
        }
    )
    for key, value in EXPECTED_CORE_LEAD.items():
        assert data[key] == value
    assert data["description"] is not None
    assert "what_type_of_building_are_you_interested_in?: Stable" in data["description"]
    assert "how_quick_would_you_like_your_new_building?: ASAP" in data["description"]
    assert "which_size_do_you_require?: 12x24" in data["description"]
    assert not data["description"].startswith("Facebook Advert:")
    assert "Facebook Ad ID:" not in data["description"]


def test_description_includes_ad_name_and_ad_id():
    data = _leadgen_field_map_to_lead_data(
        {**CSGB_GROUP_FIELDS, **CUSTOM_FORM_FIELDS},
        ad_name="Stables Carousel - August Offer",
        ad_id="123456789",
    )
    for key, value in EXPECTED_CORE_LEAD.items():
        assert data[key] == value
    assert data["description"] == (
        "Facebook Advert: Stables Carousel - August Offer\n"
        "Facebook Ad ID: 123456789\n"
        "\n"
        f"{CUSTOM_DESCRIPTION}"
    )


def test_description_includes_ad_name_only():
    data = _leadgen_field_map_to_lead_data(
        {**CHESHIRE_STABLES_FIELDS, **CUSTOM_FORM_FIELDS},
        ad_name="Stables Carousel - August Offer",
        ad_id=None,
    )
    for key, value in EXPECTED_CORE_LEAD.items():
        assert data[key] == value
    assert data["description"].startswith("Facebook Advert: Stables Carousel - August Offer\n\n")
    assert "Facebook Ad ID:" not in data["description"]
    assert CUSTOM_DESCRIPTION in data["description"]


def test_description_includes_ad_id_only():
    data = _leadgen_field_map_to_lead_data(
        {**CSGB_GROUP_FIELDS, **CUSTOM_FORM_FIELDS},
        ad_name=None,
        ad_id="123456789",
    )
    for key, value in EXPECTED_CORE_LEAD.items():
        assert data[key] == value
    assert data["description"].startswith("Facebook Ad ID: 123456789\n\n")
    assert "Facebook Advert:" not in data["description"]
    assert CUSTOM_DESCRIPTION in data["description"]


def test_missing_advert_metadata_keeps_custom_questions_only():
    data = _leadgen_field_map_to_lead_data(
        {**CHESHIRE_STABLES_FIELDS, **CUSTOM_FORM_FIELDS},
        ad_name=None,
        ad_id=None,
    )
    for key, value in EXPECTED_CORE_LEAD.items():
        assert data[key] == value
    assert data["description"] == CUSTOM_DESCRIPTION


def test_blank_advert_metadata_does_not_add_empty_lines():
    data = _leadgen_field_map_to_lead_data(
        {**CSGB_GROUP_FIELDS, **CUSTOM_FORM_FIELDS},
        ad_name="   ",
        ad_id="",
    )
    assert data["description"] == CUSTOM_DESCRIPTION


def test_advert_metadata_does_not_mix_into_contact_fields():
    data = _leadgen_field_map_to_lead_data(
        CSGB_GROUP_FIELDS,
        ad_name="Stables Carousel - August Offer",
        ad_id="123456789",
    )
    for key, value in EXPECTED_CORE_LEAD.items():
        assert data[key] == value
    assert data["name"] != "Stables Carousel - August Offer"
    assert data["email"] == "test@example.com"
    assert data["phone"] == "07123456789"
    assert data["postcode"] == "CW7 3BS"
    assert data["description"] == (
        "Facebook Advert: Stables Carousel - August Offer\n"
        "Facebook Ad ID: 123456789"
    )


def test_leads_access_token_is_preferred_over_page_token(monkeypatch):
    monkeypatch.setenv("FACEBOOK_LEADS_ACCESS_TOKEN", "leads-token")
    monkeypatch.setenv("FACEBOOK_PAGE_ACCESS_TOKEN", "messenger-token")
    assert get_leads_access_token() == "leads-token"
    assert get_page_access_token() == "messenger-token"


def test_leads_access_token_falls_back_to_page_token_with_warning(monkeypatch, capsys):
    monkeypatch.delenv("FACEBOOK_LEADS_ACCESS_TOKEN", raising=False)
    monkeypatch.setenv("FACEBOOK_PAGE_ACCESS_TOKEN", "messenger-token")
    assert get_leads_access_token() == "messenger-token"
    captured = capsys.readouterr()
    assert "WARNING: FACEBOOK_LEADS_ACCESS_TOKEN not set" in captured.err
    assert "using legacy FACEBOOK_PAGE_ACCESS_TOKEN for Lead Ads" in captured.err


def test_page_access_token_ignores_leads_token(monkeypatch):
    monkeypatch.setenv("FACEBOOK_LEADS_ACCESS_TOKEN", "leads-token")
    monkeypatch.delenv("FACEBOOK_PAGE_ACCESS_TOKEN", raising=False)
    assert get_page_access_token() is None
    assert get_leads_access_token() == "leads-token"


def test_fetch_leadgen_lead_uses_leads_token_not_page_token(monkeypatch):
    monkeypatch.setenv("FACEBOOK_LEADS_ACCESS_TOKEN", "leads-token")
    monkeypatch.setenv("FACEBOOK_PAGE_ACCESS_TOKEN", "messenger-token")
    captured = {}

    def handler(method, url, params, json=None):
        captured["method"] = method
        captured["url"] = url
        captured["params"] = params
        return _FakeResponse(
            payload={
                "id": "123",
                "field_data": [{"name": "email", "values": ["a@b.c"]}],
            }
        )

    with patch("app.messenger_service.httpx.Client", return_value=_FakeClient(handler)):
        ok, payload, err = fetch_leadgen_lead("123")

    assert ok is True
    assert err is None
    assert payload["field_map"] == {"email": "a@b.c"}
    assert payload["ad_name"] is None
    assert payload["ad_id"] is None
    assert captured["params"]["access_token"] == "leads-token"
    assert captured["params"]["fields"] == "id,created_time,field_data,ad_id,ad_name"


def test_fetch_leadgen_lead_returns_advert_metadata_separately_from_form_fields(monkeypatch):
    monkeypatch.setenv("FACEBOOK_LEADS_ACCESS_TOKEN", "leads-token")

    def handler(method, url, params, json=None):
        return _FakeResponse(
            payload={
                "id": "123",
                "ad_id": 123456789,
                "ad_name": "Stables Carousel - August Offer",
                "field_data": [
                    {"name": "Name", "values": ["Kelvin Newman"]},
                    {"name": "email", "values": ["test@example.com"]},
                ],
            }
        )

    with patch("app.messenger_service.httpx.Client", return_value=_FakeClient(handler)):
        ok, payload, err = fetch_leadgen_lead("123")

    assert ok is True
    assert err is None
    assert payload["field_map"] == {
        "Name": "Kelvin Newman",
        "email": "test@example.com",
    }
    assert "ad_name" not in payload["field_map"]
    assert "ad_id" not in payload["field_map"]
    assert payload["ad_name"] == "Stables Carousel - August Offer"
    assert payload["ad_id"] == "123456789"


def test_fetch_leadgen_lead_retries_without_advert_fields_when_graph_rejects_them(monkeypatch, capsys):
    monkeypatch.setenv("FACEBOOK_LEADS_ACCESS_TOKEN", "leads-token")
    calls = []

    def handler(method, url, params, json=None):
        fields = params.get("fields")
        calls.append(fields)
        if "ad_id" in fields or "ad_name" in fields:
            return _FakeResponse(
                status_code=400,
                payload={"error": {"message": "Tried accessing nonexisting field (ad_name)"}},
            )
        return _FakeResponse(
            payload={
                "id": "123",
                "field_data": [
                    {"name": "Name", "values": ["Kelvin Newman"]},
                    {"name": "email", "values": ["test@example.com"]},
                ],
            }
        )

    with patch("app.messenger_service.httpx.Client", return_value=_FakeClient(handler)):
        ok, payload, err = fetch_leadgen_lead("123")

    assert ok is True
    assert err is None
    assert calls == [
        "id,created_time,field_data,ad_id,ad_name",
        "id,created_time,field_data",
    ]
    assert payload["field_map"] == {
        "Name": "Kelvin Newman",
        "email": "test@example.com",
    }
    assert payload["ad_name"] is None
    assert payload["ad_id"] is None
    logged = capsys.readouterr().err
    assert "retrying without ad_id/ad_name" in logged
    assert "Tried accessing nonexisting field (ad_name)" in logged
    assert "leads-token" not in logged


def test_messenger_send_uses_page_token_not_leads_token(monkeypatch):
    monkeypatch.setenv("FACEBOOK_LEADS_ACCESS_TOKEN", "leads-token")
    monkeypatch.setenv("FACEBOOK_PAGE_ACCESS_TOKEN", "messenger-token")
    captured = {}

    def handler(method, url, params, json=None):
        captured["method"] = method
        captured["params"] = params
        return _FakeResponse(payload={"message_id": "mid.1"})

    with patch("app.messenger_service.httpx.Client", return_value=_FakeClient(handler)):
        ok, mid, err = send_messenger_message("psid-1", "hello")

    assert ok is True
    assert mid == "mid.1"
    assert err is None
    assert captured["method"] == "POST"
    assert captured["params"]["access_token"] == "messenger-token"


def test_messenger_profile_uses_page_token_not_leads_token(monkeypatch):
    monkeypatch.setenv("FACEBOOK_LEADS_ACCESS_TOKEN", "leads-token")
    monkeypatch.setenv("FACEBOOK_PAGE_ACCESS_TOKEN", "messenger-token")
    captured = {}

    def handler(method, url, params, json=None):
        captured["params"] = params
        return _FakeResponse(payload={"first_name": "Kelvin", "last_name": "Newman"})

    with patch("app.messenger_service.httpx.Client", return_value=_FakeClient(handler)):
        ok, first, last, phone, err = get_user_profile("psid-1")

    assert ok is True
    assert first == "Kelvin"
    assert last == "Newman"
    assert phone is None
    assert err is None
    assert captured["params"]["access_token"] == "messenger-token"


def test_failed_lead_fetch_log_includes_ids_not_token(capsys):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from sqlalchemy.pool import StaticPool
    from sqlmodel import Session, SQLModel, create_engine

    from app.database import get_session
    from app.routers import webhooks as webhooks_router

    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)

    def _override_session():
        with Session(engine) as session:
            yield session

    app = FastAPI()
    app.include_router(webhooks_router.router)
    app.dependency_overrides[get_session] = _override_session

    payload = {
        "object": "page",
        "entry": [
            {
                "changes": [
                    {
                        "field": "leadgen",
                        "value": {
                            "leadgen_id": "123",
                            "page_id": "456",
                            "form_id": "789",
                            "ad_id": "120330000000",
                        },
                    }
                ]
            }
        ],
    }

    with patch(
        "app.routers.webhooks.get_leads_access_token",
        return_value="leads-token",
    ), patch(
        "app.routers.webhooks.fetch_leadgen_lead",
        return_value=(False, None, "Invalid OAuth access token"),
    ):
        client = TestClient(app)
        response = client.post("/api/webhooks/facebook/leadgen", json=payload)

    assert response.status_code == 200
    err = capsys.readouterr().err
    assert "leadgen_id=123" in err
    assert "page_id=456" in err
    assert "form_id=789" in err
    assert "error=Invalid OAuth access token" in err
    assert "leads-token" not in err
    assert "webhook_ad_id=" not in err
    assert "graph_ad_id=" not in err


def test_lead_is_created_when_advert_metadata_is_absent(capsys):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from sqlalchemy.pool import StaticPool
    from sqlmodel import Session, SQLModel, create_engine, select

    from app.database import get_session
    from app.models import Lead, LeadSource, LeadType
    from app.routers import webhooks as webhooks_router

    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)

    def _override_session():
        with Session(engine) as session:
            yield session

    app = FastAPI()
    app.include_router(webhooks_router.router)
    app.dependency_overrides[get_session] = _override_session

    payload = {
        "object": "page",
        "entry": [
            {
                "changes": [
                    {
                        "field": "leadgen",
                        "value": {
                            "leadgen_id": "123",
                            "page_id": "456",
                            "form_id": "789",
                        },
                    }
                ]
            }
        ],
    }
    fetch_payload = {
        "field_map": {
            **CSGB_GROUP_FIELDS,
            **CUSTOM_FORM_FIELDS,
        },
        "ad_name": None,
        "ad_id": None,
    }

    with patch(
        "app.routers.webhooks.get_leads_access_token",
        return_value="leads-token",
    ), patch(
        "app.routers.webhooks.fetch_leadgen_lead",
        return_value=(True, fetch_payload, None),
    ), patch(
        "app.customer_outreach_service.try_customer_outreach_for_new_lead",
        return_value=None,
    ):
        client = TestClient(app)
        response = client.post("/api/webhooks/facebook/leadgen", json=payload)

    assert response.status_code == 200
    with Session(engine) as session:
        lead = session.exec(select(Lead)).first()
    assert lead is not None
    assert lead.lead_source == LeadSource.FACEBOOK
    assert lead.lead_type == LeadType.STABLES
    assert lead.name == "Kelvin Newman"
    assert lead.email == "test@example.com"
    assert lead.phone == "07123456789"
    assert lead.postcode == "CW7 3BS"
    assert lead.description == CUSTOM_DESCRIPTION
    err = capsys.readouterr().err
    assert "leadgen_id=123" in err
    assert "ad_id=- ad_name=- graph_ad_id=- webhook_ad_id=- field_count=" in err
    assert "leads-token" not in err


def _post_leadgen_webhook(webhook_body, fetch_payload):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from sqlalchemy.pool import StaticPool
    from sqlmodel import Session, SQLModel, create_engine, select

    from app.database import get_session
    from app.models import Lead
    from app.routers import webhooks as webhooks_router

    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)

    def _override_session():
        with Session(engine) as session:
            yield session

    app = FastAPI()
    app.include_router(webhooks_router.router)
    app.dependency_overrides[get_session] = _override_session

    with patch(
        "app.routers.webhooks.get_leads_access_token",
        return_value="leads-token",
    ), patch(
        "app.routers.webhooks.fetch_leadgen_lead",
        return_value=(True, fetch_payload, None),
    ), patch(
        "app.customer_outreach_service.try_customer_outreach_for_new_lead",
        return_value=None,
    ):
        client = TestClient(app)
        response = client.post("/api/webhooks/facebook/leadgen", json=webhook_body)

    with Session(engine) as session:
        lead = session.exec(select(Lead)).first()
    return response, lead


def test_created_lead_prefers_graph_ad_id_and_ad_name_over_webhook(capsys):
    from app.models import LeadSource, LeadType

    fetch_payload = {
        "field_map": {**CSGB_GROUP_FIELDS, **CUSTOM_FORM_FIELDS},
        "ad_name": "Stables Carousel - August Offer",
        "ad_id": "111",
    }
    response, lead = _post_leadgen_webhook(
        _leadgen_webhook_body(ad_id="999"),
        fetch_payload,
    )
    assert response.status_code == 200
    assert lead is not None
    assert lead.lead_source == LeadSource.FACEBOOK
    assert lead.lead_type == LeadType.STABLES
    assert lead.description == (
        "Facebook Advert: Stables Carousel - August Offer\n"
        "Facebook Ad ID: 111\n"
        "\n"
        f"{CUSTOM_DESCRIPTION}"
    )
    err = capsys.readouterr().err
    assert "ad_id=111 ad_name=Stables Carousel - August Offer graph_ad_id=111 webhook_ad_id=999" in err
    assert "leads-token" not in err


def test_created_lead_uses_webhook_ad_id_when_graph_omits_ad_id(capsys):
    from app.models import LeadSource, LeadType

    fetch_payload = {
        "field_map": {**CSGB_GROUP_FIELDS, **CUSTOM_FORM_FIELDS},
        "ad_name": None,
        "ad_id": None,
    }
    response, lead = _post_leadgen_webhook(
        _leadgen_webhook_body(ad_id="120330000000"),
        fetch_payload,
    )
    assert response.status_code == 200
    assert lead is not None
    assert lead.lead_source == LeadSource.FACEBOOK
    assert lead.lead_type == LeadType.STABLES
    assert lead.description.startswith("Facebook Ad ID: 120330000000\n\n")
    assert "Facebook Advert:" not in lead.description
    assert CUSTOM_DESCRIPTION in lead.description
    err = capsys.readouterr().err
    assert "ad_id=120330000000 ad_name=- graph_ad_id=- webhook_ad_id=120330000000" in err
    assert "leads-token" not in err
