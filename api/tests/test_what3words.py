"""Unit tests for What3Words normalize/validate helpers."""
import pytest
from fastapi import HTTPException

from app.what3words import normalize_what3words, validate_what3words


def test_normalize_strips_slashes_and_lowercases():
    assert normalize_what3words("///Filled.Table.Chair") == "filled.table.chair"
    assert normalize_what3words("  INDEX.HOME.RAFT  ") == "index.home.raft"
    assert normalize_what3words("") is None
    assert normalize_what3words(None) is None
    assert normalize_what3words("///") is None


def test_validate_accepts_valid():
    assert validate_what3words("filled.table.chair") == "filled.table.chair"
    assert validate_what3words("///Filled.Table.Chair") == "filled.table.chair"


def test_validate_rejects_invalid():
    with pytest.raises(HTTPException) as exc:
        validate_what3words("not-valid")
    assert exc.value.status_code == 400

    with pytest.raises(HTTPException):
        validate_what3words("only.two")

    with pytest.raises(HTTPException):
        validate_what3words("has.number1.word")
