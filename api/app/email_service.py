"""
Email service for sending and receiving emails via SMTP, IMAP, or Resend API.
When RESEND_API_KEY is set, outbound email uses Resend (HTTPS - works on Railway).
Otherwise SMTP is used.
"""
import base64
import re
import smtplib
import imaplib
import email
from urllib.parse import quote
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
from typing import Optional, List, Dict, Tuple
from datetime import datetime
import os
import json
import uuid
from dotenv import load_dotenv

load_dotenv()


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
    link_style = "color:#0066cc;font-weight:bold;background-color:#e8f4fc;padding:2px 6px;border-radius:4px;text-decoration:underline;"
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
    Append user signature and company disclaimer to email body.
    Order: [body] -> [signature] -> [disclaimer]
    """
    if not user_id:
        return body_html, body_text

    try:
        from sqlmodel import Session, select
        from app.database import engine
        from app.models import User, CompanySettings

        with Session(engine) as session:
            user = session.exec(select(User).where(User.id == user_id)).first()
            company = session.exec(select(CompanySettings).limit(1)).first()

            signature = (user.email_signature or "").strip() if user else ""
            disclaimer = (getattr(company, "email_disclaimer", None) or "").strip() if company else ""

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
                            "from_name": getattr(user, 'smtp_from_name', None) or user.full_name or "LeadLock CRM",
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
                            "from_name": os.getenv("SMTP_FROM_NAME", "LeadLock CRM"),
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
        "from_name": os.getenv("SMTP_FROM_NAME", "LeadLock CRM"),
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


def generate_message_id() -> str:
    """Generate a unique message ID for emails."""
    domain = os.getenv("SMTP_FROM_EMAIL", "leadlock.local").split("@")[-1]
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
    customer_number: Optional[str] = None
) -> Tuple[bool, Optional[str], Optional[str]]:
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
    
    Returns:
        Tuple of (success, message_id, error_message)
    """
    config = get_smtp_config(user_id)
    from_email = config.get("from_email") or config.get("user") or os.getenv("RESEND_FROM_EMAIL", "onboarding@resend.dev")
    from_name = config.get("from_name") or os.getenv("RESEND_FROM_NAME", "LeadLock CRM")

    # Generate message ID (needed for both test mode and real sending)
    message_id = generate_message_id()
    
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
        return True, message_id, None

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

    # Use Resend when configured (works when SMTP is blocked e.g. on Railway)
    if os.getenv("RESEND_API_KEY", "").strip():
        return _send_via_resend(
            to_email=to_email, subject=subject, body_html=body_html, body_text=body_text,
            from_email=from_email, from_name=from_name, cc=cc, bcc=bcc,
            attachments=attachments, message_id=message_id, in_reply_to=in_reply_to, references=references,
        )

    # SMTP path
    if not config["user"] or not config["password"]:
        return False, None, "SMTP not configured. Set RESEND_API_KEY in Railway variables, or configure SMTP in My Settings."

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
        if body_text:
            msg.attach(MIMEText(body_text, "plain"))
        if body_html:
            msg.attach(MIMEText(body_html, "html"))
        
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
        
        return True, message_id, None
    
    except Exception as e:
        err = str(e)
        if "timed out" in err.lower() or "connection" in err.lower():
            err += " Try: Gmail App Password (myaccount.google.com/apppasswords); port 465 with Use TLS off."
        return False, None, err


def receive_emails() -> List[Dict]:
    """
    Receive emails from IMAP inbox.
    
    Returns:
        List of email dictionaries with parsed email data
    """
    config = get_imap_config()
    
    if not config["user"] or not config["password"]:
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
        
        # Search for unread emails
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
                subject = msg["Subject"] or ""
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
        print(f"Error receiving emails: {e}")
    
    return emails
