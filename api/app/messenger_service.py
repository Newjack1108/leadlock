"""
Facebook Messenger service: send messages, fetch user profile, parse webhook payloads.
"""
import json
import os
import sys
import httpx
from typing import Optional, List, Any, Dict

GRAPH_API_BASE = "https://graph.facebook.com/v21.0"
LEAD_ADS_GRAPH_API_BASE = "https://graph.facebook.com/v26.0"
LEADGEN_FIELDS_WITH_ADVERT = "id,created_time,field_data,ad_id,ad_name"
LEADGEN_FIELDS_CORE = "id,created_time,field_data"


def get_page_access_token() -> Optional[str]:
    """Return the default Messenger Page Access Token from environment."""
    return os.getenv("FACEBOOK_PAGE_ACCESS_TOKEN")


def _parse_messenger_page_token_map() -> Dict[str, str]:
    """Parse FACEBOOK_MESSENGER_PAGE_TOKENS JSON map of page_id -> page access token."""
    raw = (os.getenv("FACEBOOK_MESSENGER_PAGE_TOKENS") or "").strip()
    if not raw:
        return {}
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        print(
            "WARNING: FACEBOOK_MESSENGER_PAGE_TOKENS is not valid JSON; ignoring map",
            file=sys.stderr,
            flush=True,
        )
        return {}
    if not isinstance(data, dict):
        print(
            "WARNING: FACEBOOK_MESSENGER_PAGE_TOKENS must be a JSON object; ignoring map",
            file=sys.stderr,
            flush=True,
        )
        return {}
    out: Dict[str, str] = {}
    for key, value in data.items():
        page_id = str(key).strip()
        token = str(value).strip() if value is not None else ""
        if page_id and token:
            out[page_id] = token
    return out


def get_messenger_page_token(page_id: Optional[str] = None) -> Optional[str]:
    """Return the Page access token for a Messenger Page ID.

    Prefers FACEBOOK_MESSENGER_PAGE_TOKENS[page_id] when page_id is set.
    Falls back to FACEBOOK_PAGE_ACCESS_TOKEN for single-Page setups and legacy rows
    without messenger_page_id.
    """
    page_key = str(page_id).strip() if page_id is not None else ""
    if page_key:
        mapped = _parse_messenger_page_token_map().get(page_key)
        if mapped:
            return mapped
    return get_page_access_token()


def get_leads_access_token() -> Optional[str]:
    """Return the Lead Ads access token, preferring FACEBOOK_LEADS_ACCESS_TOKEN.

    Falls back to FACEBOOK_PAGE_ACCESS_TOKEN for backward-compatible rollout.
    Messenger must continue using get_page_access_token() / get_messenger_page_token().
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
    page_id: Optional[str] = None,
) -> tuple[bool, Optional[str], Optional[str]]:
    """
    Send a text message via Facebook Graph API.
    Returns (success, message_id, error_message).
    """
    token = page_access_token or get_messenger_page_token(page_id)
    if not token:
        if page_id:
            return (
                False,
                None,
                (
                    f"Facebook Messenger not configured for page_id={page_id} "
                    "(set FACEBOOK_MESSENGER_PAGE_TOKENS or FACEBOOK_PAGE_ACCESS_TOKEN)"
                ),
            )
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
    page_id: Optional[str] = None,
) -> tuple[bool, Optional[str], Optional[str], Optional[str], Optional[str]]:
    """
    Fetch user profile (first_name, last_name, optional phone) from Graph API.
    Phone may require user_phone_number permission and might not be returned.
    Returns (success, first_name, last_name, phone, error_message).
    """
    token = page_access_token or get_messenger_page_token(page_id)
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


def _join_leadgen_field_values(values: Any) -> str:
    """Join all Facebook field_data values so multi-part answers are not truncated.

    Meta may return several entries in `values` (e.g. building type + size).
    Historically only values[0] was kept, which dropped later parts.
    """
    if values is None:
        return ""
    if not isinstance(values, (list, tuple)):
        text = str(values).strip()
        return text
    parts: list[str] = []
    for item in values:
        if item is None:
            continue
        text = str(item).strip()
        if text:
            parts.append(text)
    return ", ".join(parts)


def _graph_get_leadgen(client: httpx.Client, leadgen_id: str, token: str, fields: str) -> tuple[Optional[dict], Optional[str]]:
    """GET a Leadgen object. Returns (json, error_message). Never logs the token."""
    url = f"{LEAD_ADS_GRAPH_API_BASE}/{leadgen_id}"
    params = {"fields": fields, "access_token": token}
    resp = client.get(url, params=params)
    data = resp.json()
    if resp.status_code != 200:
        error_msg = data.get("error", {}).get("message", resp.text)
        return None, error_msg
    return data, None


def fetch_ad_name(
    ad_id: str,
    page_access_token: Optional[str] = None,
) -> tuple[Optional[str], Optional[str]]:
    """Fetch an ad's name from Graph API by ad_id (Lead Ads v26.0).

    Returns (ad_name, error_message). Missing/blank name is not fatal for lead creation.
    Never logs the access token.
    """
    ident = _optional_graph_str(ad_id)
    if not ident:
        return None, "missing ad_id"

    token = page_access_token or get_leads_access_token()
    if not token:
        return None, "Facebook Lead Ads not configured (missing FACEBOOK_LEADS_ACCESS_TOKEN)"

    url = f"{LEAD_ADS_GRAPH_API_BASE}/{ident}"
    params = {"fields": "name", "access_token": token}
    try:
        with httpx.Client(timeout=10.0) as client:
            resp = client.get(url, params=params)
            data = resp.json()
            if resp.status_code != 200:
                error_msg = data.get("error", {}).get("message", resp.text)
                return None, error_msg
            return _optional_graph_str(data.get("name")), None
    except Exception as e:
        return None, str(e)


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

    If Meta rejects ad_id/ad_name (common without ads_management), retry the
    same leadgen request without those fields so the lead is still created.
    """
    token = page_access_token or get_leads_access_token()
    if not token:
        return False, None, "Facebook Lead Ads not configured (missing FACEBOOK_LEADS_ACCESS_TOKEN)"

    try:
        with httpx.Client(timeout=10.0) as client:
            data, err = _graph_get_leadgen(client, leadgen_id, token, LEADGEN_FIELDS_WITH_ADVERT)
            if data is None:
                print(
                    "Facebook Lead Ads: advert metadata unavailable; "
                    f"retrying without ad_id/ad_name leadgen_id={leadgen_id} error={err}",
                    file=sys.stderr,
                    flush=True,
                )
                data, err = _graph_get_leadgen(client, leadgen_id, token, LEADGEN_FIELDS_CORE)
            if data is None:
                return False, None, err
            field_data = data.get("field_data") or []
            field_map: dict[str, str] = {}
            for item in field_data:
                name = item.get("name")
                values = item.get("values") or []
                if name is None:
                    continue
                joined = _join_leadgen_field_values(values)
                if joined:
                    field_map[name] = joined
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
    Returns a list of event dicts, each with: sender_id (PSID), text, mid,
    timestamp (optional), page_id (from entry.id when present).
    Handles 'message' and 'postback' (postback payload as text).
    """
    events = []
    entries = body.get("entry", [])
    for entry in entries:
        page_id = _optional_graph_str(entry.get("id"))
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
                        "page_id": page_id,
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
                        "page_id": page_id,
                    })

    return events
