"""
Out-of-hours SMS bot orchestration for Twilio inbound messages.
"""
import json
import os
import re
import sys
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
BOT_HANDOVER_PREFIX = "[BOT_HANDOVER]"
BOT_HANDOVER_MESSAGE = (
    f"{BOT_HANDOVER_PREFIX} Thanks for your message. "
    "A team member will review this and get back to you on the next working day."
)
HANDOVER_HINTS = (
    "price",
    "discount",
    "complaint",
    "manager",
    "human",
    "call me",
    "ring me",
    "phone me",
    "urgent",
    "go ahead",
    "proceed",
    "move forward",
    "next step",
)
DEFER_OR_THINKING_HINTS = (
    "think about it",
    "think on it",
    "i will think",
    "i'll think",
    "come back to you",
    "come back to us",
    "get back to you",
    "get back to us",
    "let you know",
    "leave it with me",
    "discuss it",
    "talk it over",
    "not sure yet",
    "still thinking",
    "will be in touch",
    "not right now",
    "not just yet",
)
CLOSE_ACK_EXACT = {
    "thanks",
    "thank you",
    "ok",
    "okay",
    "perfect",
    "great",
    "cheers",
    "noted",
    "sounds good",
    "all good",
    "all sorted",
    "all set",
    "no thanks",
    "no thank you",
    "thats all",
    "that's all",
    "speak soon",
    "speak later",
    "will do",
}
CLOSE_ACK_PREFIXES = ("thanks", "thank you", "ok", "okay", "perfect", "great", "cheers")
RECENT_HANDOVER_WINDOW_HOURS = 72
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


def _normalize_inbound_body(body: str) -> str:
    text = (body or "").lower().replace("’", "'").strip()
    text = re.sub(r"[^a-z0-9\s']", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _contains_any_phrase(text: str, phrases: tuple[str, ...]) -> bool:
    return any(phrase in text for phrase in phrases)


def _contains_handover_hint(body: str) -> bool:
    text = _normalize_inbound_body(body)
    return _contains_any_phrase(text, HANDOVER_HINTS)


def _contains_defer_or_thinking_hint(body: str) -> bool:
    text = _normalize_inbound_body(body)
    return _contains_any_phrase(text, DEFER_OR_THINKING_HINTS)


def _is_close_ack(body: str) -> bool:
    if not body or "?" in body:
        return False
    if _contains_handover_hint(body) or _contains_defer_or_thinking_hint(body):
        return False
    text = _normalize_inbound_body(body)
    if not text:
        return False
    if text in CLOSE_ACK_EXACT:
        return True
    words = text.split()
    return len(words) <= 4 and any(text.startswith(prefix) for prefix in CLOSE_ACK_PREFIXES)


def _classify_inbound_intent(body: str) -> str:
    if _contains_defer_or_thinking_hint(body):
        return "defer_or_thinking"
    if _contains_handover_hint(body):
        return "handover_request"
    if _is_close_ack(body):
        return "close_ack"
    return "normal"


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
        if (msg.body or "").startswith(BOT_HANDOVER_PREFIX):
            return msg.created_at
    return None


def _recent_handover_context(
    session: Session,
    customer_id: int,
    *,
    now_utc: Optional[datetime] = None,
) -> Tuple[Optional[datetime], bool]:
    now_utc = now_utc or datetime.utcnow()
    last_handover = _last_handover_at(session, customer_id)
    if not last_handover:
        return None, False
    if (now_utc - last_handover) > timedelta(hours=RECENT_HANDOVER_WINDOW_HOURS):
        return None, False
    stmt = (
        select(SmsMessage)
        .where(SmsMessage.customer_id == customer_id)
        .where(SmsMessage.direction == SmsDirection.SENT)
        .where(SmsMessage.created_at > last_handover)
        .order_by(SmsMessage.created_at.desc())
    )
    human_follow_up_after_handover = any(
        msg.created_by_id is not None for msg in session.exec(stmt).all()
    )
    return last_handover, human_follow_up_after_handover


def should_bot_reply(
    session: Session,
    settings: Optional[CompanySettings],
    customer: Optional[Customer],
    inbound_body: str,
    inbound_received_at: Optional[datetime] = None,
) -> Tuple[bool, Optional[str]]:
    now_utc = datetime.utcnow()
    if not settings or not customer:
        return False, "no_settings_or_customer"
    if getattr(customer, "sms_bot_stopped", False):
        return False, "bot_stopped"
    if customer.sms_bot_paused_until and customer.sms_bot_paused_until > now_utc:
        return False, "customer_pause_active"
    if _contains_opt_out(inbound_body):
        customer.sms_bot_stopped = True
        customer.automated_reminder_outreach_opt_out = True
        return False, "opt_out_keyword"
    if not is_bot_active_now(settings, now_utc=now_utc):
        return False, "bot_inactive"
    sup = customer.sms_bot_suppress_auto_reply_before_utc
    if sup and inbound_received_at is not None:
        if inbound_received_at < sup:
            return False, "handover_inbound_before_resume"
        customer.sms_bot_suppress_auto_reply_before_utc = None
    pause_minutes = max(0, int(settings.sms_bot_pause_minutes_after_handover or 0))
    last_handover = _last_handover_at(session, customer.id)
    if pause_minutes and last_handover and (now_utc - last_handover) < timedelta(minutes=pause_minutes):
        return False, "handover_pause_window"
    max_replies = max(1, int(settings.sms_bot_max_replies_per_thread or 3))
    if _bot_sent_count_recent(session, customer.id) >= max_replies:
        return False, "max_replies_reached"
    intent = _classify_inbound_intent(inbound_body)
    if intent == "close_ack":
        return False, "close_ack_no_reply"
    if intent == "defer_or_thinking":
        recent_handover_at, human_follow_up = _recent_handover_context(
            session,
            customer.id,
            now_utc=now_utc,
        )
        if recent_handover_at:
            if human_follow_up:
                return False, "defer_after_team_follow_up_no_reply"
            return False, "defer_after_handover_no_reply"
        return True, "handover"
    if intent == "handover_request":
        return True, "handover"
    return True, None


def backfill_stop_opt_out_customers(session: Session) -> int:
    """
    Backfill customer stop flags from historical inbound STOP-like SMS messages.
    Returns number of customers updated.
    """
    stmt = (
        select(SmsMessage)
        .where(SmsMessage.direction == SmsDirection.RECEIVED)
        .where(SmsMessage.customer_id.is_not(None))
    )
    updated = 0
    seen_customer_ids: set[int] = set()
    for msg in session.exec(stmt).all():
        customer_id = msg.customer_id
        if not customer_id or customer_id in seen_customer_ids:
            continue
        if not _contains_opt_out(msg.body or ""):
            continue
        customer = session.get(Customer, customer_id)
        if not customer:
            continue
        changed = False
        if not getattr(customer, "sms_bot_stopped", False):
            customer.sms_bot_stopped = True
            changed = True
        if not getattr(customer, "automated_reminder_outreach_opt_out", False):
            customer.automated_reminder_outreach_opt_out = True
            changed = True
        if changed:
            session.add(customer)
            updated += 1
        seen_customer_ids.add(customer_id)
    if updated:
        session.commit()
    return updated


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
        "You are the company's out-of-hours SMS assistant. "
        "Reply in plain text under 320 characters. "
        "If the customer is simply acknowledging, thanking you, or closing the conversation, do not reopen it or ask extra questions. "
        "If the customer says they will think about it or come back later, hand over once and avoid repeating the handover in follow-ups. "
        "If the question is complex, pricing-specific, complaint-related, or unclear, politely hand over to a human for next business day. "
        "Keep the tone warm, brief, and professional. "
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


def _extract_text_from_responses_api(data: dict) -> str:
    """Read assistant text from POST /v1/responses JSON (SDK adds output_text; raw HTTP may only nest under output)."""
    direct = (data.get("output_text") or "").strip()
    if direct:
        return direct
    out = data.get("output")
    if not isinstance(out, list):
        return ""
    parts: list[str] = []
    for item in out:
        if not isinstance(item, dict):
            continue
        if item.get("type") != "message" or item.get("role") != "assistant":
            continue
        for block in item.get("content") or []:
            if not isinstance(block, dict):
                continue
            btype = block.get("type")
            txt = (block.get("text") or "").strip()
            if not txt:
                continue
            if btype in ("output_text", "text", None):
                parts.append(txt)
    return "\n".join(parts).strip()


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
            if not isinstance(data, dict):
                print("OpenAI Responses: non-object JSON body", file=sys.stderr, flush=True)
                return fallback, False
            text = _extract_text_from_responses_api(data)
            if not text:
                keys = sorted(data.keys()) if isinstance(data, dict) else []
                print(
                    f"OpenAI Responses: empty assistant text (top-level keys: {keys})",
                    file=sys.stderr,
                    flush=True,
                )
                return fallback, False
            return text[:640], True
    except httpx.HTTPStatusError as e:
        snippet = (e.response.text or "")[:800].replace("\n", " ")
        print(
            f"OpenAI Responses HTTP {e.response.status_code}: {snippet}",
            file=sys.stderr,
            flush=True,
        )
        return fallback, False
    except Exception as ex:
        print(f"OpenAI Responses error: {ex}", file=sys.stderr, flush=True)
        return fallback, False
