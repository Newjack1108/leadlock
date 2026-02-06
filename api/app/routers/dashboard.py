from fastapi import APIRouter, Depends
from sqlmodel import Session, select, func
from app.database import get_session
from app.models import Lead, LeadStatus, Activity, SmsMessage, SmsDirection, Customer, MessengerMessage, MessengerDirection
from app.auth import get_current_user
from app.schemas import DashboardStats, UnreadSmsSummary, UnreadSmsMessageItem, UnreadMessengerSummary, UnreadMessengerMessageItem, UnreadByCustomerItem
from datetime import datetime, timedelta

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


@router.get("/stats", response_model=DashboardStats)
async def get_dashboard_stats(
    session: Session = Depends(get_session),
    current_user = Depends(get_current_user)
):
    # Count leads by status
    total_leads = session.exec(select(func.count(Lead.id))).one()
    new_count = session.exec(select(func.count(Lead.id)).where(Lead.status == LeadStatus.NEW)).one()
    engaged_count = session.exec(select(func.count(Lead.id)).where(
        Lead.status.in_([LeadStatus.ENGAGED, LeadStatus.QUALIFIED, LeadStatus.QUOTED, LeadStatus.WON])
    )).one()
    qualified_count = session.exec(select(func.count(Lead.id)).where(
        Lead.status.in_([LeadStatus.QUALIFIED, LeadStatus.QUOTED, LeadStatus.WON])
    )).one()
    quoted_count = session.exec(select(func.count(Lead.id)).where(Lead.status == LeadStatus.QUOTED)).one()
    won_count = session.exec(select(func.count(Lead.id)).where(Lead.status == LeadStatus.WON)).one()
    lost_count = session.exec(select(func.count(Lead.id)).where(Lead.status == LeadStatus.LOST)).one()
    
    engaged_percentage = (engaged_count / total_leads * 100) if total_leads > 0 else 0.0
    qualified_percentage = (qualified_count / total_leads * 100) if total_leads > 0 else 0.0
    
    return DashboardStats(
        total_leads=total_leads,
        new_count=new_count,
        engaged_count=engaged_count,
        qualified_count=qualified_count,
        quoted_count=quoted_count,
        won_count=won_count,
        lost_count=lost_count,
        engaged_percentage=round(engaged_percentage, 1),
        qualified_percentage=round(qualified_percentage, 1)
    )


@router.get("/stuck-leads")
async def get_stuck_leads(
    session: Session = Depends(get_session),
    current_user = Depends(get_current_user)
):
    """Get oldest lead per status that hasn't been updated recently."""
    stuck_leads = []
    
    for status in LeadStatus:
        statement = select(Lead).where(Lead.status == status).order_by(Lead.updated_at.asc()).limit(1)
        lead = session.exec(statement).first()
        if lead:
            days_old = (datetime.utcnow() - lead.updated_at).days
            stuck_leads.append({
                "id": lead.id,
                "name": lead.name,
                "status": lead.status.value,
                "days_old": days_old,
                "updated_at": lead.updated_at.isoformat()
            })
    
    return stuck_leads


@router.get("/unread-sms", response_model=UnreadSmsSummary)
async def get_unread_sms(
    session: Session = Depends(get_session),
    current_user=Depends(get_current_user),
):
    """Get count and list of unread received SMS for the dashboard."""
    # Unread = RECEIVED messages with read_at IS NULL
    statement = (
        select(SmsMessage)
        .where(SmsMessage.direction == SmsDirection.RECEIVED, SmsMessage.read_at.is_(None))
        .order_by(SmsMessage.created_at.desc())
        .limit(10)
    )
    messages = list(session.exec(statement).all())
    count_statement = select(func.count(SmsMessage.id)).where(
        SmsMessage.direction == SmsDirection.RECEIVED, SmsMessage.read_at.is_(None)
    )
    count = session.exec(count_statement).one()

    items = []
    for msg in messages:
        customer = session.get(Customer, msg.customer_id)
        customer_name = customer.name if customer else ""
        received_at = msg.received_at or msg.created_at
        body_snippet = (msg.body[:80] + "...") if len(msg.body) > 80 else msg.body
        items.append(
            UnreadSmsMessageItem(
                id=msg.id,
                customer_id=msg.customer_id,
                customer_name=customer_name,
                body=body_snippet,
                received_at=received_at,
                from_phone=msg.from_phone or "",
            )
        )

    return UnreadSmsSummary(count=count, messages=items)


@router.get("/unread-messenger", response_model=UnreadMessengerSummary)
async def get_unread_messenger(
    session: Session = Depends(get_session),
    current_user=Depends(get_current_user),
):
    """Get count and list of unread received Messenger messages for the dashboard."""
    statement = (
        select(MessengerMessage)
        .where(MessengerMessage.direction == MessengerDirection.RECEIVED, MessengerMessage.read_at.is_(None))
        .order_by(MessengerMessage.created_at.desc())
        .limit(10)
    )
    messages = list(session.exec(statement).all())
    count_statement = select(func.count(MessengerMessage.id)).where(
        MessengerMessage.direction == MessengerDirection.RECEIVED, MessengerMessage.read_at.is_(None)
    )
    count = session.exec(count_statement).one()
    items = []
    for msg in messages:
        customer = session.get(Customer, msg.customer_id)
        customer_name = customer.name if customer else ""
        received_at = msg.received_at or msg.created_at
        body_snippet = (msg.body[:80] + "...") if len(msg.body) > 80 else msg.body
        items.append(
            UnreadMessengerMessageItem(
                id=msg.id,
                customer_id=msg.customer_id,
                customer_name=customer_name,
                body=body_snippet,
                received_at=received_at,
                from_psid=msg.from_psid or "",
            )
        )
    return UnreadMessengerSummary(count=count, messages=items)


@router.get("/unread-by-customer", response_model=list[UnreadByCustomerItem])
async def get_unread_by_customer(
    session: Session = Depends(get_session),
    current_user=Depends(get_current_user),
):
    """Get unread message count per customer (SMS + Messenger). Only includes customers with at least one unread."""
    # Unread SMS counts per customer_id
    sms_statement = (
        select(SmsMessage.customer_id, func.count(SmsMessage.id).label("cnt"))
        .where(SmsMessage.direction == SmsDirection.RECEIVED, SmsMessage.read_at.is_(None))
        .group_by(SmsMessage.customer_id)
    )
    sms_rows = session.exec(sms_statement).all()
    merged: dict[int, int] = {row[0]: row[1] for row in sms_rows}

    # Unread Messenger counts per customer_id
    messenger_statement = (
        select(MessengerMessage.customer_id, func.count(MessengerMessage.id).label("cnt"))
        .where(MessengerMessage.direction == MessengerDirection.RECEIVED, MessengerMessage.read_at.is_(None))
        .group_by(MessengerMessage.customer_id)
    )
    messenger_rows = session.exec(messenger_statement).all()
    for customer_id, cnt in messenger_rows:
        merged[customer_id] = merged.get(customer_id, 0) + cnt

    return [UnreadByCustomerItem(customer_id=cid, unread_count=total) for cid, total in merged.items()]
