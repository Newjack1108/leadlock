from fastapi import APIRouter, Depends, Query
from sqlmodel import Session, select, func, or_
from sqlalchemy.exc import DataError
from app.database import get_session
from app.models import (
    ActivityType,
    Lead,
    LeadStatus,
    LeadSource,
    Quote,
    QuoteStatus,
    Activity,
    StatusHistory,
    SmsMessage,
    SmsDirection,
    Customer,
    MessengerMessage,
    MessengerDirection,
    Email,
    EmailDirection,
)
from app.distance_service import bulk_geocode_postcodes
from app.date_ranges import resolve_date_range
from app.auth import require_non_dealer_user
from app.schemas import (
    DashboardStats,
    DashboardChannelDirectionCounts,
    DashboardCommunicationTotals,
    LeadSourceCount,
    LeadLocationItem,
    UnreadSmsSummary,
    UnreadSmsMessageItem,
    UnreadMessengerSummary,
    UnreadMessengerMessageItem,
    UnreadEmailSummary,
    UnreadByCustomerItem,
    QualifiedForQuotingSummary,
    QualifiedForQuotingItem,
)
from typing import Optional

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


@router.get("/stats", response_model=DashboardStats)
async def get_dashboard_stats(
    session: Session = Depends(get_session),
    current_user = Depends(require_non_dealer_user),
    period: Optional[str] = Query(None, description="Filter by period: all, week, month, quarter, year."),
    start_date: Optional[str] = Query(None, description="Custom range start date (YYYY-MM-DD)."),
    end_date: Optional[str] = Query(None, description="Custom range end date (YYYY-MM-DD)."),
):
    resolved_range = resolve_date_range(period=period, start_date=start_date, end_date=end_date, default_period="all")
    date_filter = None
    quote_date_filter = None
    if resolved_range.period != "all":
        date_filter = (Lead.created_at >= resolved_range.start) & (Lead.created_at <= resolved_range.end)
        quote_date_filter = (Quote.sent_at >= resolved_range.start) & (Quote.sent_at <= resolved_range.end)

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
    try:
        closed_count = count_leads(Lead.status == LeadStatus.CLOSED)
    except DataError as exc:
        # Temporary compatibility guard for production enum drift.
        # Some DBs may not yet include CLOSED in leadstatus; treat as 0 until migrated.
        error_text = str(exc).lower()
        if "invalid input value for enum leadstatus" in error_text and "closed" in error_text:
            closed_count = 0
        else:
            raise

    # Count quotes sent (Quote records with status beyond DRAFT; one lead can have multiple)
    quotes_sent_stmt = select(func.count(Quote.id)).where(
        Quote.status.in_([QuoteStatus.SENT, QuoteStatus.VIEWED, QuoteStatus.ACCEPTED, QuoteStatus.REJECTED, QuoteStatus.EXPIRED])
    )
    if quote_date_filter is not None:
        quotes_sent_stmt = quotes_sent_stmt.where(quote_date_filter)
    quotes_sent_count = session.exec(quotes_sent_stmt).one()

    # Count unique leads that have at least one sent quote (Quote linked via customer_id)
    leads_with_sent_quotes_subq = (
        select(Lead.id)
        .join(Quote, (Lead.customer_id == Quote.customer_id) & (Lead.customer_id.isnot(None)))
        .where(
            Quote.status.in_([QuoteStatus.SENT, QuoteStatus.VIEWED, QuoteStatus.ACCEPTED, QuoteStatus.REJECTED, QuoteStatus.EXPIRED])
        )
    )
    if quote_date_filter is not None:
        leads_with_sent_quotes_subq = leads_with_sent_quotes_subq.where(quote_date_filter)
    leads_with_sent_quotes_subq = leads_with_sent_quotes_subq.distinct()
    leads_with_sent_quotes_stmt = select(func.count()).select_from(leads_with_sent_quotes_subq.subquery())
    leads_with_sent_quotes_count = session.exec(leads_with_sent_quotes_stmt).one()

    # Leads by source (grouped count, with optional date filter)
    leads_by_source_stmt = (
        select(Lead.lead_source, func.count(Lead.id).label("count"))
        .group_by(Lead.lead_source)
    )
    if date_filter is not None:
        leads_by_source_stmt = leads_by_source_stmt.where(date_filter)
    leads_by_source_rows = session.exec(leads_by_source_stmt).all()
    leads_by_source = []
    for row in leads_by_source_rows:
        if row[1] <= 0:
            continue
        source_val = row[0]
        if source_val is None:
            source_str = "Unknown"
        elif hasattr(source_val, "value"):
            source_str = source_val.value
        else:
            source_str = str(source_val)
        leads_by_source.append(LeadSourceCount(source=source_str, count=row[1]))
    leads_by_source.sort(key=lambda x: x.count, reverse=True)
    
    engaged_percentage = (engaged_count / total_leads * 100) if total_leads > 0 else 0.0
    qualified_percentage = (qualified_count / total_leads * 100) if total_leads > 0 else 0.0
    
    return DashboardStats(
        total_leads=total_leads,
        new_count=new_count,
        engaged_count=engaged_count,
        qualified_count=qualified_count,
        quoted_count=quoted_count,
        quotes_sent_count=quotes_sent_count,
        leads_with_sent_quotes_count=leads_with_sent_quotes_count,
        won_count=won_count,
        lost_count=lost_count,
        closed_count=closed_count,
        engaged_percentage=round(engaged_percentage, 1),
        qualified_percentage=round(qualified_percentage, 1),
        leads_by_source=leads_by_source,
    )


@router.get("/communication-totals", response_model=DashboardCommunicationTotals)
async def get_dashboard_communication_totals(
    session: Session = Depends(get_session),
    current_user=Depends(require_non_dealer_user),
    period: Optional[str] = Query("week", description="Period: all, week, month, quarter, year."),
    start_date: Optional[str] = Query(None, description="Custom range start date (YYYY-MM-DD)."),
    end_date: Optional[str] = Query(None, description="Custom range end date (YYYY-MM-DD)."),
):
    resolved_range = resolve_date_range(period=period, start_date=start_date, end_date=end_date, default_period="week")
    date_clause = (resolved_range.start, resolved_range.end)

    email_sent = session.exec(
        select(func.count(Email.id)).where(
            Email.direction == EmailDirection.SENT,
            Email.created_at >= date_clause[0],
            Email.created_at <= date_clause[1],
        )
    ).one()
    email_received = session.exec(
        select(func.count(Email.id)).where(
            Email.direction == EmailDirection.RECEIVED,
            Email.created_at >= date_clause[0],
            Email.created_at <= date_clause[1],
        )
    ).one()

    sms_sent = session.exec(
        select(func.count(SmsMessage.id)).where(
            SmsMessage.direction == SmsDirection.SENT,
            SmsMessage.created_at >= date_clause[0],
            SmsMessage.created_at <= date_clause[1],
        )
    ).one()
    sms_received = session.exec(
        select(func.count(SmsMessage.id)).where(
            SmsMessage.direction == SmsDirection.RECEIVED,
            SmsMessage.created_at >= date_clause[0],
            SmsMessage.created_at <= date_clause[1],
        )
    ).one()

    phone_answered = session.exec(
        select(func.count(Activity.id)).where(
            Activity.activity_type == ActivityType.LIVE_CALL,
            Activity.created_at >= date_clause[0],
            Activity.created_at <= date_clause[1],
        )
    ).one()
    phone_unanswered = session.exec(
        select(func.count(Activity.id)).where(
            Activity.activity_type == ActivityType.CALL_ATTEMPTED,
            Activity.created_at >= date_clause[0],
            Activity.created_at <= date_clause[1],
        )
    ).one()

    # Reply rate = distinct contacted customers who replied / distinct contacted customers.
    email_contacted_customers = set(
        session.exec(
            select(Email.customer_id).where(
                Email.direction == EmailDirection.SENT,
                Email.created_at >= date_clause[0],
                Email.created_at <= date_clause[1],
            )
        ).all()
    )
    email_replied_customers = set(
        session.exec(
            select(Email.customer_id).where(
                Email.direction == EmailDirection.RECEIVED,
                Email.created_at >= date_clause[0],
                Email.created_at <= date_clause[1],
            )
        ).all()
    )
    email_reply_rate_pct = (
        round((len(email_contacted_customers & email_replied_customers) / len(email_contacted_customers)) * 100, 1)
        if len(email_contacted_customers) > 0
        else 0.0
    )

    sms_contacted_customers = set(
        session.exec(
            select(SmsMessage.customer_id).where(
                SmsMessage.direction == SmsDirection.SENT,
                SmsMessage.created_at >= date_clause[0],
                SmsMessage.created_at <= date_clause[1],
            )
        ).all()
    )
    sms_replied_customers = set(
        session.exec(
            select(SmsMessage.customer_id).where(
                SmsMessage.direction == SmsDirection.RECEIVED,
                SmsMessage.created_at >= date_clause[0],
                SmsMessage.created_at <= date_clause[1],
            )
        ).all()
    )
    sms_reply_rate_pct = (
        round((len(sms_contacted_customers & sms_replied_customers) / len(sms_contacted_customers)) * 100, 1)
        if len(sms_contacted_customers) > 0
        else 0.0
    )

    total_sent = email_sent + sms_sent + phone_unanswered
    total_received = email_received + sms_received + phone_answered

    return DashboardCommunicationTotals(
        period=resolved_range.period,
        start_date=resolved_range.start,
        end_date=resolved_range.end,
        email=DashboardChannelDirectionCounts(sent=email_sent, received=email_received),
        sms=DashboardChannelDirectionCounts(sent=sms_sent, received=sms_received),
        phone=DashboardChannelDirectionCounts(sent=phone_unanswered, received=phone_answered),
        phone_answered=phone_answered,
        phone_unanswered=phone_unanswered,
        email_reply_rate_pct=email_reply_rate_pct,
        sms_reply_rate_pct=sms_reply_rate_pct,
        total_sent=total_sent,
        total_received=total_received,
        total=total_sent + total_received,
    )


@router.get("/lead-locations", response_model=list[LeadLocationItem])
async def get_lead_locations(
    session: Session = Depends(get_session),
    current_user = Depends(require_non_dealer_user),
    period: Optional[str] = Query(None, description="Filter by period: all, week, month, quarter, year."),
    start_date: Optional[str] = Query(None, description="Custom range start date (YYYY-MM-DD)."),
    end_date: Optional[str] = Query(None, description="Custom range end date (YYYY-MM-DD)."),
):
    """Get geocoded lead locations for dashboard map. Includes all leads that came in during the period (any status). Uses lead postcode, or customer postcode when lead has none."""
    resolved_range = resolve_date_range(period=period, start_date=start_date, end_date=end_date, default_period="all")
    date_filter = None
    if resolved_range.period != "all":
        date_filter = (Lead.created_at >= resolved_range.start) & (Lead.created_at <= resolved_range.end)

    # 1. Leads with postcode
    stmt = (
        select(Lead.postcode, func.count(Lead.id).label("count"))
        .where(Lead.postcode.isnot(None), Lead.postcode != "")
        .group_by(Lead.postcode)
    )
    if date_filter is not None:
        stmt = stmt.where(date_filter)
    rows = session.exec(stmt).all()
    postcode_counts: dict[str, int] = {}
    for postcode, count in rows:
        pc = (postcode or "").strip()
        if pc:
            postcode_counts[pc] = postcode_counts.get(pc, 0) + count

    # 2. Leads without postcode but with qualified customer that has postcode
    stmt2 = (
        select(Customer.postcode, func.count(Lead.id).label("count"))
        .join(Customer, Lead.customer_id == Customer.id)
        .where(
            or_(Lead.postcode.is_(None), Lead.postcode == ""),
            Customer.postcode.isnot(None),
            Customer.postcode != "",
        )
        .group_by(Customer.postcode)
    )
    if date_filter is not None:
        stmt2 = stmt2.where(date_filter)
    rows2 = session.exec(stmt2).all()
    for postcode, count in rows2:
        pc = (postcode or "").strip()
        if pc:
            postcode_counts[pc] = postcode_counts.get(pc, 0) + count

    if not postcode_counts:
        return []

    postcodes = list(postcode_counts.keys())
    counts = [postcode_counts[pc] for pc in postcodes]
    coords_list = bulk_geocode_postcodes(postcodes)
    out = []
    for i, coords in enumerate(coords_list):
        if coords is not None:
            out.append(
                LeadLocationItem(
                    lat=coords[0],
                    lng=coords[1],
                    postcode=postcodes[i],
                    count=counts[i],
                )
            )
    return out

@router.get("/unread-sms", response_model=UnreadSmsSummary)
async def get_unread_sms(
    session: Session = Depends(get_session),
    current_user=Depends(require_non_dealer_user),
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
    current_user=Depends(require_non_dealer_user),
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


@router.get("/unread-email", response_model=UnreadEmailSummary)
async def get_unread_email(
    session: Session = Depends(get_session),
    current_user=Depends(require_non_dealer_user),
):
    """Count of unread received inbound emails (read_at IS NULL)."""
    count_statement = select(func.count(Email.id)).where(
        Email.direction == EmailDirection.RECEIVED,
        Email.read_at.is_(None),
    )
    count = session.exec(count_statement).one()
    return UnreadEmailSummary(count=count)


@router.get("/qualified-for-quoting", response_model=QualifiedForQuotingSummary)
async def get_qualified_for_quoting(
    session: Session = Depends(get_session),
    current_user=Depends(require_non_dealer_user),
    assigned_to: Optional[str] = Query(None, description="Filter: 'me' for leads assigned to current user. Omit for all QUALIFIED leads."),
):
    """QUALIFIED leads with no customer Activity since last time they became QUALIFIED (new qualified queue)."""
    qualified_at_subq = (
        select(
            StatusHistory.lead_id.label("lead_id"),
            func.max(StatusHistory.created_at).label("qualified_at"),
        )
        .where(StatusHistory.new_status == LeadStatus.QUALIFIED)
        .group_by(StatusHistory.lead_id)
    ).subquery()

    post_qualified_activity = (
        select(Activity.id)
        .where(
            Activity.customer_id == Lead.customer_id,
            Activity.created_at > qualified_at_subq.c.qualified_at,
        )
        .exists()
    )

    statement = (
        select(Lead)
        .outerjoin(qualified_at_subq, qualified_at_subq.c.lead_id == Lead.id)
        .where(Lead.status == LeadStatus.QUALIFIED)
        .where(
            or_(
                qualified_at_subq.c.qualified_at.is_(None),
                ~post_qualified_activity,
            )
        )
        .order_by(Lead.updated_at.asc())
    )
    if assigned_to == "me":
        statement = statement.where(Lead.assigned_to_id == current_user.id)
    leads = list(session.exec(statement).all())
    items = []
    for lead in leads:
        customer_name = None
        if lead.customer_id:
            customer = session.get(Customer, lead.customer_id)
            customer_name = customer.name if customer else None
        items.append(
            QualifiedForQuotingItem(
                id=lead.id,
                name=lead.name,
                customer_name=customer_name,
                updated_at=lead.updated_at,
                assigned_to_id=lead.assigned_to_id,
            )
        )
    return QualifiedForQuotingSummary(count=len(items), leads=items)


@router.get("/unread-by-customer", response_model=list[UnreadByCustomerItem])
async def get_unread_by_customer(
    session: Session = Depends(get_session),
    current_user=Depends(require_non_dealer_user),
):
    """Get unread message count per customer (SMS + Messenger + email). Only includes customers with at least one unread."""
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

    # Unread inbound email counts per customer_id
    email_statement = (
        select(Email.customer_id, func.count(Email.id).label("cnt"))
        .where(Email.direction == EmailDirection.RECEIVED, Email.read_at.is_(None))
        .group_by(Email.customer_id)
    )
    email_rows = session.exec(email_statement).all()
    for customer_id, cnt in email_rows:
        merged[customer_id] = merged.get(customer_id, 0) + cnt

    return [UnreadByCustomerItem(customer_id=cid, unread_count=total) for cid, total in merged.items()]
