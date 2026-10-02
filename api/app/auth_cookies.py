"""HTTP-only auth cookie helpers and token extraction from cookie or Bearer header."""
from __future__ import annotations

import os
from typing import Literal, Optional

from fastapi import Request, Response

AUTH_COOKIE_NAME = "leadlock_token"


def _cookie_secure() -> bool:
    if (os.getenv("AUTH_COOKIE_SECURE") or "").strip().lower() in {"0", "false", "no", "off"}:
        return False
    if os.getenv("RAILWAY_ENVIRONMENT"):
        return True
    return (os.getenv("AUTH_COOKIE_SECURE") or "").strip().lower() in {"1", "true", "yes", "on"}


def set_auth_cookie(response: Response, token: str, max_age_seconds: int) -> None:
    secure = _cookie_secure()
    # Cross-origin SPA → API needs SameSite=None; same-site / local uses Lax.
    samesite = _cookie_samesite(secure)
    response.set_cookie(
        key=AUTH_COOKIE_NAME,
        value=token,
        httponly=True,
        secure=secure if samesite != "none" else True,
        samesite=samesite,
        max_age=max_age_seconds,
        path="/",
    )


def _cookie_samesite(secure: bool) -> Literal["lax", "none"]:
    cross_site = (os.getenv("AUTH_COOKIE_CROSS_SITE") or "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    return "none" if (cross_site and secure) else "lax"


def clear_auth_cookie(response: Response) -> None:
    """Clear with the same flags used when setting, or the browser keeps the cookie."""
    secure = _cookie_secure()
    samesite = _cookie_samesite(secure)
    response.delete_cookie(
        key=AUTH_COOKIE_NAME,
        path="/",
        secure=True if samesite == "none" else secure,
        httponly=True,
        samesite=samesite,
    )


def extract_bearer_or_cookie_token(request: Request, authorization: Optional[str] = None) -> Optional[str]:
    if authorization and authorization.startswith("Bearer "):
        token = authorization[7:].strip()
        if token:
            return token
    cookie_token = request.cookies.get(AUTH_COOKIE_NAME)
    if cookie_token:
        return cookie_token.strip() or None
    return None
