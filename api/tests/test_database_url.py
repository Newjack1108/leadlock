"""Unit tests for DATABASE_URL normalization used by SQLAlchemy create_engine."""
import os

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

from app.database import _normalize_database_url


def test_postgres_scheme_gains_psycopg2_driver():
    assert (
        _normalize_database_url("postgres://user:pass@host:5432/db")
        == "postgresql+psycopg2://user:pass@host:5432/db?sslmode=require"
    )


def test_postgresql_scheme_gains_psycopg2_driver():
    assert (
        _normalize_database_url("postgresql://user:pass@host:5432/db")
        == "postgresql+psycopg2://user:pass@host:5432/db?sslmode=require"
    )


def test_sqlite_url_unchanged():
    assert _normalize_database_url("sqlite:///:memory:") == "sqlite:///:memory:"
    assert _normalize_database_url("sqlite:///./leadlock.db") == "sqlite:///./leadlock.db"


def test_already_qualified_driver_unchanged():
    url = "postgresql+psycopg2://user:pass@host:5432/db?sslmode=require"
    assert _normalize_database_url(url) == url


def test_railway_internal_skips_sslmode():
    assert (
        _normalize_database_url(
            "postgresql://user:pass@postgres.railway.internal:5432/db"
        )
        == "postgresql+psycopg2://user:pass@postgres.railway.internal:5432/db"
    )


def test_localhost_skips_sslmode():
    assert (
        _normalize_database_url("postgresql://user:pass@localhost:5432/db")
        == "postgresql+psycopg2://user:pass@localhost:5432/db"
    )
