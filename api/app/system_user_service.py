"""
Dedicated User row for automation attribution (activities, webhook logs, outreach messages).

Actor users (SMTP, templates) stay separate; see customer_outreach_service._resolve_actor_user_id.
"""
import os
import secrets

from sqlmodel import Session, select

from app.auth import get_password_hash
from app.models import User, UserRole

DEFAULT_SYSTEM_EMAIL = "system@leadlock.internal"


def system_user_email() -> str:
    return (os.getenv("SYSTEM_USER_EMAIL") or DEFAULT_SYSTEM_EMAIL).strip().lower()


def get_or_create_system_user(session: Session) -> User:
    email = system_user_email()
    existing = session.exec(select(User).where(User.email == email)).first()
    if existing:
        changed = False
        if existing.full_name != "System":
            existing.full_name = "System"
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
        full_name="System",
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
