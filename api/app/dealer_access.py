"""Path allowlist for DEALER_ADMIN / DEALER_USER (deny-by-default on authenticated APIs)."""
from __future__ import annotations

import re

_SAFE = frozenset({"GET", "HEAD", "OPTIONS"})
_ALL = frozenset({"GET", "HEAD", "OPTIONS", "POST", "PUT", "PATCH", "DELETE"})

# Dealers use the dealer portal only. Staff CRM routes stay blocked.
_ALLOWED: tuple[tuple[frozenset[str], re.Pattern[str]], ...] = (
    (_SAFE, re.compile(r"^/api/auth/login-quote$")),
    (_ALL, re.compile(r"^/api/dealer-portal(/.*)?$")),
)


def dealer_may_access(method: str, path: str) -> bool:
    normalized_method = (method or "GET").upper()
    if normalized_method == "HEAD":
        normalized_method = "GET"
    normalized_path = (path or "").split("?", 1)[0].rstrip("/") or "/"
    check_method = "GET" if normalized_method == "GET" else normalized_method
    for methods, pattern in _ALLOWED:
        if check_method in methods and pattern.match(normalized_path):
            return True
    return False
