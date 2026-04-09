"""
Email service for sending and receiving emails via Microsoft Graph, Resend, or SMTP.
When CLIENT_ID, CLIENT_SECRET, TENANT_ID, and MSGRAPH_FROM_EMAIL are set, uses Microsoft Graph.
When RESEND_API_KEY is set, uses Resend (HTTPS - works on Railway).
Otherwise SMTP is used.
"""
import base64
import html as html_module
import re
import smtplib
import imaplib
import email
from urllib.parse import quote
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
from email.header import decode_header
from typing import Optional, List, Dict, Tuple
from datetime import datetime, timedelta
import os
import json
import uuid
from dotenv import load_dotenv

load_dotenv()

# Shown in the recipient's mail client as the From display name when env/user fields do not override it.
DEFAULT_OUTBOUND_FROM_NAME = "Cheshire Stables CSGB Group"

# Green email header bar (left). Override with EMAIL_HEADER_BRAND in the environment.
DEFAULT_EMAIL_HEADER_BRAND = "Cheshire Stables - part of the CSGB Group"

# Green pill style for tracked links (quote/order view + website tracking) — matches branded quote sends.
EMAIL_TRACKED_LINK_STYLE = (
    "color:#15803d;font-weight:bold;background-color:#dcfce7;"
    "padding:4px 8px;border-radius:4px;text-decoration:underline;"
)

_imap_missing_logged = False


def _decode_mime_header(value: Optional[str]) -> str:
    """Decode RFC 2047 encoded Subject and similar headers."""
    if not value:
        return ""
    parts = decode_header(value)
    out: List[str] = []
    for text, charset in parts:
        if isinstance(text, bytes):
            out.append(text.decode(charset or "utf-8", errors="replace"))
        else:
            out.append(text or "")
    return "".join(out)


def _html_to_plain(html: str) -> str:
    """Convert HTML to plain text by stripping tags and normalizing whitespace."""
    if not html or not html.strip():
        return ""
    text = re.sub(r"<[^>]+>", " ", html)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _build_website_tracking_link_html(customer_number: Optional[str]) -> str:
    """Return HTML with visit-tracking links, or empty string if no customer_number."""
    if not customer_number or not customer_number.strip():
        return ""
    from app.constants import TRACKING_WEBSITE_BASE_URLS
    token = quote(customer_number.strip(), safe="")
    link_style = EMAIL_TRACKED_LINK_STYLE
    links = [
        f'<a href="{base}?ltk={token}" style="{link_style}">{label}</a>'
        for base, label in TRACKING_WEBSITE_BASE_URLS
    ]
    return '<p style="margin-top:1em;">Visit us: ' + " | ".join(links) + '</p>'


def _build_website_tracking_link_text(customer_number: Optional[str]) -> str:
    """Return plain-text version of visit-tracking links."""
    if not customer_number or not customer_number.strip():
        return ""
    from app.constants import TRACKING_WEBSITE_BASE_URLS
    token = quote(customer_number.strip(), safe="")
    urls = [f"{base}?ltk={token}" for base, _ in TRACKING_WEBSITE_BASE_URLS]
    return "\n\nVisit us: " + " | ".join(urls)


def _append_signature_and_disclaimer(
    body_html: Optional[str],
    body_text: Optional[str],
    user_id: Optional[int],
) -> Tuple[Optional[str], Optional[str]]:
    """
    Append signature and company disclaimer to email body.
    Order: [body] -> [signature] -> [disclaimer]

    With user_id: uses that user's email_signature plus company email_disclaimer.
    Without user_id: uses company default_email_signature plus email_disclaimer.
    """
    try:
        from sqlmodel import Session, select
        from app.database import engine
        from app.models import User, CompanySettings

        with Session(engine) as session:
            company = session.exec(select(CompanySettings).limit(1)).first()
            disclaimer = (getattr(company, "email_disclaimer", None) or "").strip() if company else ""

            if user_id:
                user = session.exec(select(User).where(User.id == user_id)).first()
                signature = (user.email_signature or "").strip() if user else ""
            else:
                signature = (getattr(company, "default_email_signature", None) or "").strip() if company else ""

            if not signature and not disclaimer:
                return body_html, body_text

            footer_html_parts = []
            footer_text_parts = []

            if signature:
                footer_html_parts.append(signature)
                footer_text_parts.append(_html_to_plain(signature))
            if disclaimer:
                footer_html_parts.append(disclaimer)
                footer_text_parts.append(_html_to_plain(disclaimer))

            if not footer_html_parts:
                return body_html, body_text

            footer_html = "<br><br>".join(footer_html_parts)
            footer_text = "\n\n".join(footer_text_parts)

            sep_html = '<br><br>' if (body_html or "").strip() else ''
            out_html = (body_html or "") + sep_html + footer_html

            if body_text is not None:
                sep_text = '\n\n' if body_text.strip() else ''
                out_text = body_text + sep_text + footer_text
            else:
                out_text = None

            return out_html or None, out_text

    except Exception as e:
        import sys
        print(f"Error appending signature/disclaimer: {e}", file=sys.stderr, flush=True)
        return body_html, body_text


def _sanitize_email_brand_primary(color: Optional[str]) -> str:
    """Allow only #RGB or #RRGGBB for CSS; default matches branded quote emails."""
    default = "#286932"
    if not color or not isinstance(color, str):
        return default
    c = color.strip()
    if re.match(r"^#[0-9A-Fa-f]{3}$", c) or re.match(r"^#[0-9A-Fa-f]{6}$", c):
        return c
    return default


def _get_email_brand_primary() -> str:
    return _sanitize_email_brand_primary((os.getenv("EMAIL_BRAND_PRIMARY") or "").strip() or None)


def _build_email_highlight_box_html(
    primary: str,
    bold_label: str,
    summary: str,
    hint: str,
) -> str:
    """Green left-border callout (attachments / quotation) — table-based for email clients."""
    prim = html_module.escape(primary)
    bl = html_module.escape(bold_label)
    summ = html_module.escape(summary)
    hint_e = html_module.escape(hint)
    return (
        f'<table width="100%" cellpadding="0" cellspacing="0" role="presentation" style="margin:0 0 18px 0;">'
        f'<tr><td style="border:1px solid #d7e6db; background-color:#f3f8f4; border-left:5px solid {prim}; '
        f'padding:12px 14px; border-radius:8px;">'
        f'<div style="font-size:13px; color:#1a1a1a;">'
        f'<strong style="color:{prim};">{bl}:</strong> {summ}'
        f'<span style="color:#555;">&nbsp;&nbsp;|&nbsp;&nbsp;</span>'
        f'<span style="color:#555;">{hint_e}</span>'
        f"</div></td></tr></table>"
    )


def _compose_email_highlight_fragment(
    primary: str,
    attachments: Optional[List[Dict]],
    include_quote_highlight: bool,
) -> str:
    """Highlight box for quote sends or any message with file attachments."""
    hint_files = "If you can't see the attachment, reply to this email and we'll resend it."
    hint_quote = "If you can't see the attachment or open the link, reply to this email and we'll resend it."

    if include_quote_highlight:
        return _build_email_highlight_box_html(
            primary,
            "Quotation",
            "Secure link below — view, print, or download PDF",
            hint_quote,
        )

    if attachments:
        names = []
        for a in attachments:
            if not a:
                continue
            fn = a.get("filename") or "attachment"
            names.append(fn)
        if names:
            summary = ", ".join(names)
            return _build_email_highlight_box_html(primary, "Attached", summary, hint_files)

    return ""


def _append_highlight_plain_text(
    body_text: Optional[str],
    attachments: Optional[List[Dict]],
    include_quote_highlight: bool,
) -> Optional[str]:
    if body_text is None:
        return None
    if include_quote_highlight:
        return (
            body_text
            + "\n\nQuotation: Secure link below — view, print, or download PDF. "
            "If you can't access it, reply to this email and we'll resend it.\n"
        )
    if attachments:
        names = []
        for a in attachments:
            if not a:
                continue
            names.append(a.get("filename") or "attachment")
        if names:
            listed = ", ".join(names)
            return (
                body_text
                + f"\n\nAttached: {listed}. If you can't see the attachment, reply to this email and we'll resend it.\n"
            )
    return body_text


def _looks_like_full_html_email_document(body_html: str) -> bool:
    """Avoid double-wrapping when the body is already a complete HTML document."""
    head = body_html.strip()[:1200].lower()
    return "<html" in head or head.startswith("<!doctype")


def _website_href_for_email(url: str) -> str:
    u = (url or "").strip()
    if not u:
        return ""
    if u.lower().startswith(("http://", "https://")):
        return u
    return "https://" + u


def _wrap_outbound_email_html(
    inner_html: str,
    header_brand: str,
    footer_company: str,
    header_tagline: str,
    phone: str,
    website: str,
    primary: str,
) -> str:
    """
    System-wide HTML email shell: card layout, branded header/footer (table-based for clients).
    header_brand: main line in the green header (and HTML title).
    footer_company: bold company line in the footer (registered / trading from settings).
    """
    header_esc = html_module.escape(header_brand.strip()) if header_brand and header_brand.strip() else ""
    footer_esc = html_module.escape(footer_company.strip()) if footer_company and footer_company.strip() else ""
    prim = html_module.escape(primary)
    tag_html = html_module.escape(header_tagline.strip()) if header_tagline and header_tagline.strip() else ""
    phone_html = html_module.escape(phone.strip()) if phone and phone.strip() else ""
    site_disp = (website or "").strip()
    site_href = _website_href_for_email(site_disp)
    site_html = ""
    if site_disp:
        site_html = (
            f'<a href="{html_module.escape(site_href)}" style="color:#555;text-decoration:none;">'
            f"{html_module.escape(site_disp)}</a>"
        )

    footer_bits: List[str] = [
        f'<span style="color:{prim};font-weight:700;">{footer_esc}</span>',
    ]
    sep = '<span style="color:#9aa7a0;">&nbsp;&nbsp;|&nbsp;&nbsp;</span>'
    if phone_html:
        footer_bits.append(f"<span>{phone_html}</span>")
    if site_html:
        footer_bits.append(site_html)
    footer_inner = sep.join(footer_bits)

    if tag_html:
        right_header = (
            f'<td align="right" style="color:#e7f2ea; font-size:12px;">{tag_html}</td>'
        )
    else:
        right_header = '<td align="right" style="color:#e7f2ea; font-size:12px;">&nbsp;</td>'

    return f"""<!DOCTYPE html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>{header_esc}</title>
  </head>
  <body style="margin:0; padding:0; background-color:#f4f6f4; font-family: Arial, Helvetica, sans-serif; color:#111;">
    <table width="100%" cellpadding="0" cellspacing="0" role="presentation" style="background-color:#f4f6f4;">
      <tr>
        <td align="center" style="padding:28px 14px;">
          <table width="600" cellpadding="0" cellspacing="0" role="presentation" style="width:600px; max-width:600px; background-color:#ffffff; border-radius:10px; overflow:hidden;">
            <tr>
              <td style="background-color:{prim}; padding:18px 22px;">
                <table width="100%" cellpadding="0" cellspacing="0" role="presentation">
                  <tr>
                    <td style="color:#ffffff; font-size:16px; font-weight:700; letter-spacing:0.2px; text-transform:uppercase;">{header_esc}</td>
                    {right_header}
                  </tr>
                </table>
              </td>
            </tr>
            <tr>
              <td style="padding:24px 22px; font-size:14px; line-height:1.65;">
                {inner_html}
              </td>
            </tr>
            <tr>
              <td style="background-color:#f1f5f2; padding:14px 22px; font-size:12px; color:#555; line-height:1.5;">
                {footer_inner}
              </td>
            </tr>
          </table>
        </td>
      </tr>
    </table>
  </body>
</html>"""


def _apply_system_email_layout(
    body_html: Optional[str],
    header_tagline: Optional[str] = None,
) -> Optional[str]:
    """Wrap HTML fragments in the standard system email shell using company settings."""
    if not body_html or not body_html.strip():
        return body_html
    if _looks_like_full_html_email_document(body_html):
        return body_html
    try:
        from sqlmodel import Session, select
        from app.database import engine
        from app.models import CompanySettings

        with Session(engine) as session:
            company = session.exec(select(CompanySettings).limit(1)).first()
        if not company:
            return body_html
        header_brand = (os.getenv("EMAIL_HEADER_BRAND") or DEFAULT_EMAIL_HEADER_BRAND).strip()
        footer_company = (
            company.company_name or company.trading_name or DEFAULT_OUTBOUND_FROM_NAME
        ).strip()
        phone = (company.phone or "").strip()
        website = (company.website or "").strip()
        primary = _get_email_brand_primary()
        tag = (header_tagline or "").strip()
        return _wrap_outbound_email_html(
            body_html,
            header_brand=header_brand,
            footer_company=footer_company,
            header_tagline=tag,
            phone=phone,
            website=website,
            primary=primary,
        )
    except Exception as e:
        import sys
        print(f"Error applying system email layout: {e}", file=sys.stderr, flush=True)
        return body_html


def get_smtp_config(user_id: Optional[int] = None) -> Dict:
    """Get SMTP configuration from user settings or environment variables."""
    # Try user's database settings first
    if user_id:
        try:
            from sqlmodel import Session, select
            from app.database import engine
            from app.models import User
            
            with Session(engine) as session:
                statement = select(User).where(User.id == user_id)
                user = session.exec(statement).first()
                
                if user:
                    # Check if user has smtp_host configured (using getattr to handle missing attributes)
                    smtp_host = getattr(user, 'smtp_host', None)
                    smtp_user = getattr(user, 'smtp_user', None)
                    smtp_password = getattr(user, 'smtp_password', None)
                    
                    # Only use user's config if they have host, user, and password configured
                    if smtp_host and smtp_user and smtp_password:
                        return {
                            "host": smtp_host,
                            "port": getattr(user, 'smtp_port', None) or 587,
                            "user": smtp_user,
                            "password": smtp_password,
                            "use_tls": getattr(user, 'smtp_use_tls', True),
                            "from_email": getattr(user, 'smtp_from_email', None) or smtp_user or user.email,
                            "from_name": getattr(user, 'smtp_from_name', None) or user.full_name or DEFAULT_OUTBOUND_FROM_NAME,
                            "test_mode": getattr(user, 'email_test_mode', False)
                        }
                    else:
                        # Return test_mode even if SMTP not fully configured
                        return {
                            "host": os.getenv("SMTP_HOST", "smtp.gmail.com"),
                            "port": int(os.getenv("SMTP_PORT", "587")),
                            "user": os.getenv("SMTP_USER"),
                            "password": os.getenv("SMTP_PASSWORD"),
                            "use_tls": os.getenv("SMTP_USE_TLS", "true").lower() == "true",
                            "from_email": os.getenv("SMTP_FROM_EMAIL", os.getenv("SMTP_USER")),
                            "from_name": os.getenv("SMTP_FROM_NAME", DEFAULT_OUTBOUND_FROM_NAME),
                            "test_mode": getattr(user, 'email_test_mode', False)
                        }
        except Exception as e:
            # Log error but fall back to env vars
            import sys
            print(f"Error fetching user SMTP config: {e}", file=sys.stderr, flush=True)
    
    # Fallback to environment variables
    return {
        "host": os.getenv("SMTP_HOST", "smtp.gmail.com"),
        "port": int(os.getenv("SMTP_PORT", "587")),
        "user": os.getenv("SMTP_USER"),
        "password": os.getenv("SMTP_PASSWORD"),
        "use_tls": os.getenv("SMTP_USE_TLS", "true").lower() == "true",
        "from_email": os.getenv("SMTP_FROM_EMAIL", os.getenv("SMTP_USER")),
        "from_name": os.getenv("SMTP_FROM_NAME", DEFAULT_OUTBOUND_FROM_NAME),
        "test_mode": os.getenv("EMAIL_TEST_MODE", "false").lower() == "true"
    }


def get_imap_config(user_id: Optional[int] = None) -> Dict:
    """Get IMAP configuration from user settings or environment variables."""
    # Try user's database settings first
    if user_id:
        try:
            from sqlmodel import Session, select
            from app.database import engine
            from app.models import User
            
            with Session(engine) as session:
                statement = select(User).where(User.id == user_id)
                user = session.exec(statement).first()
                
                if user:
                    # Check if user has imap_host configured (using getattr to handle missing attributes)
                    imap_host = getattr(user, 'imap_host', None)
                    imap_user = getattr(user, 'imap_user', None)
                    imap_password = getattr(user, 'imap_password', None)
                    
                    # Only use user's config if they have host, user, and password configured
                    if imap_host and imap_user and imap_password:
                        return {
                            "host": imap_host,
                            "port": getattr(user, 'imap_port', None) or 993,
                            "user": imap_user,
                            "password": imap_password,
                            "use_ssl": getattr(user, 'imap_use_ssl', True)
                        }
        except Exception as e:
            # Log error but fall back to env vars
            import sys
            print(f"Error fetching user IMAP config: {e}", file=sys.stderr, flush=True)
    
    # Fallback to environment variables
    return {
        "host": os.getenv("IMAP_HOST", "imap.gmail.com"),
        "port": int(os.getenv("IMAP_PORT", "993")),
        "user": os.getenv("IMAP_USER"),
        "password": os.getenv("IMAP_PASSWORD"),
        "use_ssl": os.getenv("IMAP_USE_SSL", "true").lower() == "true"
    }


def get_imap_config_for_poll() -> Dict:
    """
    IMAP for the API background poller: Railway IMAP_* env vars first,
    else the first user with full IMAP saved in My Settings.
    """
    host = (os.getenv("IMAP_HOST") or "").strip()
    user = (os.getenv("IMAP_USER") or "").strip()
    password = (os.getenv("IMAP_PASSWORD") or "").strip()
    if host and user and password:
        return {
            "host": host,
            "port": int(os.getenv("IMAP_PORT", "993")),
            "user": user,
            "password": password,
            "use_ssl": os.getenv("IMAP_USE_SSL", "true").lower() == "true",
        }
    try:
        from sqlmodel import Session, select
        from app.database import engine
        from app.models import User

        with Session(engine) as session:
            users = session.exec(select(User)).all()
            for u in users:
                h = getattr(u, "imap_host", None)
                usr = getattr(u, "imap_user", None)
                pwd = getattr(u, "imap_password", None)
                if h and usr and pwd:
                    return {
                        "host": h,
                        "port": getattr(u, "imap_port", None) or 993,
                        "user": usr,
                        "password": pwd,
                        "use_ssl": getattr(u, "imap_use_ssl", True),
                    }
    except Exception as e:
        import sys
        print(f"IMAP poll: could not load user IMAP from database: {e}", file=sys.stderr, flush=True)
    return get_imap_config()


def generate_message_id() -> str:
    """Generate a unique message ID for emails."""
    domain = (
        os.getenv("MSGRAPH_FROM_EMAIL")
        or os.getenv("SMTP_FROM_EMAIL")
        or "leadlock.local"
    )
    domain = (domain or "leadlock.local").split("@")[-1]
    return f"<{uuid.uuid4()}@{domain}>"


def _send_via_resend(
    to_email: str,
    subject: str,
    body_html: Optional[str],
    body_text: Optional[str],
    from_email: str,
    from_name: str,
    cc: Optional[str],
    bcc: Optional[str],
    attachments: Optional[List[Dict]],
    message_id: str,
    in_reply_to: Optional[str],
    references: Optional[str],
) -> Tuple[bool, Optional[str], Optional[str]]:
    """Send email via Resend API (HTTPS - works when SMTP is blocked)."""
    try:
        import resend
        api_key = os.getenv("RESEND_API_KEY", "").strip()
        if not api_key:
            return False, None, "RESEND_API_KEY not configured"
        resend.api_key = api_key

        from_str = f"{from_name} <{from_email}>" if from_name else from_email
        params = {
            "from": from_str,
            "to": [e.strip() for e in to_email.split(",") if e.strip()],
            "subject": subject,
            "html": body_html or body_text or "",
        }
        if body_text and not body_html:
            params["text"] = body_text
        if cc:
            params["cc"] = [e.strip() for e in cc.split(",") if e.strip()]
        if bcc:
            params["bcc"] = [e.strip() for e in bcc.split(",") if e.strip()]
        params["headers"] = {"Message-ID": message_id}
        if in_reply_to:
            params["headers"]["In-Reply-To"] = in_reply_to
        if references:
            params["headers"]["References"] = references
        if attachments:
            params["attachments"] = [
                {"filename": a.get("filename", "attachment"), "content": base64.b64encode(a["content"]).decode("ascii")}
                for a in attachments
            ]

        result = resend.Emails.send(params)
        rid = result.get("id") if isinstance(result, dict) else getattr(result, "id", None)
        if result and rid:
            return True, message_id, None
        return False, None, str(result) if result else "Unknown Resend error"
    except Exception as e:
        return False, None, str(e)


def _is_graph_configured() -> bool:
    """Check if Microsoft Graph credentials are fully configured."""
    return bool(
        os.getenv("CLIENT_ID", "").strip()
        and os.getenv("CLIENT_SECRET", "").strip()
        and os.getenv("TENANT_ID", "").strip()
        and os.getenv("MSGRAPH_FROM_EMAIL", "").strip()
    )


def _graph_acquire_app_token() -> Tuple[Optional[str], Optional[str]]:
    """
    Client-credentials token for Microsoft Graph (same as send).
    Returns (access_token, error_message).
    """
    try:
        import msal

        client_id = os.getenv("CLIENT_ID", "").strip()
        client_secret = os.getenv("CLIENT_SECRET", "").strip()
        tenant_id = os.getenv("TENANT_ID", "").strip()
        if not all([client_id, client_secret, tenant_id]):
            return None, "CLIENT_ID, CLIENT_SECRET, or TENANT_ID missing"
        app = msal.ConfidentialClientApplication(
            client_id=client_id,
            authority=f"https://login.microsoftonline.com/{tenant_id}",
            client_credential=client_secret,
        )
        result = app.acquire_token_for_client(scopes=["https://graph.microsoft.com/.default"])
        tok = result.get("access_token")
        if tok:
            return tok, None
        err = result.get("error_description") or result.get("error") or "token acquisition failed"
        return None, str(err)
    except Exception as e:
        return None, str(e)


def is_email_configured(user_id: Optional[int] = None) -> bool:
    """Check if any email backend is configured (Graph, Resend, or SMTP)."""
    if _is_graph_configured():
        return True
    if os.getenv("RESEND_API_KEY", "").strip():
        return True
    config = get_smtp_config(user_id)
    return bool(config.get("user") and config.get("password"))


def _send_via_graph(
    to_email: str,
    subject: str,
    body_html: Optional[str],
    body_text: Optional[str],
    from_email: str,
    from_name: str,
    cc: Optional[str],
    bcc: Optional[str],
    attachments: Optional[List[Dict]],
    message_id: str,
    in_reply_to: Optional[str],
    references: Optional[str],
) -> Tuple[bool, Optional[str], Optional[str]]:
    """Send email via Microsoft Graph API (client credentials flow)."""
    try:
        import httpx

        from_address = os.getenv("MSGRAPH_FROM_EMAIL", "").strip()
        if not from_address:
            return False, None, "MSGRAPH_FROM_EMAIL not set"

        access_token, err = _graph_acquire_app_token()
        if not access_token:
            return False, None, err or "Failed to acquire token"

        body_content = body_html or body_text or ""
        body_content_type = "HTML" if body_html else "Text"

        message = {
            "subject": subject,
            "body": {"contentType": body_content_type, "content": body_content},
            "toRecipients": [{"emailAddress": {"address": e.strip()}} for e in to_email.split(",") if e.strip()],
        }
        if cc:
            message["ccRecipients"] = [{"emailAddress": {"address": e.strip()}} for e in cc.split(",") if e.strip()]
        if bcc:
            message["bccRecipients"] = [{"emailAddress": {"address": e.strip()}} for e in bcc.split(",") if e.strip()]

        # Graph only allows custom headers whose names start with x- or X- in internetMessageHeaders;
        # Message-ID, In-Reply-To, References cannot be set here. Exchange assigns Message-ID on send.

        if attachments:
            message["attachments"] = [
                {
                    "@odata.type": "#microsoft.graph.fileAttachment",
                    "name": a.get("filename", "attachment"),
                    "contentType": "application/octet-stream",
                    "contentBytes": base64.b64encode(a["content"]).decode("ascii"),
                }
                for a in attachments
            ]

        url = f"https://graph.microsoft.com/v1.0/users/{from_address}/sendMail"
        resp = httpx.post(
            url,
            json={"message": message},
            headers={"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"},
            timeout=30,
        )

        if resp.status_code == 202:
            return True, message_id, None
        err_body = resp.text
        try:
            err_json = resp.json()
            err_body = err_json.get("error", {}).get("message", err_body)
        except Exception:
            pass
        return False, None, f"Graph API error {resp.status_code}: {err_body}"
    except Exception as e:
        return False, None, str(e)


def _graph_format_address(addr_obj: Optional[dict]) -> str:
    if not addr_obj:
        return ""
    em = addr_obj.get("emailAddress") or {}
    address = em.get("address") or ""
    name = em.get("name") or ""
    if name and address:
        return f"{name} <{address}>"
    return address or ""


def _graph_format_recipient_list(recipients: Optional[List[dict]]) -> str:
    if not recipients:
        return ""
    parts = []
    for r in recipients:
        em = r.get("emailAddress") or {}
        address = em.get("address") or ""
        name = em.get("name") or ""
        if name and address:
            parts.append(f"{name} <{address}>")
        elif address:
            parts.append(address)
    return ", ".join(parts)


def _parse_graph_datetime(s: Optional[str]) -> datetime:
    if not s:
        return datetime.utcnow()
    try:
        s2 = s.replace("Z", "+00:00") if s.endswith("Z") else s
        return datetime.fromisoformat(s2)
    except Exception:
        return datetime.utcnow()


def log_inbound_poll_configuration() -> None:
    """
    Log how inbound email will be polled (no secrets). Call once at API startup.
    """
    import sys

    poll_interval = int(os.getenv("IMAP_POLL_INTERVAL", "300"))
    if _is_graph_configured():
        mb = os.getenv("MSGRAPH_FROM_EMAIL", "").strip()
        mode = (os.getenv("GRAPH_INBOUND_MODE") or "unread").strip().lower()
        print(
            f"Inbound email: Microsoft Graph — mailbox={mb}, GRAPH_INBOUND_MODE={mode}, "
            f"poll_interval={poll_interval}s",
            file=sys.stderr,
            flush=True,
        )
        return
    cfg = get_imap_config_for_poll()
    if cfg.get("user") and cfg.get("password"):
        host = cfg.get("host") or ""
        user = cfg.get("user") or ""
        search = (os.getenv("IMAP_SEARCH_MODE") or "unseen").strip().lower()
        print(
            f"Inbound email: IMAP — host={host} user={user} IMAP_SEARCH_MODE={search} "
            f"poll_interval={poll_interval}s",
            file=sys.stderr,
            flush=True,
        )
        return
    print(
        "Inbound email: not configured — set Microsoft Graph (CLIENT_ID, CLIENT_SECRET, TENANT_ID, "
        "MSGRAPH_FROM_EMAIL) or IMAP_HOST/IMAP_USER/IMAP_PASSWORD (or IMAP under My Settings). "
        "Customer replies will not be imported.",
        file=sys.stderr,
        flush=True,
    )


def _receive_emails_via_graph() -> List[Dict]:
    """
    List inbox messages via Microsoft Graph (OAuth) — works when M365 blocks IMAP basic auth.
    Requires Mail.Read (Application) permission. Marks messages read after listing (same behaviour as IMAP).

    GRAPH_INBOUND_MODE:
      - unread (default): only messages with isRead eq false (same as IMAP UNSEEN).
      - recent: latest GRAPH_INBOUND_TOP messages by date regardless of read state; duplicates skipped in API by message_id.
        Use when replies were opened in Outlook before LeadLock polled.
    """
    import httpx
    import sys

    mailbox = os.getenv("MSGRAPH_FROM_EMAIL", "").strip()
    if not mailbox:
        return []

    access_token, err = _graph_acquire_app_token()
    if not access_token:
        print(f"Graph inbound: token error: {err}", file=sys.stderr, flush=True)
        return []

    user_path = quote(mailbox, safe="")
    top = int(os.getenv("GRAPH_INBOUND_TOP", "50"))
    base_url = f"https://graph.microsoft.com/v1.0/users/{user_path}/mailFolders/inbox/messages"

    headers = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}

    def _fetch(params: dict) -> dict:
        r = httpx.get(base_url, params=params, headers=headers, timeout=30)
        return r

    mode = (os.getenv("GRAPH_INBOUND_MODE") or "unread").strip().lower()
    use_unread_only = mode != "recent"

    params = {
        "$top": str(top),
        "$orderby": "receivedDateTime desc",
        "$select": "id,internetMessageId,subject,from,toRecipients,body,receivedDateTime,isRead",
    }
    if use_unread_only:
        params["$filter"] = "isRead eq false"
    resp = _fetch(params)
    if resp.status_code == 400 and use_unread_only:
        # Some tenants/query combinations reject $filter; retry without filter
        params.pop("$filter", None)
        resp = _fetch(params)

    if resp.status_code == 403:
        print(
            "Graph inbound: 403 Forbidden — add Mail.Read (Application) permission for "
            "this app registration and grant admin consent. See MSGRAPH_EMAIL_SETUP.md",
            file=sys.stderr,
            flush=True,
        )
        return []
    if resp.status_code != 200:
        print(f"Graph inbound: list messages failed {resp.status_code}: {resp.text[:500]}", file=sys.stderr, flush=True)
        return []

    try:
        payload = resp.json()
    except Exception:
        return []

    items = payload.get("value") or []
    out: List[Dict] = []
    graph_ids_to_mark_read: List[str] = []

    for msg in items:
        if use_unread_only and msg.get("isRead") is True:
            continue
        gid = msg.get("id")
        if not gid:
            continue

        mid = msg.get("internetMessageId") or f"<graph-{gid}>"
        fr = _graph_format_address(msg.get("from"))
        to = _graph_format_recipient_list(msg.get("toRecipients"))
        subject = msg.get("subject") or ""
        body = msg.get("body") or {}
        ct = (body.get("contentType") or "").lower()
        content = body.get("content") or ""
        if "html" in ct:
            body_html, body_text = content, None
        else:
            body_html, body_text = None, content

        received_at = _parse_graph_datetime(msg.get("receivedDateTime"))

        out.append({
            "message_id": mid,
            "in_reply_to": None,
            "references": None,
            "from_email": fr,
            "to_email": to,
            "subject": subject,
            "body_html": body_html,
            "body_text": body_text,
            "received_at": received_at,
            "attachments": None,
        })
        graph_ids_to_mark_read.append(gid)

    for gid in graph_ids_to_mark_read:
        try:
            mid_enc = quote(str(gid), safe="")
            patch_url = f"https://graph.microsoft.com/v1.0/users/{user_path}/messages/{mid_enc}"
            pr = httpx.patch(patch_url, json={"isRead": True}, headers=headers, timeout=30)
            if pr.status_code not in (200, 204):
                print(
                    f"Graph inbound: mark read failed {pr.status_code} for {gid}. "
                    "Mail.Read is not enough to update messages — add Mail.ReadWrite (Application) and admin consent.",
                    file=sys.stderr,
                    flush=True,
                )
        except Exception as e:
            print(f"Graph inbound: mark read error {e}", file=sys.stderr, flush=True)

    # If we returned None earlier on 403, fix - I used return None which is wrong type
    return out


def assemble_outbound_email_html(
    body_html: Optional[str],
    body_text: Optional[str],
    user_id: Optional[int],
    customer_number: Optional[str],
    attachments: Optional[List[Dict]],
    include_quote_highlight: bool,
    header_tagline: Optional[str] = None,
) -> Tuple[Optional[str], Optional[str]]:
    """
    Apply the same HTML assembly as outbound sends: tracking, signature/disclaimer,
    attachment highlight, system layout. Does not send mail.
    """
    # Append website visit tracking link before signature (order: body -> tracking link -> signature -> disclaimer)
    if customer_number:
        tracking_html = _build_website_tracking_link_html(customer_number)
        tracking_text = _build_website_tracking_link_text(customer_number)
        if tracking_html:
            sep_html = '<br><br>' if (body_html or "").strip() else ''
            body_html = (body_html or "") + sep_html + tracking_html
        if tracking_text and body_text is not None:
            body_text = body_text + tracking_text

    # Append user signature and company disclaimer to all outgoing emails
    body_html, body_text = _append_signature_and_disclaimer(body_html, body_text, user_id)

    primary = _get_email_brand_primary()
    highlight_fragment = _compose_email_highlight_fragment(
        primary, attachments, include_quote_highlight
    )
    orig_body = body_html or ""
    if highlight_fragment and not _looks_like_full_html_email_document(orig_body):
        body_html = highlight_fragment + orig_body
    body_text = _append_highlight_plain_text(body_text, attachments, include_quote_highlight)

    body_html = _apply_system_email_layout(body_html, header_tagline=header_tagline)

    return body_html, body_text


def send_email(
    to_email: str,
    subject: str,
    body_html: Optional[str] = None,
    body_text: Optional[str] = None,
    cc: Optional[str] = None,
    bcc: Optional[str] = None,
    attachments: Optional[List[Dict]] = None,
    in_reply_to: Optional[str] = None,
    references: Optional[str] = None,
    user_id: Optional[int] = None,
    customer_number: Optional[str] = None,
    header_tagline: Optional[str] = None,
    include_quote_highlight: bool = False,
) -> Tuple[bool, Optional[str], Optional[str], Optional[str], Optional[str]]:
    """
    Send an email via SMTP.
    
    Args:
        to_email: Recipient email address
        subject: Email subject
        body_html: HTML body content
        body_text: Plain text body content
        cc: CC recipients (comma-separated)
        bcc: BCC recipients (comma-separated)
        attachments: List of attachment dicts with 'filename' and 'content' (bytes)
        in_reply_to: Message-ID of email being replied to
        references: References header for threading
        user_id: Optional user ID to use their SMTP settings
        customer_number: Optional customer number for website visit tracking links
        header_tagline: Optional short text for the green header bar (e.g. quote emails)
        include_quote_highlight: When True, prepend the quotation highlight box (quote sends)
    
    Returns:
        Tuple of (success, message_id, error_message, body_html_as_sent, body_text_as_sent).
        Assembled bodies match what recipients receive; use for persisting Email rows.
    """
    config = get_smtp_config(user_id)
    if _is_graph_configured():
        from_email = os.getenv("MSGRAPH_FROM_EMAIL", "").strip()
        from_name = os.getenv("MSGRAPH_FROM_NAME", "").strip() or config.get("from_name") or DEFAULT_OUTBOUND_FROM_NAME
    elif os.getenv("RESEND_API_KEY", "").strip():
        from_email = config.get("from_email") or config.get("user") or os.getenv("RESEND_FROM_EMAIL", "onboarding@resend.dev")
        from_name = config.get("from_name") or os.getenv("RESEND_FROM_NAME", DEFAULT_OUTBOUND_FROM_NAME)
    else:
        from_email = config.get("from_email") or config.get("user") or os.getenv("SMTP_FROM_EMAIL")
        from_name = config.get("from_name") or os.getenv("SMTP_FROM_NAME", DEFAULT_OUTBOUND_FROM_NAME)

    # Generate message ID (needed for both test mode and real sending)
    message_id = generate_message_id()

    body_html_out, body_text_out = assemble_outbound_email_html(
        body_html=body_html,
        body_text=body_text,
        user_id=user_id,
        customer_number=customer_number,
        attachments=attachments,
        include_quote_highlight=include_quote_highlight,
        header_tagline=header_tagline,
    )

    # Check if test mode is enabled
    test_mode = config.get("test_mode", False)

    if test_mode:
        # Test mode: Log email details but don't send
        import sys
        print(f"[EMAIL TEST MODE] Email would be sent:", file=sys.stderr, flush=True)
        print(f"  From: {from_name} <{from_email}>", file=sys.stderr, flush=True)
        print(f"  To: {to_email}", file=sys.stderr, flush=True)
        if cc:
            print(f"  CC: {cc}", file=sys.stderr, flush=True)
        if bcc:
            print(f"  BCC: {bcc}", file=sys.stderr, flush=True)
        print(f"  Subject: {subject}", file=sys.stderr, flush=True)
        print(f"  Message-ID: {message_id}", file=sys.stderr, flush=True)
        if attachments:
            print(f"  Attachments: {[a.get('filename', 'unknown') for a in attachments]}", file=sys.stderr, flush=True)
        print(f"[EMAIL TEST MODE] Email saved to database but NOT sent", file=sys.stderr, flush=True)
        return True, message_id, None, body_html_out, body_text_out

    # Use Microsoft Graph when configured (priority 1)
    if _is_graph_configured():
        ok, mid, err = _send_via_graph(
            to_email=to_email, subject=subject, body_html=body_html_out, body_text=body_text_out,
            from_email=from_email, from_name=from_name, cc=cc, bcc=bcc,
            attachments=attachments, message_id=message_id, in_reply_to=in_reply_to, references=references,
        )
        return ok, mid, err, body_html_out, body_text_out

    # Use Resend when configured (priority 2 - works when SMTP is blocked e.g. on Railway)
    if os.getenv("RESEND_API_KEY", "").strip():
        ok, mid, err = _send_via_resend(
            to_email=to_email, subject=subject, body_html=body_html_out, body_text=body_text_out,
            from_email=from_email, from_name=from_name, cc=cc, bcc=bcc,
            attachments=attachments, message_id=message_id, in_reply_to=in_reply_to, references=references,
        )
        return ok, mid, err, body_html_out, body_text_out

    # SMTP path (priority 3)
    if not config["user"] or not config["password"]:
        return False, None, "Email not configured. Set Microsoft Graph vars (CLIENT_ID, CLIENT_SECRET, TENANT_ID, MSGRAPH_FROM_EMAIL), RESEND_API_KEY, or configure SMTP in My Settings.", body_html_out, body_text_out

    try:
        # Create message
        msg = MIMEMultipart("alternative")
        msg["From"] = f"{config['from_name']} <{config['from_email']}>"
        msg["To"] = to_email
        msg["Subject"] = subject
        
        if cc:
            msg["Cc"] = cc
        if bcc:
            msg["Bcc"] = bcc
        
        # Set message ID
        msg["Message-ID"] = message_id
        
        if in_reply_to:
            msg["In-Reply-To"] = in_reply_to
        if references:
            msg["References"] = references
        
        # Add body
        if body_text_out:
            msg.attach(MIMEText(body_text_out, "plain"))
        if body_html_out:
            msg.attach(MIMEText(body_html_out, "html"))
        
        # Add attachments
        if attachments:
            for attachment in attachments:
                part = MIMEBase("application", "octet-stream")
                part.set_payload(attachment["content"])
                encoders.encode_base64(part)
                part.add_header(
                    "Content-Disposition",
                    f'attachment; filename="{attachment["filename"]}"'
                )
                msg.attach(part)
        
        # Connect and send (timeout configurable; 30s default for slow/cloud networks)
        timeout = int(os.getenv("SMTP_TIMEOUT", "30"))
        if config["use_tls"]:
            server = smtplib.SMTP(config["host"], config["port"], timeout=timeout)
            server.ehlo()
            server.starttls()
            server.ehlo()
        else:
            server = smtplib.SMTP_SSL(config["host"], config["port"], timeout=timeout)
        
        server.login(config["user"], config["password"])
        recipients = [to_email]
        if cc:
            recipients.extend([e.strip() for e in cc.split(",")])
        if bcc:
            recipients.extend([e.strip() for e in bcc.split(",")])
        
        server.sendmail(config["from_email"], recipients, msg.as_string())
        server.quit()
        
        return True, message_id, None, body_html_out, body_text_out
    
    except Exception as e:
        err = str(e)
        if "timed out" in err.lower() or "connection" in err.lower():
            err += " Try: Gmail App Password (myaccount.google.com/apppasswords); port 465 with Use TLS off."
        return False, None, err, body_html_out, body_text_out


def receive_emails() -> List[Dict]:
    """
    Receive inbound mail: Microsoft Graph when configured (OAuth; required when M365 blocks IMAP basic auth),
    otherwise IMAP.
    """
    if _is_graph_configured():
        return _receive_emails_via_graph()
    return _receive_emails_imap()


def _receive_emails_imap() -> List[Dict]:
    """
    Receive emails from IMAP inbox (username/password — often blocked on Microsoft 365).
    
    Returns:
        List of email dictionaries with parsed email data
    """
    global _imap_missing_logged
    config = get_imap_config_for_poll()
    
    if not config["user"] or not config["password"]:
        if not _imap_missing_logged:
            import sys
            print(
                "IMAP: no credentials — set Railway IMAP_USER and IMAP_PASSWORD (and IMAP_HOST), "
                "or save IMAP under My Settings → Email. Inbound replies will not be imported.",
                file=sys.stderr,
                flush=True,
            )
            _imap_missing_logged = True
        return []
    
    emails = []
    
    try:
        # Connect to IMAP server
        if config["use_ssl"]:
            mail = imaplib.IMAP4_SSL(config["host"], config["port"])
        else:
            mail = imaplib.IMAP4(config["host"], config["port"])
        
        mail.login(config["user"], config["password"])
        mail.select("inbox")

        # UNSEEN: only not-yet-read (opening the reply in Outlook marks it read — LeadLock will skip it).
        # Optional: IMAP_SEARCH_MODE=since_days + IMAP_SINCE_DAYS=3 re-fetches recent mail; duplicates skipped in API by message_id.
        search_mode = (os.getenv("IMAP_SEARCH_MODE") or "unseen").strip().lower()
        if search_mode == "since_days":
            days = max(1, int(os.getenv("IMAP_SINCE_DAYS", "3")))
            since_dt = datetime.utcnow() - timedelta(days=days)
            since_str = since_dt.strftime("%d-%b-%Y")
            status, messages = mail.search(None, f'SINCE {since_str}')
        else:
            status, messages = mail.search(None, "UNSEEN")
        
        if status != "OK":
            mail.close()
            mail.logout()
            return []
        
        email_ids = messages[0].split()
        
        for email_id in email_ids:
            try:
                # Fetch email
                status, msg_data = mail.fetch(email_id, "(RFC822)")
                
                if status != "OK":
                    continue
                
                # Parse email
                email_body = msg_data[0][1]
                msg = email.message_from_bytes(email_body)
                
                # Extract headers
                from_email = msg["From"]
                to_email = msg["To"]
                subject = _decode_mime_header(msg["Subject"])
                message_id = msg["Message-ID"]
                in_reply_to = msg["In-Reply-To"]
                references = msg["References"]
                date_str = msg["Date"]
                
                # Parse date
                received_at = None
                if date_str:
                    try:
                        received_at = email.utils.parsedate_to_datetime(date_str)
                    except:
                        received_at = datetime.utcnow()
                else:
                    received_at = datetime.utcnow()
                
                # Extract body
                body_html = None
                body_text = None
                
                if msg.is_multipart():
                    for part in msg.walk():
                        content_type = part.get_content_type()
                        content_disposition = str(part.get("Content-Disposition"))
                        
                        if "attachment" not in content_disposition:
                            if content_type == "text/html":
                                body_html = part.get_payload(decode=True).decode("utf-8", errors="ignore")
                            elif content_type == "text/plain":
                                body_text = part.get_payload(decode=True).decode("utf-8", errors="ignore")
                else:
                    content_type = msg.get_content_type()
                    if content_type == "text/html":
                        body_html = msg.get_payload(decode=True).decode("utf-8", errors="ignore")
                    elif content_type == "text/plain":
                        body_text = msg.get_payload(decode=True).decode("utf-8", errors="ignore")
                
                # Extract attachments
                attachments = []
                if msg.is_multipart():
                    for part in msg.walk():
                        content_disposition = str(part.get("Content-Disposition"))
                        if "attachment" in content_disposition:
                            filename = part.get_filename()
                            if filename:
                                attachments.append({
                                    "filename": filename,
                                    "content_type": part.get_content_type(),
                                    "size": len(part.get_payload(decode=True))
                                })
                
                emails.append({
                    "message_id": message_id,
                    "in_reply_to": in_reply_to,
                    "references": references,
                    "from_email": from_email,
                    "to_email": to_email,
                    "subject": subject,
                    "body_html": body_html,
                    "body_text": body_text,
                    "received_at": received_at,
                    "attachments": json.dumps(attachments) if attachments else None
                })
                
            except Exception as e:
                print(f"Error parsing email {email_id}: {e}")
                continue
        
        # Mark emails as read
        if email_ids:
            mail.store(b",".join(email_ids), "+FLAGS", "\\Seen")
        
        mail.close()
        mail.logout()
        
    except Exception as e:
        import sys
        print(f"Error receiving emails: {e}", file=sys.stderr, flush=True)
    
    return emails
