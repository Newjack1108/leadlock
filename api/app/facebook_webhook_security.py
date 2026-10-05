"""Verify Meta (Facebook) webhook request signatures."""
from __future__ import annotations

import hashlib
import hmac
import os
from typing import Optional

# Channel keys used by webhook routers when selecting App Secrets.
FACEBOOK_CHANNEL_MESSENGER = "messenger"
FACEBOOK_CHANNEL_LEADGEN = "leadgen"

_CHANNEL_SPECIFIC_ENV = {
    FACEBOOK_CHANNEL_MESSENGER: "FACEBOOK_MESSENGER_APP_SECRET",
    FACEBOOK_CHANNEL_LEADGEN: "FACEBOOK_LEADS_APP_SECRET",
}


def facebook_app_secret() -> Optional[str]:
    return (os.getenv("FACEBOOK_APP_SECRET") or "").strip() or None


def facebook_secrets_for_channel(channel: str) -> list[str]:
    """Return unique App Secrets to try for a webhook channel.

    Prefer the channel-specific secret when set, and always also accept the
    shared FACEBOOK_APP_SECRET so a single-app setup keeps working.
    """
    secrets: list[str] = []
    env_name = _CHANNEL_SPECIFIC_ENV.get(channel)
    if env_name:
        specific = (os.getenv(env_name) or "").strip()
        if specific:
            secrets.append(specific)
    shared = facebook_app_secret()
    if shared and shared not in secrets:
        secrets.append(shared)
    return secrets


def compute_facebook_signature(raw_body: bytes, app_secret: str) -> str:
    digest = hmac.new(
        app_secret.encode("utf-8"),
        msg=raw_body,
        digestmod=hashlib.sha256,
    ).hexdigest()
    return f"sha256={digest}"


def verify_facebook_signature(
    raw_body: bytes,
    signature_header: Optional[str],
    app_secret: Optional[str] = None,
    channel: Optional[str] = None,
) -> bool:
    """Verify X-Hub-Signature-256 against one or more App Secrets.

    When ``app_secret`` is passed, only that secret is checked (tests).
    Otherwise ``channel`` selects channel-specific + shared secrets.
    """
    if app_secret is not None:
        secrets = [app_secret] if app_secret.strip() else []
    elif channel:
        secrets = facebook_secrets_for_channel(channel)
    else:
        shared = facebook_app_secret()
        secrets = [shared] if shared else []

    if not secrets:
        return False
    if not signature_header:
        return False

    provided = signature_header.strip()
    matched = False
    for secret in secrets:
        expected = compute_facebook_signature(raw_body, secret)
        # Always evaluate every secret so timing does not reveal which matched.
        matched = hmac.compare_digest(provided, expected) or matched
    return matched
