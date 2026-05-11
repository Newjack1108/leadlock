import os
import asyncio
from decimal import Decimal
from io import BytesIO
from types import SimpleNamespace

import pytest
from fastapi import FastAPI, HTTPException, UploadFile
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine
from starlette.datastructures import Headers

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

from app.auth import get_current_user
from app.customer_file_service import MAX_BYTES, upload_customer_file_to_cloudinary
from app.database import get_session
from app.models import Customer, Order, Quote, User, UserRole
from app.routers import customer_files


def _make_upload_file(filename: str, content_type: str, content: bytes) -> UploadFile:
    return UploadFile(
        file=BytesIO(content),
        filename=filename,
        headers=Headers({"content-type": content_type}),
    )


def _mock_cloudinary_upload(monkeypatch):
    calls: list[dict[str, object]] = []

    def fake_upload(content: bytes, **kwargs):
        calls.append({"content": content, "kwargs": kwargs})
        return {
            "secure_url": f"https://cdn.example.com/{kwargs['folder']}/uploaded.pdf",
            "public_id": f"{kwargs['folder']}/uploaded",
            "resource_type": "raw",
            "bytes": len(content),
        }

    monkeypatch.setattr("app.customer_file_service._ensure_configured", lambda: None)
    monkeypatch.setattr("app.customer_file_service.cloudinary.uploader.upload", fake_upload)
    return calls


def _make_app(engine, user):
    def get_session_override():
        with Session(engine) as session:
            yield session

    app = FastAPI()
    app.include_router(customer_files.router)
    app.dependency_overrides[get_session] = get_session_override
    app.dependency_overrides[get_current_user] = lambda: user
    return app


def _seed_upload_context(engine):
    with Session(engine) as session:
        user = User(
            email="files@example.com",
            hashed_password="x",
            full_name="Files User",
            role=UserRole.DIRECTOR,
        )
        customer = Customer(
            customer_number="CUST-PDF-001",
            name="PDF Test Customer",
        )
        session.add(user)
        session.add(customer)
        session.commit()
        session.refresh(user)
        session.refresh(customer)

        quote = Quote(
            customer_id=customer.id,
            quote_number="QT-PDF-001",
            subtotal=Decimal("100.00"),
            discount_total=Decimal("0.00"),
            total_amount=Decimal("100.00"),
            deposit_amount=Decimal("0.00"),
            balance_amount=Decimal("100.00"),
            created_by_id=user.id,
        )
        session.add(quote)
        session.commit()
        session.refresh(quote)

        order = Order(
            quote_id=quote.id,
            customer_id=customer.id,
            order_number="ORD-PDF-001",
            subtotal=Decimal("100.00"),
            discount_total=Decimal("0.00"),
            total_amount=Decimal("100.00"),
            deposit_amount=Decimal("0.00"),
            balance_amount=Decimal("100.00"),
            created_by_id=user.id,
        )
        session.add(order)
        session.commit()
        session.refresh(order)

        return (
            SimpleNamespace(id=user.id, role=user.role, full_name=user.full_name),
            customer.id,
            quote.id,
            order.id,
        )


def test_upload_customer_file_accepts_standard_pdf(monkeypatch):
    calls = _mock_cloudinary_upload(monkeypatch)

    upload = _make_upload_file("plan.pdf", "application/pdf", b"%PDF-1.4 test pdf")
    response = asyncio.run(upload_customer_file_to_cloudinary(upload, 42))

    assert response["content_type"] == "application/pdf"
    assert response["resource_type"] == "raw"
    assert response["secure_url"] == "https://cdn.example.com/customers/42/uploaded.pdf"
    assert calls[0]["content"] == b"%PDF-1.4 test pdf"
    assert calls[0]["kwargs"]["folder"] == "customers/42"


def test_upload_customer_file_accepts_pdf_with_generic_mime(monkeypatch):
    _mock_cloudinary_upload(monkeypatch)

    upload = _make_upload_file("scan.pdf", "application/octet-stream", b"%PDF-1.7 generic mime")
    response = asyncio.run(upload_customer_file_to_cloudinary(upload, 7))

    assert response["content_type"] == "application/pdf"
    assert response["public_id"] == "customers/7/uploaded"


def test_upload_customer_file_rejects_unsupported_type(monkeypatch):
    _mock_cloudinary_upload(monkeypatch)

    upload = _make_upload_file("notes.txt", "text/plain", b"plain text")
    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(upload_customer_file_to_cloudinary(upload, 7))

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == "File must be a PDF, JPG or PNG"


def test_upload_customer_file_rejects_oversize_file(monkeypatch):
    _mock_cloudinary_upload(monkeypatch)

    upload = _make_upload_file("large.pdf", "application/pdf", b"x" * (MAX_BYTES + 1))
    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(upload_customer_file_to_cloudinary(upload, 7))

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == "File size must be 25 MB or less"


def test_upload_customer_file_rejects_empty_file(monkeypatch):
    _mock_cloudinary_upload(monkeypatch)

    upload = _make_upload_file("empty.pdf", "application/pdf", b"")
    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(upload_customer_file_to_cloudinary(upload, 7))

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == "Empty file"


@pytest.mark.parametrize(
    ("route", "list_route", "expected_fields"),
    [
        (
            "customers/{customer_id}/files",
            "customers/{customer_id}/files",
            {"quote_id": None, "order_id": None},
        ),
        (
            "quotes/{quote_id}/files",
            "quotes/{quote_id}/files",
            {"quote_id": "quote_id", "order_id": "order_id"},
        ),
        (
            "orders/{order_id}/files",
            "orders/{order_id}/files",
            {"quote_id": None, "order_id": "order_id"},
        ),
    ],
)
def test_upload_routes_accept_generic_pdf_and_list_file(
    monkeypatch, route, list_route, expected_fields
):
    _mock_cloudinary_upload(monkeypatch)

    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    import app.models  # noqa: F401

    SQLModel.metadata.create_all(engine)
    user, customer_id, quote_id, order_id = _seed_upload_context(engine)

    app = _make_app(engine, user)
    client = TestClient(app)

    route_values = {
        "customer_id": customer_id,
        "quote_id": quote_id,
        "order_id": order_id,
    }
    upload_res = client.post(
        f"/api/{route.format(**route_values)}",
        files={"file": ("plan.pdf", b"%PDF-1.4 route upload", "application/octet-stream")},
        data={"kind": "PLAN"},
    )

    assert upload_res.status_code == 200, upload_res.text
    body = upload_res.json()
    assert body["customer_id"] == customer_id
    assert body["content_type"] == "application/pdf"
    assert body["secure_url"].startswith("https://cdn.example.com/customers/")

    for field, expected in expected_fields.items():
        expected_value = route_values[expected] if isinstance(expected, str) else expected
        assert body[field] == expected_value

    list_res = client.get(f"/api/{list_route.format(**route_values)}")
    assert list_res.status_code == 200, list_res.text
    listed = list_res.json()
    assert len(listed) == 1
    assert listed[0]["id"] == body["id"]
    assert listed[0]["content_type"] == "application/pdf"
