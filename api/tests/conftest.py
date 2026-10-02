"""Pytest defaults for local security-sensitive settings."""
import os

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("ALLOW_INSECURE_SECRET_KEY", "true")
os.environ.setdefault("SECRET_KEY", "test-secret-key-for-unit-tests-only")
os.environ.setdefault("FACEBOOK_APP_SECRET", "test-facebook-app-secret")
