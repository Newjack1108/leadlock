"""
Facebook Messenger service: send messages, fetch user profile, parse webhook payloads.
"""
import os
import httpx
from typing import Optional, List, Any
from datetime import datetime

GRAPH_API_BASE = "https://graph.facebook.com/v21.0"


def get_page_access_token() -> Optional[str]:
    """Return the Page Access Token from environment."""
    return os.getenv("FACEBOOK_PAGE_ACCESS_TOKEN")


def send_messenger_message(
    recipient_psid: str,
    body: str,
    page_access_token: Optional[str] = None,
) -> tuple[bool, Optional[str], Optional[str]]:
    """
    Send a text message via Facebook Graph API.
    Returns (success, message_id, error_message).
    """
    token = page_access_token or get_page_access_token()
    if not token:
        return False, None, "Facebook Messenger not configured (missing FACEBOOK_PAGE_ACCESS_TOKEN)"

    url = f"{GRAPH_API_BASE}/me/messages"
    payload = {
        "recipient": {"id": recipient_psid},
        "messaging_type": "RESPONSE",
        "message": {"text": body},
    }

    try:
        with httpx.Client(timeout=15.0) as client:
            resp = client.post(url, json=payload, params={"access_token": token})
            data = resp.json()
            if resp.status_code != 200:
                error_msg = data.get("error", {}).get("message", resp.text)
                return False, None, error_msg
            mid = data.get("message_id")
            return True, mid, None
    except Exception as e:
        return False, None, str(e)


def get_user_profile(
    psid: str,
    page_access_token: Optional[str] = None,
) -> tuple[bool, Optional[str], Optional[str], Optional[str], Optional[str]]:
    """
    Fetch user profile (first_name, last_name, optional phone) from Graph API.
    Phone may require user_phone_number permission and might not be returned.
    Returns (success, first_name, last_name, phone, error_message).
    """
    token = page_access_token or get_page_access_token()
    if not token:
        return False, None, None, None, "Facebook Messenger not configured"

    url = f"{GRAPH_API_BASE}/{psid}"
    # Request phone; API may omit it or error if permission not granted - we treat as no phone
    params = {"fields": "first_name,last_name,mobile_phone", "access_token": token}

    try:
        with httpx.Client(timeout=10.0) as client:
            resp = client.get(url, params=params)
            data = resp.json()
            if resp.status_code != 200:
                error_msg = data.get("error", {}).get("message", resp.text)
                return False, None, None, None, error_msg
            first = data.get("first_name", "") or None
            last = data.get("last_name", "") or None
            phone = data.get("mobile_phone")
            if not phone or not str(phone).strip():
                phone = None
            else:
                phone = str(phone).strip()
            return True, first, last, phone, None
    except Exception as e:
        return False, None, None, None, str(e)


def fetch_leadgen_lead(
    leadgen_id: str,
    page_access_token: Optional[str] = None,
) -> tuple[bool, Optional[dict], Optional[str]]:
    """
    Fetch lead form data from Graph API by leadgen_id.
    Returns (success, field_map, error_message).
    field_map is a dict of field name -> value (e.g. full_name, email, phone_number, etc.).
    """
    token = page_access_token or get_page_access_token()
    if not token:
        return False, None, "Facebook not configured (missing FACEBOOK_PAGE_ACCESS_TOKEN)"

    url = f"{GRAPH_API_BASE}/{leadgen_id}"
    params = {"fields": "id,created_time,field_data", "access_token": token}

    try:
        with httpx.Client(timeout=10.0) as client:
            resp = client.get(url, params=params)
            data = resp.json()
            if resp.status_code != 200:
                error_msg = data.get("error", {}).get("message", resp.text)
                return False, None, error_msg
            field_data = data.get("field_data") or []
            field_map: dict[str, str] = {}
            for item in field_data:
                name = item.get("name")
                values = item.get("values") or []
                if name is not None and values:
                    field_map[name] = str(values[0]).strip() if values[0] is not None else ""
            return True, field_map, None
    except Exception as e:
        return False, None, str(e)


def parse_webhook_payload(body: dict) -> List[dict]:
    """
    Extract messaging events from Facebook webhook payload.
    Returns a list of event dicts, each with: sender_id (PSID), text, mid, timestamp (optional).
    Handles 'message' and 'postback' (postback payload as text).
    """
    events = []
    entries = body.get("entry", [])
    for entry in entries:
        for messaging in entry.get("messaging", []):
            sender_id = messaging.get("sender", {}).get("id")
            if not sender_id:
                continue
            timestamp = messaging.get("timestamp")

            # Message event
            if "message" in messaging:
                msg = messaging["message"]
                mid = msg.get("mid")
                text = msg.get("text", "").strip()
                if text:
                    events.append({
                        "sender_id": sender_id,
                        "text": text,
                        "mid": mid,
                        "timestamp": timestamp,
                    })
                # Skip attachments in v1

            # Postback (e.g. button click)
            elif "postback" in messaging:
                payload = messaging["postback"].get("payload", "")
                if payload:
                    events.append({
                        "sender_id": sender_id,
                        "text": payload,
                        "mid": None,
                        "timestamp": timestamp,
                    })

    return events
