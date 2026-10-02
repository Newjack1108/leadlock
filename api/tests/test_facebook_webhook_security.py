"""Facebook webhook signature verification."""
from app.facebook_webhook_security import compute_facebook_signature, verify_facebook_signature


def test_facebook_signature_round_trip():
    body = b'{"object":"page"}'
    secret = "app-secret"
    sig = compute_facebook_signature(body, secret)
    assert verify_facebook_signature(body, sig, app_secret=secret)
    assert not verify_facebook_signature(body, "sha256=deadbeef", app_secret=secret)
    assert not verify_facebook_signature(body, sig, app_secret="other")
    assert not verify_facebook_signature(body, None, app_secret=secret)
