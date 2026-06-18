import os

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

from cryptography.fernet import Fernet

_TEST_FERNET_KEY = Fernet.generate_key().decode()
os.environ["BANK_DETAILS_ENCRYPTION_KEY"] = _TEST_FERNET_KEY

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

from app.auth import get_current_user
from app.bank_details_crypto import (
    decrypt_bank_value,
    encrypt_bank_value,
    encrypt_existing_plaintext_values,
    get_decrypted_bank_details,
    is_encrypted,
    mask_account_number,
    mask_sort_code,
    prepare_bank_fields_for_save,
)
from app.database import get_session
from app.models import CompanySettings, User, UserRole
from app.routers import settings as settings_router


def _make_app(engine, user: User):
    def get_session_override():
        with Session(engine) as session:
            yield session

    app = FastAPI()
    app.include_router(settings_router.router)
    app.dependency_overrides[get_session] = get_session_override
    app.dependency_overrides[get_current_user] = lambda: user
    return app


def _seed_users_and_settings(session: Session):
    director = User(
        email="director@example.com",
        hashed_password="x",
        full_name="Director",
        role=UserRole.DIRECTOR,
    )
    closer = User(
        email="closer@example.com",
        hashed_password="x",
        full_name="Closer",
        role=UserRole.CLOSER,
    )
    session.add(director)
    session.add(closer)
    session.commit()
    session.refresh(director)
    session.refresh(closer)

    settings = CompanySettings(
        company_name="Test Co Ltd",
        bank_name="Barclays",
        bank_account_name="Test Co Ltd",
        account_number="12345678",
        sort_code="12-34-56",
        updated_by_id=director.id,
    )
    session.add(settings)
    session.commit()
    session.refresh(director)
    session.refresh(closer)
    session.refresh(settings)
    # Eager-load attributes used outside the session in TestClient overrides
    _ = director.role, director.id
    _ = closer.role, closer.id
    session.expunge(director)
    session.expunge(closer)
    session.expunge(settings)
    return director, closer, settings


def test_encrypt_decrypt_round_trip():
    encrypted = encrypt_bank_value("12345678")
    assert encrypted is not None
    assert is_encrypted(encrypted)
    assert decrypt_bank_value(encrypted) == "12345678"


def test_mask_helpers():
    assert mask_account_number("12345678") == "****5678"
    assert mask_sort_code("12-34-56") == "**-**-56"


def test_encrypt_existing_plaintext_values():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        _, _, settings = _seed_users_and_settings(session)
        settings_id = settings.id
        assert settings.account_number == "12345678"
        updated = encrypt_existing_plaintext_values(session)
        assert updated == 1
        migrated = session.get(CompanySettings, settings_id)
        assert migrated is not None
        assert is_encrypted(migrated.account_number)
        assert is_encrypted(migrated.sort_code)
        assert decrypt_bank_value(migrated.account_number) == "12345678"


def test_prepare_bank_fields_skips_masked_placeholders():
    class Existing:
        account_number = encrypt_bank_value("12345678")
        sort_code = encrypt_bank_value("12-34-56")

    result = prepare_bank_fields_for_save(
        {"account_number": "****5678", "sort_code": "**-**-56", "bank_name": "HSBC"},
        Existing(),
    )
    assert "account_number" not in result
    assert "sort_code" not in result
    assert result["bank_name"] == "HSBC"


def test_get_company_settings_masks_for_director():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        director, _, settings = _seed_users_and_settings(session)
        settings.account_number = encrypt_bank_value("12345678")
        settings.sort_code = encrypt_bank_value("12-34-56")
        session.add(settings)
        session.commit()

    app = _make_app(engine, director)
    client = TestClient(app)
    response = client.get("/api/settings/company")
    assert response.status_code == 200
    data = response.json()
    assert data["account_number"] == "****5678"
    assert data["sort_code"] == "**-**-56"
    assert data["account_number_set"] is True
    assert data["sort_code_set"] is True
    assert data["bank_name"] == "Barclays"


def test_get_company_settings_omits_bank_fields_for_non_director():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        director, closer, _ = _seed_users_and_settings(session)

    app = _make_app(engine, closer)
    client = TestClient(app)
    response = client.get("/api/settings/company")
    assert response.status_code == 200
    data = response.json()
    assert data["account_number"] is None
    assert data["sort_code"] is None
    assert data["bank_name"] is None
    assert data["bank_account_name"] is None
    assert data["account_number_set"] is False
    assert data["sort_code_set"] is False


def test_reveal_bank_details_director_only():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        director, closer, settings = _seed_users_and_settings(session)
        settings.account_number = encrypt_bank_value("12345678")
        settings.sort_code = encrypt_bank_value("12-34-56")
        session.add(settings)
        session.commit()

    director_app = _make_app(engine, director)
    director_client = TestClient(director_app)
    reveal = director_client.get("/api/settings/company/bank-details")
    assert reveal.status_code == 200
    assert reveal.json()["account_number"] == "12345678"
    assert reveal.json()["sort_code"] == "12-34-56"

    closer_app = _make_app(engine, closer)
    closer_client = TestClient(closer_app)
    denied = closer_client.get("/api/settings/company/bank-details")
    assert denied.status_code == 403


def test_put_with_masked_placeholder_preserves_encrypted_value():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        director, _, settings = _seed_users_and_settings(session)
        settings.account_number = encrypt_bank_value("12345678")
        settings.sort_code = encrypt_bank_value("12-34-56")
        session.add(settings)
        session.commit()
        stored_account = settings.account_number

    app = _make_app(engine, director)
    client = TestClient(app)
    response = client.put(
        "/api/settings/company",
        json={"account_number": "****5678", "sort_code": "**-**-56", "bank_name": "NatWest"},
    )
    assert response.status_code == 200
    assert response.json()["bank_name"] == "NatWest"

    with Session(engine) as session:
        settings = session.exec(select(CompanySettings)).first()
        assert settings.account_number == stored_account
        assert decrypt_bank_value(settings.account_number) == "12345678"
        assert settings.bank_name == "NatWest"


def test_get_decrypted_bank_details_for_pdf_and_public():
    settings = CompanySettings(
        company_name="Test Co",
        bank_name="Barclays",
        bank_account_name="Test Co",
        account_number=encrypt_bank_value("87654321"),
        sort_code=encrypt_bank_value("65-43-21"),
        updated_by_id=1,
    )
    bank = get_decrypted_bank_details(settings)
    assert bank["account_number"] == "87654321"
    assert bank["sort_code"] == "65-43-21"
    assert bank["bank_name"] == "Barclays"
