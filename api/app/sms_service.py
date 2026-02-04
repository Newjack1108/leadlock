"""
SMS service for sending and receiving SMS via Twilio.
"""
import os
import re
from typing import Optional, Tuple

from dotenv import load_dotenv

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


def get_twilio_config() -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """Return (account_sid, auth_token, from_phone)."""
    sid = os.getenv("TWILIO_ACCOUNT_SID")
    token = os.getenv("TWILIO_AUTH_TOKEN")
    from_phone = os.getenv("TWILIO_PHONE_NUMBER")
    return sid, token, from_phone


def send_sms(to_phone: str, body: str) -> Tuple[bool, Optional[str], Optional[str]]:
    """
    Send SMS via Twilio. Returns (success, message_sid, error_message).
    """
    sid, token, from_phone = get_twilio_config()
    if not sid or not token or not from_phone:
        return False, None, "Twilio not configured (TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_PHONE_NUMBER)"
    to_phone = normalize_phone(to_phone)
    if not to_phone:
        return False, None, "Invalid phone number"
    try:
        from twilio.rest import Client
        client = Client(sid, token)
        message = client.messages.create(body=body, from_=from_phone, to=to_phone)
        return True, message.sid, None
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
