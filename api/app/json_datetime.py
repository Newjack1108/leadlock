"""Normalize naive UTC datetimes in JSON so browsers parse them as UTC.

Naive datetimes from Pydantic/SQLModel serialize as e.g. "2025-04-01T12:00:00" with no
offset. JavaScript interprets that as *local* wall time, so wall-clock display is wrong
by the UTC offset (e.g. 1 hour in BST). Appending "Z" marks UTC and fixes display.
"""

from __future__ import annotations

import json
import re
from typing import Any

# ISO-8601 local-time form without timezone (not date-only).
_NAIVE_UTC_ISO = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?$"
)


def append_z_if_naive_utc_iso(s: str) -> str:
    if not _NAIVE_UTC_ISO.match(s):
        return s
    return s + "Z"


def normalize_json_datetimes(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {k: normalize_json_datetimes(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [normalize_json_datetimes(x) for x in obj]
    if isinstance(obj, str):
        return append_z_if_naive_utc_iso(obj)
    return obj


def json_dumps_utf8(payload: Any) -> bytes:
    """Match Starlette JSONResponse encoding."""
    return json.dumps(
        payload,
        ensure_ascii=False,
        allow_nan=False,
        indent=None,
        separators=(",", ":"),
    ).encode("utf-8")
