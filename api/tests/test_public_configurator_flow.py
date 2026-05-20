import os
from datetime import datetime, timedelta
from decimal import Decimal
from unittest.mock import patch

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

from app.auth import get_current_user, require_configurator_access
from app.database import get_session
from app.models import (
    CompanySettings,
    ConfiguratorInvite,
    ConfiguratorInviteStatus,
    Customer,
    Lead,
    Product,
    ProductCategory,
    Quote,
    QuoteConfiguration,
    QuoteItem,
    User,
    UserRole,
)
from app.routers import configurator_invites, public_configurator, quotes


def _make_app(engine, user: User) -> FastAPI:
    def get_session_override():
        with Session(engine) as session:
            yield session

    app = FastAPI()
    app.include_router(public_configurator.router)
    app.include_router(configurator_invites.router)
    app.include_router(quotes.router)
    app.dependency_overrides[get_session] = get_session_override
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[require_configurator_access] = lambda: user
    return app


def _seed_user(engine) -> User:
    with Session(engine) as session:
        user = User(
            email="public-config@example.com",
            hashed_password="dummy",
            full_name="Staff User",
            role=UserRole.DIRECTOR,
        )
        session.add(user)
        session.add(
            CompanySettings(
                company_name="Test Co",
                postcode="SW1A 1AA",
                updated_by_id=1,
            )
        )
        session.commit()
        session.refresh(user)
        return user


def _seed_starter_product(engine, user: User) -> int:
    with Session(engine) as session:
        item = Product(
            name="3m Starter",
            category=ProductCategory.CONFIGURATOR,
            configurator_is_starter_box=True,
            base_price=Decimal("2500.00"),
            configurator_width=Decimal("3.00"),
            configurator_length=Decimal("3.00"),
        )
        session.add(item)
        session.commit()
        session.refresh(item)
        return item.id


def test_public_configurator_start_and_register():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    user = _seed_user(engine)
    client = TestClient(_make_app(engine, user))

    start = client.post("/api/public/configurator/start", json={"campaign_slug": "configure"})
    assert start.status_code == 200
    token = start.json()["access_token"]
    assert start.json()["configure_url"].endswith(f"/configure/{token}")

    register = client.post(
        f"/api/public/configurator/{token}/register",
        json={
            "name": "Jane Customer",
            "email": "jane@example.com",
            "phone": "07123456789",
            "postcode": "M1 1AA",
        },
    )
    assert register.status_code == 200
    body = register.json()
    assert body["status"] == "ACTIVE"
    assert body["customer_name"] == "Jane Customer"
    assert body["quote_id"] is not None

    with Session(engine) as session:
        invite = session.exec(
            select(ConfiguratorInvite).where(ConfiguratorInvite.access_token == token)
        ).first()
        assert invite is not None
        assert invite.lead_id is not None
        assert invite.customer_id is not None
        quote = session.get(Quote, invite.quote_id)
        assert quote is not None
        assert quote.status.value == "DRAFT"


def test_public_configurator_save_and_submit():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    user = _seed_user(engine)
    item_id = _seed_starter_product(engine, user)
    client = TestClient(_make_app(engine, user))

    start = client.post("/api/public/configurator/start", json={})
    token = start.json()["access_token"]
    client.post(
        f"/api/public/configurator/{token}/register",
        json={"name": "Bob Builder", "email": "bob@example.com", "postcode": "M1 1AA"},
    )

    payload = {
        "schema_version": 1,
        "boxes": [
            {
                "id": "box-1",
                "product_id": item_id,
                "x": "0",
                "y": "0",
                "rotation": 0,
            }
        ],
        "extras": [],
        "delivery_estimate_inclusion": "none",
    }
    save = client.put(f"/api/public/configurator/{token}/configuration", json=payload)
    assert save.status_code == 200

    with patch(
        "app.configurator_service.compute_delivery_install_estimate",
        side_effect=AssertionError("should not estimate for none"),
    ):
        submit = client.post(f"/api/public/configurator/{token}/submit")

    assert submit.status_code == 200
    assert submit.json()["status"] == "SUBMITTED"

    with Session(engine) as session:
        invite = session.exec(
            select(ConfiguratorInvite).where(ConfiguratorInvite.access_token == token)
        ).first()
        assert invite.status == ConfiguratorInviteStatus.SUBMITTED


def test_staff_mint_invite_for_existing_customer_skips_details():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    user = _seed_user(engine)
    client = TestClient(_make_app(engine, user))

    with Session(engine) as session:
        customer = Customer(customer_number="C-CFG-001", name="Existing Customer", email="ex@example.com")
        session.add(customer)
        session.commit()
        session.refresh(customer)
        customer_id = customer.id

    mint = client.post(
        "/api/configurator-invites",
        json={"customer_id": customer_id},
    )
    assert mint.status_code == 200
    body = mint.json()
    assert body["status"] == "ACTIVE"
    assert body["quote_id"] is not None
    assert "/configure/" in body["configure_url"]

    context = client.get(f"/api/public/configurator/{body['access_token']}")
    assert context.status_code == 200
    assert context.json()["status"] == "ACTIVE"
    assert context.json()["customer_name"] == "Existing Customer"


def test_expired_invite_returns_410():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    user = _seed_user(engine)
    client = TestClient(_make_app(engine, user))

    with Session(engine) as session:
        invite = ConfiguratorInvite(
            access_token="expired-token-test",
            status=ConfiguratorInviteStatus.PENDING_DETAILS,
            expires_at=datetime.utcnow() - timedelta(days=1),
        )
        session.add(invite)
        session.commit()

    response = client.get("/api/public/configurator/expired-token-test")
    assert response.status_code == 410
