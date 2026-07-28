"""Normalize and validate free-text What3Words addresses."""
from __future__ import annotations

import re
from typing import Optional

from fastapi import HTTPException

# Three lowercase words separated by dots (What3Words format after stripping ///).
_WHAT3WORDS_RE = re.compile(r"^[a-z]+\.[a-z]+\.[a-z]+$")


def normalize_what3words(value: Optional[str]) -> Optional[str]:
    """Strip whitespace and leading ///, lowercase. Empty becomes None."""
    if value is None:
        return None
    text = str(value).strip().lower()
    if text.startswith("///"):
        text = text[3:].strip()
    if not text:
        return None
    return text


def validate_what3words(value: Optional[str]) -> Optional[str]:
    """
    Normalize and validate a What3Words string.

    Returns None for empty input. Raises HTTP 400 when format is invalid.
    """
    normalized = normalize_what3words(value)
    if normalized is None:
        return None
    if not _WHAT3WORDS_RE.match(normalized):
        raise HTTPException(
            status_code=400,
            detail="What3Words must be three words separated by dots (e.g. filled.table.chair).",
        )
    return normalized
