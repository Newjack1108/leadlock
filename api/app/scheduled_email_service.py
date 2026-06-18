"""Storage and send helpers for scheduled outbound emails."""

from __future__ import annotations

import json
import os
import sys
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx
from fastapi import HTTPException, UploadFile

from app.customer_file_service import delete_customer_file_from_cloudinary
from app.email_service import build_activity_email_notes, send_email
from app.models import (
    Activity,
    ActivityType,
    Customer,
    Email,
    EmailDirection,
    ScheduledEmail,
    ScheduledEmailStatus,
    User,
)
from sqlmodel import Session

try:
    import cloudinary
    import cloudinary.uploader

    CLOUDINARY_AVAILABLE = True
except ImportError:
    CLOUDINARY_AVAILABLE = False

if CLOUDINARY_AVAILABLE:
    cloudinary.config(
        cloud_name=os.getenv("CLOUDINARY_CLOUD_NAME"),
        api_key=os.getenv("CLOUDINARY_API_KEY"),
        api_secret=os.getenv("CLOUDINARY_API_SECRET"),
        secure=True,
    )

MAX_ATTACHMENT_SIZE = 10 * 1024 * 1024  # 10MB per file
MAX_TOTAL_ATTACHMENTS = 25 * 1024 * 1024  # 25MB total

LOCAL_ATTACHMENTS_DIR = Path(__file__).parent.parent / "static" / "scheduled-email-attachments"


def _cloudinary_configured() -> bool:
    return CLOUDINARY_AVAILABLE and bool(
        os.getenv("CLOUDINARY_CLOUD_NAME")
        and os.getenv("CLOUDINARY_API_KEY")
        and os.getenv("CLOUDINARY_API_SECRET")
    )


def _sanitize_filename(filename: Optional[str]) -> str:
    if not filename or not filename.strip():
        return "attachment"
    return os.path.basename(filename.strip())


def _parse_attachments_json(attachments_json: Optional[str]) -> List[Dict[str, Any]]:
    if not attachments_json:
        return []
    try:
        parsed = json.loads(attachments_json)
    except json.JSONDecodeError:
        return []
    return parsed if isinstance(parsed, list) else []


async def upload_scheduled_email_attachments(
    customer_id: int,
    files: List[UploadFile],
) -> Optional[str]:
    """Upload attachment bytes and return JSON metadata for ScheduledEmail.attachments."""
    if not files:
        return None

    attachment_meta: List[Dict[str, Any]] = []
    total_size = 0

    for f in files:
        if not f.filename:
            continue
        content = await f.read()
        size = len(content)
        if size > MAX_ATTACHMENT_SIZE:
            raise HTTPException(
                status_code=400,
                detail=f"Attachment '{f.filename}' exceeds 10MB limit",
            )
        total_size += size
        if total_size > MAX_TOTAL_ATTACHMENTS:
            raise HTTPException(
                status_code=400,
                detail="Total attachments exceed 25MB limit",
            )

        safe_name = _sanitize_filename(f.filename)
        content_type = (f.content_type or "application/octet-stream").lower()

        if _cloudinary_configured():
            try:
                upload_result = cloudinary.uploader.upload(
                    content,
                    folder=f"customers/{customer_id}/scheduled-email-attachments",
                    resource_type="auto",
                    use_filename=True,
                    unique_filename=True,
                )
            except Exception as exc:
                raise HTTPException(status_code=500, detail=f"Failed to upload attachment: {exc}")

            secure_url = upload_result.get("secure_url")
            public_id = upload_result.get("public_id")
            if not secure_url or not public_id:
                raise HTTPException(status_code=500, detail="Attachment upload completed without a durable URL")

            attachment_meta.append(
                {
                    "filename": safe_name,
                    "secure_url": secure_url,
                    "cloudinary_public_id": public_id,
                    "resource_type": upload_result.get("resource_type") or "raw",
                    "content_type": content_type,
                }
            )
            continue

        if os.getenv("RAILWAY_ENVIRONMENT"):
            raise HTTPException(
                status_code=500,
                detail="Cloudinary is not configured for scheduled email attachments",
            )

        LOCAL_ATTACHMENTS_DIR.mkdir(parents=True, exist_ok=True)
        stored_name = f"{uuid.uuid4()}_{safe_name}"
        file_path = LOCAL_ATTACHMENTS_DIR / stored_name
        try:
            file_path.write_bytes(content)
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"Failed to save attachment: {exc}")

        attachment_meta.append(
            {
                "filename": safe_name,
                "secure_url": str(file_path),
                "cloudinary_public_id": None,
                "resource_type": None,
                "content_type": content_type,
            }
        )

    return json.dumps(attachment_meta) if attachment_meta else None


async def load_attachment_bytes(meta: Dict[str, Any]) -> bytes:
    """Load attachment bytes from stored metadata (async)."""
    return _load_attachment_bytes_sync(meta)


def _load_attachment_bytes_sync(meta: Dict[str, Any]) -> bytes:
    """Load attachment bytes from stored metadata."""
    file_ref = (meta.get("secure_url") or "").strip()
    if not file_ref:
        raise HTTPException(status_code=404, detail="Attachment reference missing")

    lowered = file_ref.lower()
    if lowered.startswith("http://") or lowered.startswith("https://"):
        try:
            with httpx.Client(follow_redirects=True, timeout=30.0) as client:
                response = client.get(file_ref)
        except Exception as exc:
            raise HTTPException(status_code=502, detail=f"Failed to fetch attachment: {exc}")
        if not response.is_success or not response.content:
            raise HTTPException(status_code=404, detail="Stored attachment no longer exists")
        return response.content

    path = Path(file_ref)
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Attachment file not found on disk")
    return path.read_bytes()


async def load_scheduled_email_attachment_list(
    attachments_json: Optional[str],
) -> Optional[List[Dict[str, Any]]]:
    """Return attachment payloads suitable for send_email() (async)."""
    return load_scheduled_email_attachment_list_sync(attachments_json)


def load_scheduled_email_attachment_list_sync(
    attachments_json: Optional[str],
) -> Optional[List[Dict[str, Any]]]:
    """Return attachment payloads suitable for send_email()."""
    meta_list = _parse_attachments_json(attachments_json)
    if not meta_list:
        return None

    attachment_list: List[Dict[str, Any]] = []
    for meta in meta_list:
        filename = meta.get("filename") or "attachment"
        content = _load_attachment_bytes_sync(meta)
        attachment_list.append({"filename": filename, "content": content})
    return attachment_list


def delete_stored_attachments(attachments_json: Optional[str]) -> None:
    """Best-effort delete of stored scheduled email attachments."""
    for meta in _parse_attachments_json(attachments_json):
        public_id = meta.get("cloudinary_public_id")
        if public_id:
            delete_customer_file_from_cloudinary(
                public_id,
                meta.get("resource_type") or "raw",
            )
            continue

        file_ref = (meta.get("secure_url") or "").strip()
        if file_ref and not file_ref.lower().startswith(("http://", "https://")):
            try:
                Path(file_ref).unlink(missing_ok=True)
            except Exception as e:
                print(
                    f"Failed to delete local scheduled email attachment {file_ref}: {e}",
                    file=sys.stderr,
                    flush=True,
                )


def _email_attachment_metadata(attachments_json: Optional[str]) -> Optional[str]:
    """Filename-only metadata for the sent Email record."""
    meta_list = _parse_attachments_json(attachments_json)
    if not meta_list:
        return None
    return json.dumps([{"filename": m.get("filename") or "attachment"} for m in meta_list])


def process_due_scheduled_email(session: Session, scheduled_id: int) -> None:
    """Send a due scheduled email and update its status."""
    scheduled = session.get(ScheduledEmail, scheduled_id)
    if not scheduled or scheduled.status != ScheduledEmailStatus.PENDING:
        return

    payload = {
        "customer_id": scheduled.customer_id,
        "to_email": scheduled.to_email,
        "cc": scheduled.cc,
        "bcc": scheduled.bcc,
        "subject": scheduled.subject,
        "body_html": scheduled.body_html,
        "body_text": scheduled.body_text,
        "attachments_json": scheduled.attachments,
        "created_by_id": scheduled.created_by_id,
    }

    customer = session.get(Customer, payload["customer_id"])
    user = session.get(User, payload["created_by_id"])
    customer_number = customer.customer_number if customer else None
    from_email = (user.email if user else None) or os.getenv("SMTP_FROM_EMAIL", "")

    has_customer_email = bool(customer and (customer.email or "").strip())

    attachment_list = None
    try:
        attachment_list = load_scheduled_email_attachment_list_sync(payload["attachments_json"])
    except Exception as e:
        scheduled.status = ScheduledEmailStatus.FAILED
        scheduled.failure_reason = str(e)[:1000]
        session.add(scheduled)
        session.commit()
        return

    if has_customer_email or payload["to_email"]:
        try:
            success, message_id, err, sent_html, sent_text = send_email(
                to_email=payload["to_email"],
                subject=payload["subject"],
                body_html=payload["body_html"],
                body_text=payload["body_text"],
                cc=payload["cc"],
                bcc=payload["bcc"],
                attachments=attachment_list,
                user_id=payload["created_by_id"],
                customer_number=customer_number,
            )
        except Exception as e:
            success, message_id, err, sent_html, sent_text = False, None, str(e), None, None
    else:
        success, message_id, err, sent_html, sent_text = (
            False,
            None,
            "Customer has no email address; scheduled email cannot be sent",
            None,
            None,
        )

    scheduled = session.get(ScheduledEmail, scheduled_id)
    if not scheduled or scheduled.status != ScheduledEmailStatus.PENDING:
        return

    try:
        if success:
            attachments_json = _email_attachment_metadata(payload["attachments_json"])
            email_record = Email(
                customer_id=payload["customer_id"],
                message_id=message_id,
                direction=EmailDirection.SENT,
                from_email=from_email,
                to_email=payload["to_email"],
                cc=payload["cc"],
                bcc=payload["bcc"],
                subject=payload["subject"],
                body_html=sent_html or payload["body_html"],
                body_text=sent_text if sent_text is not None else payload["body_text"],
                attachments=attachments_json,
                sent_at=datetime.utcnow(),
                created_by_id=payload["created_by_id"],
                thread_id=str(uuid.uuid4()),
            )
            session.add(email_record)
            activity = Activity(
                customer_id=payload["customer_id"],
                activity_type=ActivityType.EMAIL_SENT,
                notes=build_activity_email_notes(
                    f"Scheduled email sent to {payload['to_email']}",
                    payload["subject"],
                    sent_text if sent_text is not None else payload["body_text"],
                    sent_html or payload["body_html"],
                ),
                created_by_id=payload["created_by_id"],
            )
            session.add(activity)
            scheduled.status = ScheduledEmailStatus.SENT
            scheduled.sent_at = datetime.utcnow()
            scheduled.message_id = message_id
            session.add(scheduled)
            delete_stored_attachments(payload["attachments_json"])
        else:
            print(
                f"Scheduled email {scheduled_id} send failed: {err}",
                file=sys.stderr,
                flush=True,
            )
            scheduled.status = ScheduledEmailStatus.FAILED
            scheduled.failure_reason = (err or "Email send failed")[:1000]
            session.add(scheduled)
        session.commit()
    except Exception as e:
        print(
            f"Error processing scheduled email {scheduled_id}: {e}",
            file=sys.stderr,
            flush=True,
        )
        session.rollback()
