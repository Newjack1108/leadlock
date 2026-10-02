"""Verify Meta (Facebook) webhook request signatures."""
from __future__ import annotations

import hashlib
import hmac
import os
from typing import Optional


def facebook_app_secret() -> Optional[str]:
    return (os.getenv("FACEBOOK_APP_SECRET") or "").strip() or None


def compute_facebook_signature(raw_body: bytes, app_secret: str) -> str:
    digest = hmac.new(
        app_secret.encode("utf-8"),
        msg=raw_body,
        digestmod=hashlib.sha256,
    ).hexdigest()
    return f"sha256={digest}"


def verify_facebook_signature(
    raw_body: bytes,
    signature_header: Optional[str],
    app_secret: Optional[str] = None,
) -> bool:
    secret = (app_secret if app_secret is not None else facebook_app_secret()) or ""
    if not secret:
        return False
    if not signature_header:
        return False
    expected = compute_facebook_signature(raw_body, secret)
    return hmac.compare_digest(signature_header.strip(), expected)
