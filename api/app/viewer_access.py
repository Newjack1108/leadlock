"""Access rules for VIEWER (read-only) users."""
from __future__ import annotations

_SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})

# VIEWER may not see user admin or company settings (including bank details).
_BLOCKED_PATH_PREFIXES = (
    "/api/users",
    "/api/settings/company",
)


def viewer_may_access(method: str, path: str) -> bool:
    """True when a VIEWER is allowed to call this authenticated API path."""
    normalized_method = (method or "GET").upper()
    normalized_path = (path or "").split("?", 1)[0].rstrip("/") or "/"

    for prefix in _BLOCKED_PATH_PREFIXES:
        if normalized_path == prefix or normalized_path.startswith(prefix + "/"):
            return False

    return normalized_method in _SAFE_METHODS
