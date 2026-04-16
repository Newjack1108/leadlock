"""
Out-of-hours SMS bot orchestration for Twilio inbound messages.
"""
import json
import os
import re
from datetime import datetime, timedelta
from typing import Optional, Tuple
from zoneinfo import ZoneInfo

import httpx
from sqlmodel import Session, select

from app.models import CompanySettings, Customer, SmsBotMode, SmsDirection, SmsMessage


DEFAULT_BUSINESS_HOURS = {
    "mon": {"enabled": True, "start": "09:00", "end": "17:00"},
    "tue": {"enabled": True, "start": "09:00", "end": "17:00"},
    "wed": {"enabled": True, "start": "09:00", "end": "17:00"},
    "thu": {"enabled": True, "start": "09:00", "end": "17:00"},
    "fri": {"enabled": True, "start": "09:00", "end": "17:00"},
    "sat": {"enabled": False, "start": "09:00", "end": "17:00"},
    "sun": {"enabled": False, "start": "09:00", "end": "17:00"},
}

OPT_OUT_KEYWORDS = {"STOP", "UNSUBSCRIBE", "CANCEL", "END", "QUIT", "STOPALL"}
HANDOVER_HINTS = ("price", "discount", "complaint", "manager", "human", "call me", "urgent")
WEEKDAY_KEYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]


def _parse_hours(settings: Optional[CompanySettings]) -> dict:
    if not settings or not settings.sms_bot_business_hours_json:
        return DEFAULT_BUSINESS_HOURS
    try:
        loaded = json.loads(settings.sms_bot_business_hours_json)
    except json.JSONDecodeError:
        return DEFAULT_BUSINESS_HOURS
    if not isinstance(loaded, dict):
        return DEFAULT_BUSINESS_HOURS
    merged = dict(DEFAULT_BUSINESS_HOURS)
    for key in WEEKDAY_KEYS:
        day = loaded.get(key)
        if isinstance(day, dict):
            merged[key] = {
                "enabled": bool(day.get("enabled", merged[key]["enabled"])),
                "start": str(day.get("start", merged[key]["start"])),
                "end": str(day.get("end", merged[key]["end"])),
            }
    return merged


def is_bot_active_now(settings: Optional[CompanySettings], now_utc: Optional[datetime] = None) -> bool:
    if not settings:
        return False
    mode = settings.sms_bot_mode or SmsBotMode.OFF
    if mode == SmsBotMode.ON:
        return True
    if mode == SmsBotMode.OFF:
        return False
    now_utc = now_utc or datetime.utcnow()
    tz_name = settings.sms_bot_timezone or "Europe/London"
    try:
        local_now = now_utc.replace(tzinfo=ZoneInfo("UTC")).astimezone(ZoneInfo(tz_name))
    except Exception:
        local_now = now_utc.replace(tzinfo=ZoneInfo("UTC")).astimezone(ZoneInfo("Europe/London"))
    weekday_key = WEEKDAY_KEYS[local_now.weekday()]
    schedule = _parse_hours(settings).get(weekday_key, {})
    if not schedule.get("enabled", False):
        return True
    start = str(schedule.get("start", "09:00"))
    end = str(schedule.get("end", "17:00"))
    current = local_now.strftime("%H:%M")
    return current < start or current >= end


def _contains_opt_out(body: str) -> bool:
    words = {w.strip().upper() for w in re.split(r"\s+", (body or "").strip()) if w.strip()}
    return any(k in words for k in OPT_OUT_KEYWORDS)


def _contains_handover_hint(body: str) -> bool:
    lower = (body or "").lower()
    return any(k in lower for k in HANDOVER_HINTS)


def _bot_sent_count_recent(session: Session, customer_id: int, minutes: int = 1440) -> int:
    since = datetime.utcnow() - timedelta(minutes=minutes)
    stmt = (
        select(SmsMessage)
        .where(SmsMessage.customer_id == customer_id)
        .where(SmsMessage.direction == SmsDirection.SENT)
        .where(SmsMessage.created_by_id.is_(None))
        .where(SmsMessage.created_at >= since)
    )
    return len(list(session.exec(stmt).all()))


def _last_handover_at(session: Session, customer_id: int) -> Optional[datetime]:
    stmt = (
        select(SmsMessage)
        .where(SmsMessage.customer_id == customer_id)
        .where(SmsMessage.direction == SmsDirection.SENT)
        .where(SmsMessage.created_by_id.is_(None))
        .order_by(SmsMessage.created_at.desc())
    )
    for msg in session.exec(stmt).all():
        if (msg.body or "").startswith("[BOT_HANDOVER]"):
            return msg.created_at
    return None


def should_bot_reply(
    session: Session,
    settings: Optional[CompanySettings],
    customer: Optional[Customer],
    inbound_body: str,
) -> Tuple[bool, Optional[str]]:
    if not settings or not customer:
        return False, "no_settings_or_customer"
    if customer.sms_bot_paused_until and customer.sms_bot_paused_until > datetime.utcnow():
        return False, "customer_pause_active"
    if _contains_opt_out(inbound_body):
        return False, "opt_out_keyword"
    if not is_bot_active_now(settings):
        return False, "bot_inactive"
    pause_minutes = max(0, int(settings.sms_bot_pause_minutes_after_handover or 0))
    last_handover = _last_handover_at(session, customer.id)
    if pause_minutes and last_handover and (datetime.utcnow() - last_handover) < timedelta(minutes=pause_minutes):
        return False, "handover_pause_window"
    max_replies = max(1, int(settings.sms_bot_max_replies_per_thread or 3))
    if _bot_sent_count_recent(session, customer.id) >= max_replies:
        return False, "max_replies_reached"
    if _contains_handover_hint(inbound_body):
        return True, "handover"
    return True, None


def _build_company_context_block(settings: Optional[CompanySettings]) -> Optional[str]:
    if not settings:
        return None
    display = (settings.trading_name or "").strip() or (settings.company_name or "").strip()
    phone = (settings.phone or "").strip()
    website = (settings.website or "").strip()
    lines: list[str] = []
    if display:
        lines.append(f"- Company name: {display}")
    if phone:
        lines.append(f"- Phone: {phone}")
    if website:
        lines.append(f"- Website: {website}")
    if not lines:
        return None
    return "Company context (facts only; do not contradict):\n" + "\n".join(lines)


def _build_sms_bot_system_prompt(settings: Optional[CompanySettings]) -> str:
    """Guardrails first, then optional company facts, then company-specific instructions."""
    guardrails = (
        "You are LeadLock's out-of-hours SMS assistant. "
        "Reply in plain text under 320 characters. "
        "If the question is complex, pricing-specific, complaint-related, or unclear, politely hand over to a human for next business day. "
        "Do not invent facts or promise specific installation dates."
    )
    parts: list[str] = [guardrails]
    ctx = _build_company_context_block(settings)
    if ctx:
        parts.append(ctx)
    custom = (settings.sms_bot_system_instructions if settings else None) or ""
    custom = custom.strip()
    if custom:
        parts.append(custom)
    return "\n\n".join(parts)


async def generate_bot_reply(
    settings: Optional[CompanySettings],
    customer_name: str,
    inbound_body: str,
) -> Tuple[str, bool]:
    fallback = (
        (settings.sms_bot_fallback_message if settings else None)
        or "Thanks for your message. Our team is currently out of hours and will reply as soon as we are back."
    )
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        return fallback, False

    # Responses API: optional tracing IDs (not legacy Assistants API calls).
    prompt_id = (
        os.getenv("OPENAI_PROMPT_ID", "").strip()
        or os.getenv("OPENAI_RESPONSES_PROMPT_ID", "").strip()
    )
    legacy_assistant_id = os.getenv("OPENAI_ASSISTANT_ID", "").strip()

    model = os.getenv("OPENAI_SMS_BOT_MODEL", "").strip() or "gpt-4.1-mini"

    metadata: dict = {"channel": "sms"}
    if prompt_id:
        metadata["prompt_id"] = prompt_id
    if legacy_assistant_id:
        metadata["assistant_id"] = legacy_assistant_id

    url = "https://api.openai.com/v1/responses"
    instructions = _build_sms_bot_system_prompt(settings)
    payload = {
        "model": model,
        "input": [
            {
                "role": "system",
                "content": [{"type": "input_text", "text": instructions}],
            },
            {
                "role": "user",
                "content": [
                    {
                        "type": "input_text",
                        "text": f"Customer: {customer_name or 'Customer'}\nInbound SMS: {inbound_body}",
                    }
                ],
            },
        ],
        "metadata": metadata,
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    try:
        async with httpx.AsyncClient(timeout=12.0) as client:
            resp = await client.post(url, headers=headers, json=payload)
            resp.raise_for_status()
            data = resp.json()
            text = (data.get("output_text") or "").strip()
            if not text:
                return fallback, False
            return text[:640], True
    except Exception:
        return fallback, False
