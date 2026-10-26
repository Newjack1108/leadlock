"""Unit tests for SMS bot opening-hours formatting and system prompt guardrails."""
import json
import os
from datetime import datetime

from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

from app.models import CompanySettings, User, UserRole
from app.sms_bot_service import (
    DEFAULT_BUSINESS_HOURS,
    RECOMMENDED_SMS_BOT_SYSTEM_INSTRUCTIONS,
    _build_company_context_block,
    _build_sms_bot_system_prompt,
    _format_clock_for_prompt,
    _format_opening_hours_lines,
)


def _engine():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    return engine


def _settings(session: Session, **overrides) -> CompanySettings:
    user = User(
        email=f"director-{datetime.utcnow().timestamp()}@example.com",
        hashed_password="dummy",
        full_name="Director",
        role=UserRole.DIRECTOR,
    )
    session.add(user)
    session.commit()
    session.refresh(user)
    settings = CompanySettings(
        company_name=overrides.pop("company_name", "Cheshire Sheds"),
        trading_name=overrides.pop("trading_name", "Cheshire Sheds"),
        phone=overrides.pop("phone", "01234567890"),
        website=overrides.pop("website", "https://example.com"),
        updated_by_id=user.id,
        sms_bot_business_hours_json=overrides.pop(
            "sms_bot_business_hours_json",
            json.dumps(DEFAULT_BUSINESS_HOURS),
        ),
        **overrides,
    )
    session.add(settings)
    session.commit()
    session.refresh(settings)
    return settings


def test_format_clock_for_prompt():
    assert _format_clock_for_prompt("08:00") == "8am"
    assert _format_clock_for_prompt("17:00") == "5pm"
    assert _format_clock_for_prompt("15:00") == "3pm"
    assert _format_clock_for_prompt("09:30") == "9:30am"
    assert _format_clock_for_prompt("12:00") == "12pm"
    assert _format_clock_for_prompt("00:00") == "12am"


def test_format_opening_hours_groups_consecutive_days():
    lines = _format_opening_hours_lines(DEFAULT_BUSINESS_HOURS)
    assert lines == [
        "- Monday–Thursday: 8am–5pm",
        "- Friday: 8am–3pm",
        "- Saturday: 9am–2pm",
        "- Sunday: closed",
    ]


def test_company_context_includes_opening_hours():
    with Session(_engine()) as session:
        settings = _settings(session)
        block = _build_company_context_block(settings)
    assert block is not None
    assert "Opening hours:" in block
    assert "Monday–Thursday: 8am–5pm" in block
    assert "Friday: 8am–3pm" in block
    assert "Saturday: 9am–2pm" in block
    assert "Sunday: closed" in block
    assert "Cheshire Sheds" in block


def test_guardrails_require_complete_answer_without_handover():
    with Session(_engine()) as session:
        settings = _settings(session)
        prompt = _build_sms_bot_system_prompt(settings)
    assert "Do not say you have passed the message on" in prompt
    assert "when the answer is complete" in prompt
    assert "never invent hours, staff names" in prompt
    assert "Hand over only when you cannot complete the answer" in prompt
    assert "Monday–Thursday: 8am–5pm" in prompt


def test_recommended_company_instructions_mention_wayne_only_for_handover():
    text = RECOMMENDED_SMS_BOT_SYSTEM_INSTRUCTIONS
    assert "Wayne" in text
    assert "fully answer" in text
    assert "genuine handovers" in text
