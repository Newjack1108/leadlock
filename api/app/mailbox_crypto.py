"""Encrypt/decrypt per-user SMTP and IMAP passwords at rest."""
from __future__ import annotations

import logging
import os
from typing import Any, Optional

from cryptography.fernet import Fernet, InvalidToken

logger = logging.getLogger(__name__)

MAILBOX_ENCRYPTED_FIELDS = ("smtp_password", "imap_password")
_FERNET_PREFIX = "gAAAAA"


def _encryption_key() -> Optional[str]:
    return (
        (os.getenv("MAILBOX_PASSWORD_ENCRYPTION_KEY") or "").strip()
        or (os.getenv("BANK_DETAILS_ENCRYPTION_KEY") or "").strip()
        or None
    )


def _fernet() -> Fernet:
    key = _encryption_key()
    if not key:
        raise RuntimeError(
            "MAILBOX_PASSWORD_ENCRYPTION_KEY (or BANK_DETAILS_ENCRYPTION_KEY) is not set. "
            "Generate with: python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\""
        )
    return Fernet(key.encode("utf-8"))


def is_encrypted(stored: str) -> bool:
    return bool(stored) and stored.startswith(_FERNET_PREFIX)


def encrypt_mailbox_password(plain: Optional[str]) -> Optional[str]:
    if plain is None:
        return None
    value = plain.strip()
    if not value:
        return None
    if is_encrypted(value):
        return value
    return _fernet().encrypt(value.encode("utf-8")).decode("utf-8")


def decrypt_mailbox_password(stored: Optional[str]) -> Optional[str]:
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
        raise RuntimeError(
            "Failed to decrypt mailbox password; check MAILBOX_PASSWORD_ENCRYPTION_KEY"
        ) from exc


def prepare_mailbox_fields_for_save(update_data: dict[str, Any]) -> dict[str, Any]:
    result = dict(update_data)
    for field in MAILBOX_ENCRYPTED_FIELDS:
        if field not in result:
            continue
        incoming = result[field]
        if incoming is None:
            continue
        if isinstance(incoming, str) and not incoming.strip():
            result[field] = None
            continue
        result[field] = encrypt_mailbox_password(str(incoming) if incoming is not None else None)
    return result


def encrypt_existing_plaintext_mailbox_passwords(session: Any) -> int:
    """One-time migration: encrypt plaintext smtp/imap passwords in DB."""
    from sqlmodel import select

    from app.models import User

    if not _encryption_key():
        logger.warning(
            "MAILBOX_PASSWORD_ENCRYPTION_KEY not set; skipping mailbox password encryption migration"
        )
        return 0

    users = session.exec(select(User)).all()
    updated = 0
    for user in users:
        changed = False
        for field in MAILBOX_ENCRYPTED_FIELDS:
            stored = getattr(user, field, None)
            if not stored or not str(stored).strip():
                continue
            if is_encrypted(str(stored)):
                continue
            setattr(user, field, encrypt_mailbox_password(str(stored)))
            changed = True
        if changed:
            session.add(user)
            updated += 1
    if updated:
        session.commit()
        logger.info("Encrypted mailbox passwords for %s user(s)", updated)
    return updated
