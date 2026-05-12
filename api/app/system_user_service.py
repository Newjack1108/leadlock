"""
Dedicated User row for automation attribution (activities, webhook logs, outreach messages).

Actor users (SMTP, templates) stay separate; see customer_outreach_service._resolve_actor_user_id.
"""
import os
import secrets
from typing import Optional

from sqlmodel import Session, select

from app.auth import get_password_hash
from app.models import User, UserRole

DEFAULT_SYSTEM_EMAIL = "system@leadlock.internal"
SYSTEM_USER_FULL_NAME = "System"


def system_user_email() -> str:
    return (os.getenv("SYSTEM_USER_EMAIL") or DEFAULT_SYSTEM_EMAIL).strip().lower()


def is_system_user_email(email: Optional[str]) -> bool:
    if email is None:
        return False
    return email.strip().lower() == system_user_email()


def has_reserved_system_name(full_name: Optional[str]) -> bool:
    if full_name is None:
        return False
    return full_name.strip().casefold() == SYSTEM_USER_FULL_NAME.casefold()


def is_system_user(user: Optional[User]) -> bool:
    if user is None:
        return False
    return is_system_user_email(user.email)


def get_or_create_system_user(session: Session) -> User:
    email = system_user_email()
    existing = session.exec(select(User).where(User.email == email)).first()
    if existing:
        changed = False
        if existing.full_name != SYSTEM_USER_FULL_NAME:
            existing.full_name = SYSTEM_USER_FULL_NAME
            changed = True
        if existing.is_active:
            existing.is_active = False
            changed = True
        if changed:
            session.add(existing)
            session.commit()
            session.refresh(existing)
        return existing
    user = User(
        email=email,
        full_name=SYSTEM_USER_FULL_NAME,
        hashed_password=get_password_hash(secrets.token_urlsafe(48)),
        role=UserRole.DIRECTOR,
        is_active=False,
    )
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


def get_system_user_id(session: Session) -> int:
    return get_or_create_system_user(session).id
