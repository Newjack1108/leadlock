"""
Facebook Messenger service: send messages, fetch user profile, parse webhook payloads.
"""
import os
import sys
import httpx
from typing import Optional, List, Any
from datetime import datetime

GRAPH_API_BASE = "https://graph.facebook.com/v21.0"
LEAD_ADS_GRAPH_API_BASE = "https://graph.facebook.com/v26.0"


def get_page_access_token() -> Optional[str]:
    """Return the Messenger Page Access Token from environment."""
    return os.getenv("FACEBOOK_PAGE_ACCESS_TOKEN")


def get_leads_access_token() -> Optional[str]:
    """Return the Lead Ads access token, preferring FACEBOOK_LEADS_ACCESS_TOKEN.

    Falls back to FACEBOOK_PAGE_ACCESS_TOKEN for backward-compatible rollout.
    Messenger must continue using get_page_access_token() / FACEBOOK_PAGE_ACCESS_TOKEN.
    """
    token = os.getenv("FACEBOOK_LEADS_ACCESS_TOKEN")
    if token:
        return token

    fallback = os.getenv("FACEBOOK_PAGE_ACCESS_TOKEN")
    if fallback:
        print(
            "WARNING: FACEBOOK_LEADS_ACCESS_TOKEN not set; "
            "using legacy FACEBOOK_PAGE_ACCESS_TOKEN for Lead Ads",
            file=sys.stderr,
            flush=True,
        )
    return fallback


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


def _optional_graph_str(value: Any) -> Optional[str]:
    """Return a stripped string, or None if the Graph field is missing/blank."""
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def fetch_leadgen_lead(
    leadgen_id: str,
    page_access_token: Optional[str] = None,
) -> tuple[bool, Optional[dict], Optional[str]]:
    """
    Fetch lead form data from Graph API by leadgen_id.

    Returns (success, payload, error_message).
    payload is:
      {"field_map": dict, "ad_name": Optional[str], "ad_id": Optional[str]}
    field_map is form answers only. ad_name/ad_id are optional advert metadata
    from the same lead object (not a second Marketing API call). Test leads
    often omit them; that is not an error.
    """
    token = page_access_token or get_leads_access_token()
    if not token:
        return False, None, "Facebook Lead Ads not configured (missing FACEBOOK_LEADS_ACCESS_TOKEN)"

    url = f"{LEAD_ADS_GRAPH_API_BASE}/{leadgen_id}"
    params = {
        "fields": "id,created_time,field_data,ad_id,ad_name",
        "access_token": token,
    }

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
            payload = {
                "field_map": field_map,
                "ad_name": _optional_graph_str(data.get("ad_name")),
                "ad_id": _optional_graph_str(data.get("ad_id")),
            }
            return True, payload, None
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
