from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.routers import auth


def test_login_quote_requires_auth():
    app = FastAPI()
    app.include_router(auth.router)
    client = TestClient(app)

    response = client.get("/api/auth/login-quote")
    assert response.status_code == 401
