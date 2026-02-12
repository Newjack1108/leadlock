"""
Email router for sending and receiving emails.
"""
import json
import os
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlmodel import Session, select
from typing import List, Optional
from datetime import datetime
import uuid
from app.database import get_session
from app.models import Email, Customer, User, EmailDirection, Activity, ActivityType, EmailTemplate
from app.auth import get_current_user
from app.schemas import EmailCreate, EmailResponse, EmailReplyRequest
from app.email_service import send_email, receive_emails
from app.email_template_service import render_email_template

router = APIRouter(prefix="/api/emails", tags=["emails"])

# Attachment limits (bytes)
MAX_ATTACHMENT_SIZE = 10 * 1024 * 1024  # 10MB per file
MAX_TOTAL_ATTACHMENTS = 25 * 1024 * 1024  # 25MB total


def generate_thread_id(message_id: Optional[str], in_reply_to: Optional[str]) -> str:
    """Generate or retrieve thread ID for email threading."""
    if in_reply_to:
        # Try to find existing thread
        return in_reply_to.split("@")[0] if in_reply_to else str(uuid.uuid4())
    return str(uuid.uuid4())


def _sanitize_filename(filename: Optional[str]) -> str:
    """Sanitize filename to prevent path traversal."""
    if not filename or not filename.strip():
        return "attachment"
    return os.path.basename(filename.strip())


@router.post("", response_model=EmailResponse)
async def send_email_to_customer(
    email_data: str = Form(..., description="JSON string of email payload"),
    attachments: Optional[List[UploadFile]] = File(None),
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """Send an email to a customer. Accepts multipart/form-data with email_data (JSON) and optional attachments."""
    import traceback
    import sys

    try:
        data = json.loads(email_data)
        email_data_parsed = EmailCreate.model_validate(data)
    except json.JSONDecodeError as e:
        raise HTTPException(status_code=400, detail=f"Invalid email_data JSON: {e}")
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

    try:
        # Verify customer exists
        statement = select(Customer).where(Customer.id == email_data_parsed.customer_id)
        customer = session.exec(statement).first()

        if not customer:
            raise HTTPException(status_code=404, detail="Customer not found")

        # Process attachments
        attachment_list: List[dict] = []
        attachment_metadata: List[dict] = []
        total_size = 0
        files_to_process = attachments or []

        for f in files_to_process:
            if not f.filename:
                continue
            content = await f.read()
            size = len(content)
            if size > MAX_ATTACHMENT_SIZE:
                raise HTTPException(
                    status_code=400,
                    detail=f"Attachment '{f.filename}' exceeds 10MB limit"
                )
            total_size += size
            if total_size > MAX_TOTAL_ATTACHMENTS:
                raise HTTPException(
                    status_code=400,
                    detail="Total attachments exceed 25MB limit"
                )
            safe_name = _sanitize_filename(f.filename)
            attachment_list.append({"filename": safe_name, "content": content})
            attachment_metadata.append({"filename": safe_name})

        # If template_id is provided, render the template
        subject = email_data_parsed.subject
        body_html = email_data_parsed.body_html
        body_text = email_data_parsed.body_text

        if email_data_parsed.template_id:
            statement = select(EmailTemplate).where(EmailTemplate.id == email_data_parsed.template_id)
            template = session.exec(statement).first()

            if template:
                rendered_subject, rendered_body_html = render_email_template(template, customer)
                if not subject:
                    subject = rendered_subject
                if not body_html:
                    body_html = rendered_body_html
                if not body_text:
                    body_text = rendered_body_html

        # Send email via SMTP
        success, message_id, error = send_email(
            to_email=email_data_parsed.to_email,
            subject=subject,
            body_html=body_html,
            body_text=body_text,
            cc=email_data_parsed.cc,
            bcc=email_data_parsed.bcc,
            attachments=attachment_list if attachment_list else None,
            user_id=current_user.id
        )

        if not success:
            error_msg = f"Failed to send email: {error}"
            print(error_msg, file=sys.stderr, flush=True)
            raise HTTPException(status_code=500, detail=error_msg)
    except HTTPException:
        raise
    except Exception as e:
        error_msg = f"Error sending email: {str(e)}"
        print(error_msg, file=sys.stderr, flush=True)
        print(traceback.format_exc(), file=sys.stderr, flush=True)
        raise HTTPException(status_code=500, detail=error_msg)

    # Create email record
    attachments_json = json.dumps(attachment_metadata) if attachment_metadata else None
    email_record = Email(
        customer_id=email_data_parsed.customer_id,
        message_id=message_id,
        direction=EmailDirection.SENT,
        from_email=current_user.email,
        to_email=email_data_parsed.to_email,
        cc=email_data_parsed.cc,
        bcc=email_data_parsed.bcc,
        subject=subject,
        body_html=body_html,
        body_text=body_text,
        attachments=attachments_json,
        sent_at=datetime.utcnow(),
        created_by_id=current_user.id,
        thread_id=generate_thread_id(message_id, None)
    )
    session.add(email_record)
    session.commit()
    session.refresh(email_record)
    
    # Create EMAIL_SENT activity
    activity = Activity(
        customer_id=email_data_parsed.customer_id,
        activity_type=ActivityType.EMAIL_SENT,
        notes=f"Email sent to {email_data_parsed.to_email}: {subject}",
        created_by_id=current_user.id
    )
    session.add(activity)
    session.commit()
    
    return EmailResponse(
        id=email_record.id,
        customer_id=email_record.customer_id,
        message_id=email_record.message_id,
        in_reply_to=email_record.in_reply_to,
        thread_id=email_record.thread_id,
        direction=email_record.direction,
        from_email=email_record.from_email,
        to_email=email_record.to_email,
        cc=email_record.cc,
        bcc=email_record.bcc,
        subject=email_record.subject,
        body_html=email_record.body_html,
        body_text=email_record.body_text,
        attachments=email_record.attachments,
        sent_at=email_record.sent_at,
        received_at=email_record.received_at,
        created_by_id=email_record.created_by_id,
        created_at=email_record.created_at,
        created_by_name=current_user.full_name
    )


@router.get("/customers/{customer_id}", response_model=List[EmailResponse])
async def get_customer_emails(
    customer_id: int,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """Get all emails for a customer."""
    # Verify customer exists
    statement = select(Customer).where(Customer.id == customer_id)
    customer = session.exec(statement).first()
    
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")
    
    # Get emails
    statement = select(Email, User).outerjoin(User, Email.created_by_id == User.id).where(
        Email.customer_id == customer_id
    ).order_by(Email.created_at.desc())
    
    results = session.exec(statement).all()
    emails = []
    
    for email_record, user in results:
        emails.append(EmailResponse(
            id=email_record.id,
            customer_id=email_record.customer_id,
            message_id=email_record.message_id,
            in_reply_to=email_record.in_reply_to,
            thread_id=email_record.thread_id,
            direction=email_record.direction,
            from_email=email_record.from_email,
            to_email=email_record.to_email,
            cc=email_record.cc,
            bcc=email_record.bcc,
            subject=email_record.subject,
            body_html=email_record.body_html,
            body_text=email_record.body_text,
            attachments=email_record.attachments,
            sent_at=email_record.sent_at,
            received_at=email_record.received_at,
            created_by_id=email_record.created_by_id,
            created_at=email_record.created_at,
            created_by_name=user.full_name if user else None
        ))
    
    return emails


@router.get("/{email_id}", response_model=EmailResponse)
async def get_email(
    email_id: int,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """Get a single email by ID."""
    statement = select(Email, User).outerjoin(User, Email.created_by_id == User.id).where(
        Email.id == email_id
    )
    result = session.exec(statement).first()
    
    if not result:
        raise HTTPException(status_code=404, detail="Email not found")
    
    email_record, user = result
    
    return EmailResponse(
        id=email_record.id,
        customer_id=email_record.customer_id,
        message_id=email_record.message_id,
        in_reply_to=email_record.in_reply_to,
        thread_id=email_record.thread_id,
        direction=email_record.direction,
        from_email=email_record.from_email,
        to_email=email_record.to_email,
        cc=email_record.cc,
        bcc=email_record.bcc,
        subject=email_record.subject,
        body_html=email_record.body_html,
        body_text=email_record.body_text,
        attachments=email_record.attachments,
        sent_at=email_record.sent_at,
        received_at=email_record.received_at,
        created_by_id=email_record.created_by_id,
        created_at=email_record.created_at,
        created_by_name=user.full_name if user else None
    )


@router.post("/{email_id}/reply", response_model=EmailResponse)
async def reply_to_email(
    email_id: int,
    reply_data: str = Form(..., description="JSON string of reply payload (body_html, body_text, cc, bcc)"),
    attachments: Optional[List[UploadFile]] = File(None),
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """Reply to an email. Accepts multipart/form-data with reply_data (JSON) and optional attachments."""
    try:
        data = json.loads(reply_data)
        reply_data_parsed = EmailReplyRequest.model_validate(data)
    except json.JSONDecodeError as e:
        raise HTTPException(status_code=400, detail=f"Invalid reply_data JSON: {e}")
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

    # Get original email
    statement = select(Email).where(Email.id == email_id)
    original_email = session.exec(statement).first()

    if not original_email:
        raise HTTPException(status_code=404, detail="Email not found")

    # Determine reply recipient
    if original_email.direction == EmailDirection.SENT:
        to_email = original_email.to_email
    else:
        to_email = original_email.from_email

    # Create reply subject
    subject = original_email.subject
    if not subject.startswith("Re: "):
        subject = f"Re: {subject}"

    # Process attachments
    attachment_list: List[dict] = []
    attachment_metadata: List[dict] = []
    total_size = 0
    files_to_process = attachments or []

    for f in files_to_process:
        if not f.filename:
            continue
        content = await f.read()
        size = len(content)
        if size > MAX_ATTACHMENT_SIZE:
            raise HTTPException(
                status_code=400,
                detail=f"Attachment '{f.filename}' exceeds 10MB limit"
            )
        total_size += size
        if total_size > MAX_TOTAL_ATTACHMENTS:
            raise HTTPException(
                status_code=400,
                detail="Total attachments exceed 25MB limit"
            )
        safe_name = _sanitize_filename(f.filename)
        attachment_list.append({"filename": safe_name, "content": content})
        attachment_metadata.append({"filename": safe_name})

    # Send reply email
    success, message_id, error = send_email(
        to_email=to_email,
        subject=subject,
        body_html=reply_data_parsed.body_html,
        body_text=reply_data_parsed.body_text,
        cc=reply_data_parsed.cc,
        bcc=reply_data_parsed.bcc,
        attachments=attachment_list if attachment_list else None,
        in_reply_to=original_email.message_id,
        references=original_email.message_id,
        user_id=current_user.id
    )

    if not success:
        raise HTTPException(status_code=500, detail=f"Failed to send reply: {error}")

    attachments_json = json.dumps(attachment_metadata) if attachment_metadata else None
    reply_email = Email(
        customer_id=original_email.customer_id,
        message_id=message_id,
        in_reply_to=original_email.message_id,
        thread_id=original_email.thread_id or generate_thread_id(message_id, original_email.message_id),
        direction=EmailDirection.SENT,
        from_email=current_user.email,
        to_email=to_email,
        cc=reply_data_parsed.cc,
        bcc=reply_data_parsed.bcc,
        subject=subject,
        body_html=reply_data_parsed.body_html,
        body_text=reply_data_parsed.body_text,
        attachments=attachments_json,
        sent_at=datetime.utcnow(),
        created_by_id=current_user.id
    )
    session.add(reply_email)
    session.commit()
    session.refresh(reply_email)
    
    # Create EMAIL_SENT activity
    activity = Activity(
        customer_id=original_email.customer_id,
        activity_type=ActivityType.EMAIL_SENT,
        notes=f"Reply sent to {to_email}: {subject}",
        created_by_id=current_user.id
    )
    session.add(activity)
    session.commit()
    
    return EmailResponse(
        id=reply_email.id,
        customer_id=reply_email.customer_id,
        message_id=reply_email.message_id,
        in_reply_to=reply_email.in_reply_to,
        thread_id=reply_email.thread_id,
        direction=reply_email.direction,
        from_email=reply_email.from_email,
        to_email=reply_email.to_email,
        cc=reply_email.cc,
        bcc=reply_email.bcc,
        subject=reply_email.subject,
        body_html=reply_email.body_html,
        body_text=reply_email.body_text,
        attachments=reply_email.attachments,
        sent_at=reply_email.sent_at,
        received_at=reply_email.received_at,
        created_by_id=reply_email.created_by_id,
        created_at=reply_email.created_at,
        created_by_name=current_user.full_name
    )


@router.get("/{email_id}/thread", response_model=List[EmailResponse])
async def get_email_thread(
    email_id: int,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """Get email thread/conversation."""
    # Get original email
    statement = select(Email).where(Email.id == email_id)
    original_email = session.exec(statement).first()
    
    if not original_email:
        raise HTTPException(status_code=404, detail="Email not found")
    
    # Get all emails in thread
    thread_id = original_email.thread_id
    if not thread_id:
        # If no thread_id, use message_id as thread identifier
        thread_id = original_email.message_id
    
    statement = select(Email, User).outerjoin(User, Email.created_by_id == User.id).where(
        Email.thread_id == thread_id
    ).order_by(Email.created_at.asc())
    
    results = session.exec(statement).all()
    emails = []
    
    for email_record, user in results:
        emails.append(EmailResponse(
            id=email_record.id,
            customer_id=email_record.customer_id,
            message_id=email_record.message_id,
            in_reply_to=email_record.in_reply_to,
            thread_id=email_record.thread_id,
            direction=email_record.direction,
            from_email=email_record.from_email,
            to_email=email_record.to_email,
            cc=email_record.cc,
            bcc=email_record.bcc,
            subject=email_record.subject,
            body_html=email_record.body_html,
            body_text=email_record.body_text,
            attachments=email_record.attachments,
            sent_at=email_record.sent_at,
            received_at=email_record.received_at,
            created_by_id=email_record.created_by_id,
            created_at=email_record.created_at,
            created_by_name=user.full_name if user else None
        ))
    
    return emails
