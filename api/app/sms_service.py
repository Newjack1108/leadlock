"""
SMS service for sending and receiving SMS via Twilio.
"""
import os
import re
from typing import Optional, Tuple

from dotenv import load_dotenv
from sqlmodel import Session, select

from app.models import Customer, Lead

load_dotenv()


def normalize_phone(phone: str) -> str:
    """Normalize phone to E.164-like form for matching and sending. UK-centric."""
    if not phone:
        return ""
    s = re.sub(r"\s+", "", phone.strip())
    if s.startswith("+"):
        return s
    if s.startswith("00"):
        return "+" + s[2:]
    if s.startswith("0") and len(s) >= 10:
        return "+44" + s[1:]
    if s.startswith("44") and len(s) == 12 and s.isdigit():
        return "+" + s
    if len(s) >= 10 and s.isdigit():
        return "+44" + s
    return s


def validate_outbound_phone(phone: str) -> Tuple[bool, str, Optional[str]]:
    """
    Normalize and validate outbound phone numbers with UK-first defaults.
    Returns (is_valid, normalized_phone, error_message).
    """
    normalized = normalize_phone(phone)
    if not normalized:
        return False, "", "Invalid phone number"
    if not re.fullmatch(r"\+?\d+", normalized):
        return False, normalized, "Phone number must contain only digits (and optional leading +)"

    digits = normalized[1:] if normalized.startswith("+") else normalized
    if len(digits) < 10 or len(digits) > 15:
        return False, normalized, "Phone number must be between 10 and 15 digits"

    if normalized.startswith("+") and digits.startswith("0"):
        return False, normalized, "Phone number cannot include leading 0 after country code"

    return True, normalized, None


def get_twilio_config() -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """Return (account_sid, auth_token, from_phone)."""
    sid = os.getenv("TWILIO_ACCOUNT_SID")
    token = os.getenv("TWILIO_AUTH_TOKEN")
    from_phone = os.getenv("TWILIO_PHONE_NUMBER")
    return sid, token, from_phone


def resolve_sms_to_phone(
    session: Session,
    customer: Customer,
    *,
    explicit_to: Optional[str] = None,
    lead_id: Optional[int] = None,
) -> Optional[str]:
    """
    Pick the outbound destination number: explicit override, customer profile,
    then the given lead (if it belongs to this customer), then any linked lead
    with a phone (most recently updated first).
    """
    t = (explicit_to or "").strip()
    if t:
        return t
    t = (customer.phone or "").strip()
    if t:
        return t
    if lead_id is not None:
        lead = session.get(Lead, lead_id)
        if lead is not None and lead.customer_id == customer.id:
            p = (lead.phone or "").strip()
            if p:
                return p
    statement = (
        select(Lead)
        .where(Lead.customer_id == customer.id)
        .order_by(Lead.updated_at.desc())
    )
    for lead in session.exec(statement).all():
        p = (lead.phone or "").strip()
        if p:
            return p
    return None


def is_unsubscribed_recipient_error(error_message: Optional[str]) -> bool:
    """True when Twilio rejected send to an opted-out number (error 21610)."""
    if not error_message:
        return False
    msg = error_message.lower()
    return "21610" in msg or "unsubscribed recipient" in msg


def send_sms(to_phone: str, body: str) -> Tuple[bool, Optional[str], Optional[str]]:
    """
    Send SMS via Twilio. Returns (success, message_sid, error_message).
    """
    sid, token, from_phone = get_twilio_config()
    if not sid or not token or not from_phone:
        return False, None, "Twilio not configured (TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_PHONE_NUMBER)"
    is_valid, normalized_phone, phone_error = validate_outbound_phone(to_phone)
    if not is_valid:
        return False, None, phone_error or "Invalid phone number"
    try:
        from twilio.rest import Client
        from twilio.base.exceptions import TwilioRestException
        client = Client(sid, token)
        message = client.messages.create(body=body, from_=from_phone, to=normalized_phone)
        return True, message.sid, None
    except TwilioRestException as e:
        code = getattr(e, "code", None)
        if code:
            return False, None, f"Twilio error {code}: {e.msg}"
        return False, None, str(e)
    except Exception as e:
        return False, None, str(e)


def validate_twilio_webhook(url: str, params: dict, signature: str, auth_token: str) -> bool:
    """
    Validate that the request came from Twilio using X-Twilio-Signature.
    url: full webhook URL (e.g. https://your-api.com/api/webhooks/twilio/sms)
    params: dict of form body (e.g. request.form() or parsed body)
    signature: value of X-Twilio-Signature header
    auth_token: TWILIO_AUTH_TOKEN
    """
    if not auth_token or not signature:
        return False
    try:
        from twilio.request_validator import RequestValidator
        validator = RequestValidator(auth_token)
        return validator.validate(url, params, signature)
    except Exception:
        return False
