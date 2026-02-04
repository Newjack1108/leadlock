"""
Messenger router for sending and listing Facebook Messenger messages.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select
from typing import List, Optional
from datetime import datetime

from app.database import get_session
from app.models import (
    MessengerMessage,
    MessengerDirection,
    Customer,
    User,
    Activity,
    ActivityType,
)
from app.auth import get_current_user
from app.schemas import MessengerCreate, MessengerResponse
from app.messenger_service import send_messenger_message

router = APIRouter(prefix="/api/messenger", tags=["messenger"])


def _msg_to_response(msg: MessengerMessage, created_by_name: Optional[str] = None) -> MessengerResponse:
    return MessengerResponse(
        id=msg.id,
        customer_id=msg.customer_id,
        lead_id=msg.lead_id,
        direction=msg.direction,
        from_psid=msg.from_psid,
        to_psid=msg.to_psid,
        body=msg.body,
        facebook_mid=msg.facebook_mid,
        sent_at=msg.sent_at,
        received_at=msg.received_at,
        read_at=msg.read_at,
        created_by_id=msg.created_by_id,
        created_at=msg.created_at,
        created_by_name=created_by_name,
    )


@router.post("", response_model=MessengerResponse)
async def send_messenger(
    data: MessengerCreate,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """Send a Messenger message to a customer (use customer's messenger_psid or provide to_psid)."""
    statement = select(Customer).where(Customer.id == data.customer_id)
    customer = session.exec(statement).first()
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")
    to_psid = data.to_psid or customer.messenger_psid
    if not to_psid:
        raise HTTPException(
            status_code=400,
            detail="No Messenger PSID; set to_psid or link customer via Facebook (messenger_psid)",
        )
    success, mid, error = send_messenger_message(to_psid, data.body)
    if not success:
        raise HTTPException(status_code=500, detail=error or "Failed to send Messenger message")
    now = datetime.utcnow()
    msg = MessengerMessage(
        customer_id=data.customer_id,
        lead_id=None,
        direction=MessengerDirection.SENT,
        from_psid="",  # Page PSID not stored for SENT in v1; recipient is the user
        to_psid=to_psid,
        body=data.body,
        facebook_mid=mid,
        sent_at=now,
        created_by_id=current_user.id,
    )
    session.add(msg)
    session.commit()
    session.refresh(msg)
    activity = Activity(
        customer_id=data.customer_id,
        activity_type=ActivityType.MESSENGER_SENT,
        notes=f"Messenger sent: {data.body[:50]}...",
        created_by_id=current_user.id,
    )
    session.add(activity)
    session.commit()
    return _msg_to_response(msg, current_user.full_name)


@router.get("/customers/{customer_id}", response_model=List[MessengerResponse])
async def get_customer_messenger(
    customer_id: int,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """Get all Messenger messages for a customer."""
    statement = select(Customer).where(Customer.id == customer_id)
    customer = session.exec(statement).first()
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")
    statement = (
        select(MessengerMessage)
        .where(MessengerMessage.customer_id == customer_id)
        .order_by(MessengerMessage.created_at)
    )
    messages = list(session.exec(statement).all())
    result = []
    for msg in messages:
        name = None
        if msg.created_by_id:
            u = session.get(User, msg.created_by_id)
            name = u.full_name if u else None
        result.append(_msg_to_response(msg, name))
    return result


@router.post("/customers/{customer_id}/mark-read")
async def mark_customer_messenger_read(
    customer_id: int,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """Mark all received Messenger messages for this customer as read."""
    statement = select(Customer).where(Customer.id == customer_id)
    customer = session.exec(statement).first()
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")
    statement = select(MessengerMessage).where(
        MessengerMessage.customer_id == customer_id,
        MessengerMessage.direction == MessengerDirection.RECEIVED,
        MessengerMessage.read_at.is_(None),
    )
    messages = list(session.exec(statement).all())
    now = datetime.utcnow()
    for msg in messages:
        msg.read_at = now
        session.add(msg)
    session.commit()
    return {"marked_count": len(messages)}
