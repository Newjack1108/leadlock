"""Facebook webhook signature verification."""
import os

from app.facebook_webhook_security import (
    FACEBOOK_CHANNEL_LEADGEN,
    FACEBOOK_CHANNEL_MESSENGER,
    compute_facebook_signature,
    facebook_secrets_for_channel,
    verify_facebook_signature,
)


def test_facebook_signature_round_trip():
    body = b'{"object":"page"}'
    secret = "app-secret"
    sig = compute_facebook_signature(body, secret)
    assert verify_facebook_signature(body, sig, app_secret=secret)
    assert not verify_facebook_signature(body, "sha256=deadbeef", app_secret=secret)
    assert not verify_facebook_signature(body, sig, app_secret="other")
    assert not verify_facebook_signature(body, None, app_secret=secret)


def test_channel_secrets_prefer_specific_then_shared(monkeypatch):
    monkeypatch.setenv("FACEBOOK_APP_SECRET", "shared-secret")
    monkeypatch.setenv("FACEBOOK_LEADS_APP_SECRET", "leads-secret")
    monkeypatch.delenv("FACEBOOK_MESSENGER_APP_SECRET", raising=False)

    assert facebook_secrets_for_channel(FACEBOOK_CHANNEL_LEADGEN) == [
        "leads-secret",
        "shared-secret",
    ]
    assert facebook_secrets_for_channel(FACEBOOK_CHANNEL_MESSENGER) == ["shared-secret"]


def test_verify_accepts_channel_specific_or_shared_secret(monkeypatch):
    body = b'{"object":"page","entry":[]}'
    monkeypatch.setenv("FACEBOOK_APP_SECRET", "shared-secret")
    monkeypatch.setenv("FACEBOOK_MESSENGER_APP_SECRET", "messenger-secret")
    monkeypatch.setenv("FACEBOOK_LEADS_APP_SECRET", "leads-secret")

    messenger_sig = compute_facebook_signature(body, "messenger-secret")
    leads_sig = compute_facebook_signature(body, "leads-secret")
    shared_sig = compute_facebook_signature(body, "shared-secret")

    assert verify_facebook_signature(
        body, messenger_sig, channel=FACEBOOK_CHANNEL_MESSENGER
    )
    assert verify_facebook_signature(body, shared_sig, channel=FACEBOOK_CHANNEL_MESSENGER)
    assert not verify_facebook_signature(
        body, leads_sig, channel=FACEBOOK_CHANNEL_MESSENGER
    )

    assert verify_facebook_signature(body, leads_sig, channel=FACEBOOK_CHANNEL_LEADGEN)
    assert verify_facebook_signature(body, shared_sig, channel=FACEBOOK_CHANNEL_LEADGEN)
    assert not verify_facebook_signature(
        body, messenger_sig, channel=FACEBOOK_CHANNEL_LEADGEN
    )


def test_verify_fails_when_no_secrets_configured(monkeypatch):
    for key in (
        "FACEBOOK_APP_SECRET",
        "FACEBOOK_MESSENGER_APP_SECRET",
        "FACEBOOK_LEADS_APP_SECRET",
    ):
        monkeypatch.delenv(key, raising=False)
    body = b"{}"
    sig = compute_facebook_signature(body, "anything")
    assert not verify_facebook_signature(body, sig, channel=FACEBOOK_CHANNEL_LEADGEN)
    assert facebook_secrets_for_channel(FACEBOOK_CHANNEL_LEADGEN) == []
