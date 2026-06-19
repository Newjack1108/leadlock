import os

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

import pytest
from fastapi import UploadFile
from io import BytesIO

from app.image_upload_service import _normalize_specification_sheet_content_type


def _upload_file(filename: str, content_type: str, data: bytes) -> UploadFile:
    return UploadFile(filename=filename, file=BytesIO(data), headers={"content-type": content_type})


def test_normalize_specification_sheet_content_type_accepts_pdf():
    file = _upload_file("spec.pdf", "application/pdf", b"%PDF-1.4 test")
    assert _normalize_specification_sheet_content_type(file, b"%PDF-1.4 test") == "application/pdf"


def test_normalize_specification_sheet_content_type_accepts_generic_pdf_mime():
    file = _upload_file("spec.pdf", "application/octet-stream", b"%PDF-1.7 test")
    assert _normalize_specification_sheet_content_type(file, b"%PDF-1.7 test") == "application/pdf"


def test_normalize_specification_sheet_content_type_accepts_png():
    file = _upload_file("spec.png", "image/png", b"\x89PNG")
    assert _normalize_specification_sheet_content_type(file, b"\x89PNG") == "image/png"


def test_normalize_specification_sheet_content_type_rejects_other_files():
    file = _upload_file("notes.txt", "text/plain", b"hello")
    with pytest.raises(Exception):
        _normalize_specification_sheet_content_type(file, b"hello")
