"""
Email service for sending and receiving emails via SMTP and IMAP.
"""
import smtplib
import imaplib
import email
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
    user_id: Optional[int] = None
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
    
    Returns:
        Tuple of (success, message_id, error_message)
    """
    config = get_smtp_config(user_id)
    
    # Generate message ID (needed for both test mode and real sending)
    message_id = generate_message_id()
    
    # Check if test mode is enabled
    test_mode = config.get("test_mode", False)
    
    if test_mode:
        # Test mode: Log email details but don't send via SMTP
        import sys
        print(f"[EMAIL TEST MODE] Email would be sent:", file=sys.stderr, flush=True)
        print(f"  From: {config.get('from_name', 'N/A')} <{config.get('from_email', 'N/A')}>", file=sys.stderr, flush=True)
        print(f"  To: {to_email}", file=sys.stderr, flush=True)
        if cc:
            print(f"  CC: {cc}", file=sys.stderr, flush=True)
        if bcc:
            print(f"  BCC: {bcc}", file=sys.stderr, flush=True)
        print(f"  Subject: {subject}", file=sys.stderr, flush=True)
        print(f"  Message-ID: {message_id}", file=sys.stderr, flush=True)
        if attachments:
            print(f"  Attachments: {[a.get('filename', 'unknown') for a in attachments]}", file=sys.stderr, flush=True)
        print(f"[EMAIL TEST MODE] Email saved to database but NOT sent via SMTP", file=sys.stderr, flush=True)
        return True, message_id, None
    
    # Normal mode: Send via SMTP
    if not config["user"] or not config["password"]:
        return False, None, "SMTP credentials not configured"
    
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
        
        # Connect and send
        if config["use_tls"]:
            server = smtplib.SMTP(config["host"], config["port"])
            server.starttls()
        else:
            server = smtplib.SMTP_SSL(config["host"], config["port"])
        
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
        return False, None, str(e)


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
