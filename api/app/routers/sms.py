"""
SMS router for sending, receiving, and scheduling SMS via Twilio.
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session, select
from typing import List, Optional
from datetime import datetime, timedelta

from app.database import get_session
from app.models import (
    SmsMessage,
    SmsDirection,
    ScheduledSms,
    ScheduledSmsStatus,
    Customer,
    Lead,
    User,
    Activity,
    ActivityType,
)
from app.auth import get_current_user
from app.schemas import (
    SmsCreate,
    SmsResponse,
    SmsScheduledCreate,
    SmsScheduledResponse,
    SmsScheduledUpdate,
    MessagesMarkReadResult,
    MessageIdsMarkUnread,
    MessagesMarkUnreadResult,
)
from app.sms_service import send_sms, normalize_phone, validate_outbound_phone

router = APIRouter(prefix="/api/sms", tags=["sms"])


def _sms_to_response(msg: SmsMessage, created_by_name: Optional[str] = None) -> SmsResponse:
    return SmsResponse(
        id=msg.id,
        customer_id=msg.customer_id,
        lead_id=msg.lead_id,
        direction=msg.direction,
        from_phone=msg.from_phone,
        to_phone=msg.to_phone,
        body=msg.body,
        twilio_sid=msg.twilio_sid,
        sent_at=msg.sent_at,
        received_at=msg.received_at,
        read_at=msg.read_at,
        created_by_id=msg.created_by_id,
        created_at=msg.created_at,
        created_by_name=created_by_name,
    )


@router.post("", response_model=SmsResponse)
async def send_sms_to_customer(
    data: SmsCreate,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """Send an SMS to a customer (or lead)."""
    statement = select(Customer).where(Customer.id == data.customer_id)
    customer = session.exec(statement).first()
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")
    if not (customer.phone or "").strip():
        raise HTTPException(
            status_code=400,
            detail="SMS is disabled for this customer until a phone number is added",
        )

    to_phone = data.to_phone or (customer.phone if customer.phone else None)
    if data.lead_id and not to_phone:
        statement = select(Lead).where(Lead.id == data.lead_id)
        lead = session.exec(statement).first()
        if lead and lead.phone:
            to_phone = lead.phone
    if not to_phone:
        raise HTTPException(status_code=400, detail="No phone number; set to_phone or customer/lead phone")

    success, sid, error = send_sms(to_phone, data.body)
    if not success:
        raise HTTPException(status_code=500, detail=error or "Failed to send SMS")

    from_phone = None
    import os
    from_phone = os.getenv("TWILIO_PHONE_NUMBER", "")
    now = datetime.utcnow()
    msg = SmsMessage(
        customer_id=data.customer_id,
        lead_id=data.lead_id,
        direction=SmsDirection.SENT,
        from_phone=from_phone,
        to_phone=normalize_phone(to_phone),
        body=data.body,
        twilio_sid=sid,
        sent_at=now,
        created_by_id=current_user.id,
    )
    session.add(msg)
    session.commit()
    session.refresh(msg)

    activity = Activity(
        customer_id=data.customer_id,
        activity_type=ActivityType.SMS_SENT,
        notes=f"SMS sent to {to_phone}\n{data.body}",
        created_by_id=current_user.id,
    )
    session.add(activity)
    session.commit()

    return _sms_to_response(msg, current_user.full_name)


@router.get("/customers/{customer_id}", response_model=List[SmsResponse])
async def get_customer_sms(
    customer_id: int,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """Get all SMS messages for a customer."""
    statement = select(Customer).where(Customer.id == customer_id)
    customer = session.exec(statement).first()
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")

    statement = (
        select(SmsMessage)
        .where(SmsMessage.customer_id == customer_id)
        .order_by(SmsMessage.created_at.desc())
    )
    messages = list(session.exec(statement).all())
    result = []
    for msg in messages:
        name = None
        if msg.created_by_id:
            u = session.get(User, msg.created_by_id)
            name = u.full_name if u else None
        result.append(_sms_to_response(msg, name))
    return result


@router.post("/customers/{customer_id}/mark-read", response_model=MessagesMarkReadResult)
async def mark_customer_sms_read(
    customer_id: int,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """Mark all received SMS for this customer as read."""
    statement = select(Customer).where(Customer.id == customer_id)
    customer = session.exec(statement).first()
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")

    statement = select(SmsMessage).where(
        SmsMessage.customer_id == customer_id,
        SmsMessage.direction == SmsDirection.RECEIVED,
        SmsMessage.read_at.is_(None),
    )
    messages = list(session.exec(statement).all())
    now = datetime.utcnow()
    for msg in messages:
        msg.read_at = now
        session.add(msg)
    session.commit()
    return MessagesMarkReadResult(
        marked_count=len(messages),
        marked_ids=[m.id for m in messages],
    )


@router.post("/mark-unread", response_model=MessagesMarkUnreadResult)
async def mark_sms_unread(
    body: MessageIdsMarkUnread,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """Clear read_at on received SMS by id (restore unread indicators)."""
    ids = list(dict.fromkeys(body.message_ids))
    if not ids:
        return MessagesMarkUnreadResult(unmarked_count=0)
    to_update: List[SmsMessage] = []
    for mid in ids:
        msg = session.get(SmsMessage, mid)
        if not msg:
            raise HTTPException(status_code=400, detail=f"SMS message not found: {mid}")
        if msg.direction != SmsDirection.RECEIVED:
            raise HTTPException(status_code=400, detail=f"Not a received SMS: {mid}")
        to_update.append(msg)
    for msg in to_update:
        msg.read_at = None
        session.add(msg)
    session.commit()
    return MessagesMarkUnreadResult(unmarked_count=len(to_update))


@router.post("/customers/{customer_id}/bot/pause")
async def pause_customer_sms_bot(
    customer_id: int,
    minutes: int = Query(720, ge=1, le=10080),
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """Pause SMS bot replies for one customer for N minutes."""
    customer = session.get(Customer, customer_id)
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")
    until = datetime.utcnow() + timedelta(minutes=minutes)
    customer.sms_bot_paused_until = until
    session.add(customer)
    session.add(
        Activity(
            customer_id=customer.id,
            activity_type=ActivityType.NOTE,
            notes=f"SMS bot paused until {until.isoformat()}Z",
            created_by_id=current_user.id,
        )
    )
    session.commit()
    return {"ok": True, "customer_id": customer.id, "paused_until": until}


@router.post("/customers/{customer_id}/bot/stop")
async def stop_customer_sms_bot(
    customer_id: int,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """Stop SMS bot auto-replies for this customer until resumed."""
    customer = session.get(Customer, customer_id)
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")
    customer.sms_bot_stopped = True
    session.add(customer)
    session.add(
        Activity(
            customer_id=customer.id,
            activity_type=ActivityType.NOTE,
            notes="SMS bot stopped for this customer",
            created_by_id=current_user.id,
        )
    )
    session.commit()
    return {"ok": True, "customer_id": customer.id, "sms_bot_stopped": True}


@router.post("/customers/{customer_id}/bot/resume")
async def resume_customer_sms_bot(
    customer_id: int,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """Resume SMS bot replies: clears pause timer and stopped flag."""
    customer = session.get(Customer, customer_id)
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")
    customer.sms_bot_paused_until = None
    customer.sms_bot_stopped = False
    session.add(customer)
    session.add(
        Activity(
            customer_id=customer.id,
            activity_type=ActivityType.NOTE,
            notes="SMS bot resumed for this customer",
            created_by_id=current_user.id,
        )
    )
    session.commit()
    return {"ok": True, "customer_id": customer.id, "paused_until": None, "sms_bot_stopped": False}


# Scheduled SMS (must be before /{sms_id} so /scheduled is not captured as sms_id)
@router.post("/scheduled", response_model=SmsScheduledResponse)
async def create_scheduled_sms(
    data: SmsScheduledCreate,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """Schedule an SMS to be sent later."""
    statement = select(Customer).where(Customer.id == data.customer_id)
    customer = session.exec(statement).first()
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")
    if not (customer.phone or "").strip():
        raise HTTPException(
            status_code=400,
            detail="SMS automations are disabled for this customer until a phone number is added",
        )
    is_valid, normalized_to_phone, phone_error = validate_outbound_phone(data.to_phone)
    if not is_valid:
        raise HTTPException(status_code=400, detail=phone_error or "Invalid phone number")

    scheduled = ScheduledSms(
        customer_id=data.customer_id,
        to_phone=normalized_to_phone,
        body=data.body,
        scheduled_at=data.scheduled_at,
        status=ScheduledSmsStatus.PENDING,
        created_by_id=current_user.id,
    )
    session.add(scheduled)
    session.commit()
    session.refresh(scheduled)
    return SmsScheduledResponse(
        id=scheduled.id,
        customer_id=scheduled.customer_id,
        to_phone=scheduled.to_phone,
        body=scheduled.body,
        scheduled_at=scheduled.scheduled_at,
        status=scheduled.status,
        created_by_id=scheduled.created_by_id,
        created_at=scheduled.created_at,
        sent_at=scheduled.sent_at,
        twilio_sid=scheduled.twilio_sid,
        failure_reason=scheduled.failure_reason,
    )


@router.get("/scheduled", response_model=List[SmsScheduledResponse])
async def list_scheduled_sms(
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
    customer_id: Optional[int] = Query(None),
    status: Optional[ScheduledSmsStatus] = Query(None),
):
    """List scheduled SMS; optionally filter by customer_id and status."""
    statement = select(ScheduledSms).order_by(ScheduledSms.scheduled_at)
    if customer_id is not None:
        statement = statement.where(ScheduledSms.customer_id == customer_id)
    if status is not None:
        statement = statement.where(ScheduledSms.status == status)
    items = list(session.exec(statement).all())
    return [
        SmsScheduledResponse(
            id=s.id,
            customer_id=s.customer_id,
            to_phone=s.to_phone,
            body=s.body,
            scheduled_at=s.scheduled_at,
            status=s.status,
            created_by_id=s.created_by_id,
            created_at=s.created_at,
            sent_at=s.sent_at,
            twilio_sid=s.twilio_sid,
            failure_reason=s.failure_reason,
        )
        for s in items
    ]


@router.patch("/scheduled/{scheduled_id}", response_model=SmsScheduledResponse)
async def update_scheduled_sms(
    scheduled_id: int,
    data: SmsScheduledUpdate,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """Update a scheduled SMS (e.g. reschedule or cancel)."""
    scheduled = session.get(ScheduledSms, scheduled_id)
    if not scheduled:
        raise HTTPException(status_code=404, detail="Scheduled SMS not found")
    if scheduled.status != ScheduledSmsStatus.PENDING:
        raise HTTPException(status_code=400, detail="Can only update PENDING scheduled SMS")
    if data.scheduled_at is not None:
        scheduled.scheduled_at = data.scheduled_at
    if data.status is not None:
        scheduled.status = data.status
    session.add(scheduled)
    session.commit()
    session.refresh(scheduled)
    return SmsScheduledResponse(
        id=scheduled.id,
        customer_id=scheduled.customer_id,
        to_phone=scheduled.to_phone,
        body=scheduled.body,
        scheduled_at=scheduled.scheduled_at,
        status=scheduled.status,
        created_by_id=scheduled.created_by_id,
        created_at=scheduled.created_at,
        sent_at=scheduled.sent_at,
        twilio_sid=scheduled.twilio_sid,
        failure_reason=scheduled.failure_reason,
    )


@router.delete("/scheduled/{scheduled_id}")
async def cancel_scheduled_sms(
    scheduled_id: int,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """Cancel a scheduled SMS (set status to CANCELLED)."""
    scheduled = session.get(ScheduledSms, scheduled_id)
    if not scheduled:
        raise HTTPException(status_code=404, detail="Scheduled SMS not found")
    if scheduled.status != ScheduledSmsStatus.PENDING:
        raise HTTPException(status_code=400, detail="Scheduled SMS is not PENDING")
    scheduled.status = ScheduledSmsStatus.CANCELLED
    session.add(scheduled)
    session.commit()
    return {"ok": True}


@router.get("/{sms_id}", response_model=SmsResponse)
async def get_sms(
    sms_id: int,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """Get a single SMS message."""
    msg = session.get(SmsMessage, sms_id)
    if not msg:
        raise HTTPException(status_code=404, detail="SMS not found")
    name = None
    if msg.created_by_id:
        u = session.get(User, msg.created_by_id)
        name = u.full_name if u else None
    return _sms_to_response(msg, name)
