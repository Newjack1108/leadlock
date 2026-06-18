"""Encrypt/decrypt and mask company bank account number and sort code at rest."""
from __future__ import annotations

import logging
import os
import re
from typing import Any, Optional

from cryptography.fernet import Fernet, InvalidToken

logger = logging.getLogger(__name__)

ENCRYPTED_FIELDS = ("account_number", "sort_code")
_FERNET_PREFIX = "gAAAAA"


def _encryption_key() -> Optional[str]:
    return (os.getenv("BANK_DETAILS_ENCRYPTION_KEY") or "").strip() or None


def _fernet() -> Fernet:
    key = _encryption_key()
    if not key:
        raise RuntimeError(
            "BANK_DETAILS_ENCRYPTION_KEY is not set. "
            "Generate with: python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\""
        )
    return Fernet(key.encode("utf-8"))


def is_encrypted(stored: str) -> bool:
    return bool(stored) and stored.startswith(_FERNET_PREFIX)


def encrypt_bank_value(plain: Optional[str]) -> Optional[str]:
    if plain is None:
        return None
    value = plain.strip()
    if not value:
        return None
    if is_encrypted(value):
        return value
    return _fernet().encrypt(value.encode("utf-8")).decode("utf-8")


def decrypt_bank_value(stored: Optional[str]) -> Optional[str]:
    if stored is None:
        return None
    value = stored.strip()
    if not value:
        return None
    if not is_encrypted(value):
        return value
    try:
        return _fernet().decrypt(value.encode("utf-8")).decode("utf-8")
    except InvalidToken as exc:
        raise RuntimeError("Failed to decrypt bank detail; check BANK_DETAILS_ENCRYPTION_KEY") from exc


def mask_account_number(plain: str) -> str:
    digits = re.sub(r"\D", "", plain)
    if len(digits) >= 4:
        return f"****{digits[-4:]}"
    if plain:
        return "****"
    return ""


def mask_sort_code(plain: str) -> str:
    digits = re.sub(r"\D", "", plain)
    if len(digits) >= 2:
        return f"**-**-{digits[-2:]}"
    if plain:
        return "**-**-**"
    return ""


def is_masked_account_number(value: Optional[str]) -> bool:
    if not value:
        return False
    return bool(re.fullmatch(r"\*{4}\d{0,4}", value.strip()))


def is_masked_sort_code(value: Optional[str]) -> bool:
    if not value:
        return False
    return bool(re.fullmatch(r"\*{2}-\*{2}-\*{0,2}\d{0,2}", value.strip()))


def get_decrypted_bank_details(company_settings: Any) -> dict[str, Optional[str]]:
    """Return plaintext bank fields for PDFs and public quote views."""
    return {
        "bank_name": getattr(company_settings, "bank_name", None),
        "bank_account_name": getattr(company_settings, "bank_account_name", None),
        "account_number": decrypt_bank_value(getattr(company_settings, "account_number", None)),
        "sort_code": decrypt_bank_value(getattr(company_settings, "sort_code", None)),
    }


def build_masked_bank_response(
    settings: Any,
) -> tuple[Optional[str], Optional[str], bool, bool]:
    """Return (masked_account, masked_sort, account_set, sort_set) for API responses."""
    stored_account = getattr(settings, "account_number", None)
    stored_sort = getattr(settings, "sort_code", None)
    account_set = bool(stored_account and str(stored_account).strip())
    sort_set = bool(stored_sort and str(stored_sort).strip())
    masked_account = None
    masked_sort = None
    if account_set:
        plain = decrypt_bank_value(stored_account)
        masked_account = mask_account_number(plain or "")
    if sort_set:
        plain = decrypt_bank_value(stored_sort)
        masked_sort = mask_sort_code(plain or "")
    return masked_account, masked_sort, account_set, sort_set


def prepare_bank_fields_for_save(
    update_data: dict[str, Any],
    existing_settings: Any,
) -> dict[str, Any]:
    """Encrypt sensitive fields; skip masked placeholders (unchanged values)."""
    result = dict(update_data)
    for field in ENCRYPTED_FIELDS:
        if field not in result:
            continue
        incoming = result[field]
        if incoming is None:
            continue
        if isinstance(incoming, str):
            stripped = incoming.strip()
            if not stripped:
                result[field] = None
                continue
            if field == "account_number" and is_masked_account_number(stripped):
                result.pop(field)
                continue
            if field == "sort_code" and is_masked_sort_code(stripped):
                result.pop(field)
                continue
        result[field] = encrypt_bank_value(str(incoming) if incoming is not None else None)
    return result


def encrypt_existing_plaintext_values(session: Any) -> int:
    """One-time migration: encrypt plaintext account_number and sort_code in DB."""
    from sqlmodel import select

    from app.models import CompanySettings

    if not _encryption_key():
        logger.warning("BANK_DETAILS_ENCRYPTION_KEY not set; skipping bank details encryption migration")
        return 0

    settings_rows = session.exec(select(CompanySettings)).all()
    updated = 0
    for settings in settings_rows:
        changed = False
        for field in ENCRYPTED_FIELDS:
            stored = getattr(settings, field, None)
            if not stored or not str(stored).strip():
                continue
            if is_encrypted(str(stored)):
                continue
            setattr(settings, field, encrypt_bank_value(str(stored)))
            changed = True
        if changed:
            session.add(settings)
            updated += 1
    if updated:
        session.commit()
        logger.info("Encrypted bank details for %s company settings row(s)", updated)
    return updated
