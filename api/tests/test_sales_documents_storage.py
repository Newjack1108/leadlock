import asyncio
import os
from types import SimpleNamespace

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from app.auth import get_current_user
from app.database import get_session
from app.models import SalesDocument, User, UserRole
from app.routers import sales_documents
from app.sales_document_service import load_sales_document_bytes


def _make_app(engine, user: User):
    def get_session_override():
        with Session(engine) as session:
            yield session

    app = FastAPI()
    app.include_router(sales_documents.router)
    app.dependency_overrides[get_session] = get_session_override
    app.dependency_overrides[get_current_user] = lambda: user
    return app


def test_sales_document_upload_stores_cloud_url_and_downloads_via_proxy(monkeypatch):
    monkeypatch.setenv("CLOUDINARY_CLOUD_NAME", "demo-cloud")
    monkeypatch.setenv("CLOUDINARY_API_KEY", "demo-key")
    monkeypatch.setenv("CLOUDINARY_API_SECRET", "demo-secret")

    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        user = User(
            email="sales-docs@example.com",
            hashed_password="x",
            full_name="Sales Manager",
            role=UserRole.SALES_MANAGER,
        )
        session.add(user)
        session.commit()
        session.refresh(user)

    captured: dict[str, object] = {}

    def fake_upload(content, **kwargs):
        captured["uploaded_content"] = content
        captured["upload_kwargs"] = kwargs
        return {
            "secure_url": "https://cdn.example.com/sales-documents/price-list.pdf",
            "public_id": "sales-documents/price-list",
            "resource_type": "raw",
        }

    class MockAsyncClient:
        def __init__(self, *args, **kwargs):
            captured["client_kwargs"] = kwargs

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def get(self, url):
            captured["download_url"] = url
            return SimpleNamespace(
                status_code=200,
                is_success=True,
                content=b"%PDF-1.4 cloud document",
            )

    monkeypatch.setattr("app.sales_document_service.cloudinary.uploader.upload", fake_upload)
    monkeypatch.setattr("app.sales_document_service.httpx.AsyncClient", MockAsyncClient)

    app = _make_app(engine, user)
    client = TestClient(app)

    upload_res = client.post(
        "/api/sales-documents",
        files={"file": ("price-list.pdf", b"%PDF-1.4 upload source", "application/pdf")},
        data={"name": "Spring Price List", "category": "Price List"},
    )
    assert upload_res.status_code == 200, upload_res.text
    doc_id = upload_res.json()["id"]

    with Session(engine) as session:
        doc = session.get(SalesDocument, doc_id)
        assert doc is not None
        assert doc.file_path == "https://cdn.example.com/sales-documents/price-list.pdf"
        assert doc.cloudinary_public_id == "sales-documents/price-list"
        assert doc.cloudinary_resource_type == "raw"

    download_res = client.get(f"/api/sales-documents/{doc_id}/download")
    assert download_res.status_code == 200, download_res.text
    assert download_res.content == b"%PDF-1.4 cloud document"
    assert download_res.headers["content-type"].startswith("application/pdf")
    assert "price-list.pdf" in download_res.headers["content-disposition"]
    assert captured["uploaded_content"] == b"%PDF-1.4 upload source"
    assert captured["download_url"] == "https://cdn.example.com/sales-documents/price-list.pdf"


def test_load_sales_document_bytes_supports_legacy_local_path(tmp_path):
    legacy_path = tmp_path / "legacy-price-list.csv"
    legacy_path.write_bytes(b"col1,col2\n1,2\n")

    doc = SalesDocument(
        name="Legacy Price List",
        filename="legacy-price-list.csv",
        file_path=str(legacy_path),
        content_type="text/csv",
    )

    assert asyncio.run(load_sales_document_bytes(doc)) == b"col1,col2\n1,2\n"
