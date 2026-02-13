from fastapi import APIRouter, Depends, Query
from sqlmodel import Session, select, func
from app.database import get_session
from app.models import Lead, LeadStatus, Activity, SmsMessage, SmsDirection, Customer, MessengerMessage, MessengerDirection
from app.auth import get_current_user
from app.schemas import DashboardStats, UnreadSmsSummary, UnreadSmsMessageItem, UnreadMessengerSummary, UnreadMessengerMessageItem, UnreadByCustomerItem
from datetime import datetime, timedelta
from typing import Optional

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


def get_date_range_for_period(period: str) -> tuple[datetime, datetime]:
    """Return (start, end) datetime for the given period (week, month, quarter, year)."""
    now = datetime.utcnow()
    end = now
    if period == "week":
        # This week: Monday 00:00 to now
        start_of_week = now - timedelta(days=now.weekday())
        start = start_of_week.replace(hour=0, minute=0, second=0, microsecond=0)
    elif period == "month":
        # This month: 1st 00:00 to now
        start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    elif period == "quarter":
        # This quarter: first day of quarter to now
        quarter_start_month = ((now.month - 1) // 3) * 3 + 1
        start = now.replace(month=quarter_start_month, day=1, hour=0, minute=0, second=0, microsecond=0)
    elif period == "year":
        # This year: Jan 1 00:00 to now
        start = now.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
    else:
        # Default: all time (epoch to now)
        start = datetime(1970, 1, 1)
    return start, end


@router.get("/stats", response_model=DashboardStats)
async def get_dashboard_stats(
    session: Session = Depends(get_session),
    current_user = Depends(get_current_user),
    period: Optional[str] = Query(None, description="Filter by period: week, month, quarter, year. Omit for all-time."),
):
    date_filter = None
    if period and period.lower() in ("week", "month", "quarter", "year"):
        start, end = get_date_range_for_period(period.lower())
        date_filter = (Lead.created_at >= start) & (Lead.created_at <= end)

    def count_leads(extra_cond=None):
        stmt = select(func.count(Lead.id))
        if extra_cond is not None:
            stmt = stmt.where(extra_cond)
        if date_filter is not None:
            stmt = stmt.where(date_filter)
        return session.exec(stmt).one()

    # Count leads by status (with optional date filter)
    total_leads = count_leads()
    new_count = count_leads(Lead.status == LeadStatus.NEW)
    engaged_count = count_leads(Lead.status.in_([LeadStatus.ENGAGED, LeadStatus.QUALIFIED, LeadStatus.QUOTED, LeadStatus.WON]))
    qualified_count = count_leads(Lead.status.in_([LeadStatus.QUALIFIED, LeadStatus.QUOTED, LeadStatus.WON]))
    quoted_count = count_leads(Lead.status == LeadStatus.QUOTED)
    won_count = count_leads(Lead.status == LeadStatus.WON)
    lost_count = count_leads(Lead.status == LeadStatus.LOST)
    
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
