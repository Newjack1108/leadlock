"""Path allowlist for MARKETING users (deny-by-default on authenticated APIs)."""
from __future__ import annotations

import re

_GET = frozenset({"GET", "HEAD"})
_GET_POST = frozenset({"GET", "HEAD", "POST"})
_GET_PUT = frozenset({"GET", "HEAD", "PUT"})
_PATCH = frozenset({"PATCH"})
_POST = frozenset({"POST"})

# Marketing can inspect inbound leads, ads conversion, and website/configurator QA.
# Sales workflow, customers, quotes, orders, and admin stay blocked.
_ALLOWED: tuple[tuple[frozenset[str], re.Pattern[str]], ...] = (
    (_GET, re.compile(r"^/api/auth/login-quote$")),
    (_GET, re.compile(r"^/api/dashboard/stats$")),
    (_GET, re.compile(r"^/api/dashboard/lead-locations$")),
    (_GET, re.compile(r"^/api/reports/source-performance(/pdf)?$")),
    (_GET, re.compile(r"^/api/reports/facebook-lead-conversion(\.csv|/pdf)?$")),
    (_GET_POST, re.compile(r"^/api/settings/facebook-adverts$")),
    (_PATCH, re.compile(r"^/api/settings/facebook-adverts/\d+$")),
    (_GET_PUT, re.compile(r"^/api/settings/user/email$")),
    (_GET, re.compile(r"^/api/leads$")),
    (_GET, re.compile(r"^/api/leads/\d+$")),
    (_GET, re.compile(r"^/api/leads/\d+/(activities|status-history|allowed-transitions)$")),
    (_GET, re.compile(r"^/api/configurator-invites$")),
    (_GET, re.compile(r"^/api/configurator-invites/unread-count$")),
    (_GET, re.compile(r"^/api/configurator-invites/\d+$")),
    (_POST, re.compile(r"^/api/configurator-invites/\d+/mark-viewed$")),
    (_POST, re.compile(r"^/api/products/upload-image$")),
)


def marketing_may_access(method: str, path: str) -> bool:
    normalized_method = (method or "GET").upper()
    if normalized_method == "HEAD":
        normalized_method = "GET"
    normalized_path = (path or "").split("?", 1)[0].rstrip("/") or "/"
    check_method = "GET" if normalized_method == "GET" else normalized_method
    for methods, pattern in _ALLOWED:
        if check_method in methods and pattern.match(normalized_path):
            return True
    return False
