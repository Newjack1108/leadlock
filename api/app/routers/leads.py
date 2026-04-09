from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlmodel import Session, select, or_
from sqlalchemy import func
from typing import Optional, List, Dict, Tuple
from app.database import get_session
from app.models import (
    Lead,
    User,
    Activity,
    StatusHistory,
    LeadStatus,
    LeadType,
    LeadSource,
    ActivityType,
    Customer,
    Quote,
    QuoteItem,
    QuoteStatus,
    Order,
    OpportunityStage,
    Email,
    EmailDirection,
    SmsMessage,
    SmsDirection,
    MessengerMessage,
    MessengerDirection,
    QuoteTemperature,
    FacebookAdvertProfile,
)
from app.auth import get_current_user
from app.schemas import (
    LeadCreate, LeadUpdate, LeadResponse, StatusTransitionRequest,
    ActivityCreate, ActivityResponse, StatusHistoryResponse, CustomerResponse, QuoteResponse,
    FacebookAdvertProfileResponse,
)
from app.workflow import can_transition, check_sla_overdue, check_quote_prerequisites
from app.quote_delete import delete_quote_cascade
from app.constants import QUOTE_LIST_EXCLUDED_STATUSES
from datetime import datetime

router = APIRouter(prefix="/api/leads", tags=["leads"])


def generate_customer_number(session: Session) -> str:
    """Generate a unique customer number like CUST-2024-001."""
    from datetime import date
    year = date.today().year
    
    # Find all customers with customer numbers for this year
    statement = select(Customer).where(Customer.customer_number.like(f"CUST-{year}-%"))
    customers = session.exec(statement).all()
    
    if not customers:
        return f"CUST-{year}-001"
    
    # Extract numbers and find max
    numbers = []
    for customer in customers:
        if customer.customer_number:
            try:
                num = int(customer.customer_number.split('-')[-1])
                numbers.append(num)
            except (ValueError, IndexError):
                continue
    
    if not numbers:
        return f"CUST-{year}-001"
    
    next_num = max(numbers) + 1
    return f"CUST-{year}-{next_num:03d}"


def find_or_create_customer(lead: Lead, session: Session) -> Customer:
    """
    Find existing customer by email or phone, or create new customer from lead.
    Returns the Customer instance.
    """
    # Try to find existing customer by email
    if lead.email:
        statement = select(Customer).where(Customer.email == lead.email)
        customer = session.exec(statement).first()
        if customer:
            return customer
    
    # Try to find existing customer by phone
    if lead.phone:
        statement = select(Customer).where(Customer.phone == lead.phone)
        customer = session.exec(statement).first()
        if customer:
            return customer
    
    # Create new customer from lead data
    customer = Customer(
        customer_number=generate_customer_number(session),
        name=lead.name,
        email=lead.email,
        phone=lead.phone,
        postcode=lead.postcode,
        customer_since=datetime.utcnow()
    )
    session.add(customer)
    session.commit()
    session.refresh(customer)
    return customer


def compute_lead_engagement_flags(session: Session, leads: List[Lead]) -> Dict[int, Tuple[bool, bool]]:
    """
    Per lead: (quote_viewed, has_inbound_reply).
    Quote viewed: any Quote for this lead with viewed_at set.
    Inbound reply: received Email/SMS/Messenger for the lead's customer and/or lead_id.
    """
    if not leads:
        return {}
    lead_ids = [l.id for l in leads]
    customer_ids = list({l.customer_id for l in leads if l.customer_id})

    stmt = select(Quote.lead_id).where(
        Quote.lead_id.in_(lead_ids),
        Quote.viewed_at.isnot(None),
    )
    quote_viewed_ids = {lid for lid in session.exec(stmt).all() if lid is not None}

    email_customers: set = set()
    if customer_ids:
        stmt = select(Email.customer_id).where(
            Email.customer_id.in_(customer_ids),
            Email.direction == EmailDirection.RECEIVED,
        ).distinct()
        email_customers = set(session.exec(stmt).all())

    sms_customers: set = set()
    if customer_ids:
        stmt = select(SmsMessage.customer_id).where(
            SmsMessage.customer_id.in_(customer_ids),
            SmsMessage.direction == SmsDirection.RECEIVED,
        ).distinct()
        sms_customers = set(session.exec(stmt).all())

    stmt = select(SmsMessage.lead_id).where(
        SmsMessage.lead_id.in_(lead_ids),
        SmsMessage.direction == SmsDirection.RECEIVED,
    ).distinct()
    sms_leads = {lid for lid in session.exec(stmt).all() if lid is not None}

    messenger_customers: set = set()
    if customer_ids:
        stmt = select(MessengerMessage.customer_id).where(
            MessengerMessage.customer_id.in_(customer_ids),
            MessengerMessage.direction == MessengerDirection.RECEIVED,
        ).distinct()
        messenger_customers = set(session.exec(stmt).all())

    stmt = select(MessengerMessage.lead_id).where(
        MessengerMessage.lead_id.in_(lead_ids),
        MessengerMessage.direction == MessengerDirection.RECEIVED,
    ).distinct()
    messenger_leads = {lid for lid in session.exec(stmt).all() if lid is not None}

    out: Dict[int, Tuple[bool, bool]] = {}
    for lead in leads:
        qv = lead.id in quote_viewed_ids
        cid = lead.customer_id
        reply = False
        if cid and cid in email_customers:
            reply = True
        elif cid and cid in sms_customers:
            reply = True
        elif lead.id in sms_leads:
            reply = True
        elif cid and cid in messenger_customers:
            reply = True
        elif lead.id in messenger_leads:
            reply = True
        out[lead.id] = (qv, reply)
    return out


def compute_lead_quote_list_stats(
    session: Session, leads: List[Lead]
) -> Dict[int, Tuple[Optional[QuoteTemperature], int]]:
    """
    Per lead: (latest_quote_temperature from most recently updated quote, quotes_sent_count).
    Temperature is omitted when that quote is ordered or accepted (no longer an open deal).
    """
    if not leads:
        return {}
    lead_ids = [l.id for l in leads]

    sent_counts: Dict[int, int] = {}
    stmt_sent = (
        select(Quote.lead_id, func.count(Quote.id))
        .where(Quote.lead_id.in_(lead_ids), Quote.sent_at.isnot(None))
        .group_by(Quote.lead_id)
    )
    for row in session.exec(stmt_sent).all():
        lid, cnt = row[0], row[1]
        if lid is not None:
            sent_counts[int(lid)] = int(cnt)

    temp_by_lead: Dict[int, Optional[QuoteTemperature]] = {}
    stmt_temp = (
        select(
            Quote.id,
            Quote.lead_id,
            Quote.temperature,
            Quote.status,
            Quote.opportunity_stage,
            Quote.accepted_at,
        )
        .where(Quote.lead_id.in_(lead_ids))
        .distinct(Quote.lead_id)
        .order_by(Quote.lead_id, Quote.updated_at.desc(), Quote.id.desc())
    )
    temp_rows = list(session.exec(stmt_temp).all())
    quote_ids_for_order = [row[0] for row in temp_rows if row[0] is not None]
    ordered_quote_ids: set[int] = set()
    if quote_ids_for_order:
        stmt_ord = select(Order.quote_id).where(Order.quote_id.in_(quote_ids_for_order))
        ordered_quote_ids = {int(qid) for qid in session.exec(stmt_ord).all() if qid is not None}

    for row in temp_rows:
        qid, lid, temp, q_status, opp_stage, accepted_at = (
            row[0],
            row[1],
            row[2],
            row[3],
            row[4],
            row[5],
        )
        if lid is None:
            continue
        tid = int(lid)
        if qid is not None and int(qid) in ordered_quote_ids:
            temp_by_lead[tid] = None
            continue
        if q_status == QuoteStatus.ACCEPTED or opp_stage == OpportunityStage.WON or accepted_at is not None:
            temp_by_lead[tid] = None
            continue
        if isinstance(temp, QuoteTemperature):
            temp_by_lead[tid] = temp
        elif temp is None:
            temp_by_lead[tid] = None
        else:
            try:
                temp_by_lead[tid] = QuoteTemperature(str(temp))
            except ValueError:
                temp_by_lead[tid] = None

    out: Dict[int, Tuple[Optional[QuoteTemperature], int]] = {}
    for lead in leads:
        out[lead.id] = (temp_by_lead.get(lead.id), sent_counts.get(lead.id, 0))
    return out


def enrich_lead_response(
    lead: Lead,
    session: Session,
    current_user: User,
    engagement: Optional[Tuple[bool, bool]] = None,
    quote_stats: Optional[Tuple[Optional[QuoteTemperature], int]] = None,
) -> LeadResponse:
    """Enrich lead with SLA badge, quote lock info, engagement flags, and quote list stats."""
    if engagement is None:
        engagement = compute_lead_engagement_flags(session, [lead]).get(lead.id, (False, False))
    quote_viewed, has_inbound_reply = engagement
    if quote_stats is None:
        quote_stats = compute_lead_quote_list_stats(session, [lead]).get(lead.id, (None, 0))
    latest_quote_temperature, quotes_sent_count = quote_stats
    sla_badge = check_sla_overdue(lead, session)
    
    quote_locked = False
    quote_lock_reason = None
    customer = None
    
    if lead.customer_id:
        statement = select(Customer).where(Customer.id == lead.customer_id)
        customer = session.exec(statement).first()
        
        if lead.status == LeadStatus.QUALIFIED and customer:
            can_quote, error = check_quote_prerequisites(customer, session)
            if not can_quote:
                quote_locked = True
                quote_lock_reason = error
    
    from app.models import LeadType, LeadSource, Timeframe
    
    def _safe_enum(value, enum_cls, default):
        if value is None:
            return default
        if isinstance(value, enum_cls):
            return value
        if isinstance(value, str):
            try:
                return enum_cls(value)
            except ValueError:
                return default
        return default
    
    customer_response = None
    if customer:
        customer_response = CustomerResponse(
            id=customer.id,
            customer_number=customer.customer_number,
            name=customer.name,
            email=customer.email,
            phone=customer.phone,
            address_line1=customer.address_line1,
            address_line2=customer.address_line2,
            city=customer.city,
            county=customer.county,
            postcode=customer.postcode,
            country=customer.country,
            customer_since=customer.customer_since,
            created_at=customer.created_at,
            updated_at=customer.updated_at,
            messenger_psid=customer.messenger_psid,
            source_system=customer.source_system,
        )

    advert_profile_response = None
    if lead.facebook_advert_profile_id:
        advert_statement = select(FacebookAdvertProfile).where(
            FacebookAdvertProfile.id == lead.facebook_advert_profile_id
        )
        advert_profile = session.exec(advert_statement).first()
        if advert_profile:
            advert_profile_response = FacebookAdvertProfileResponse(
                id=advert_profile.id,
                name=advert_profile.name,
                offer_type=advert_profile.offer_type,
                image_url=advert_profile.image_url,
                is_active=advert_profile.is_active,
                created_at=advert_profile.created_at,
                updated_at=advert_profile.updated_at,
            )
    
    return LeadResponse(
        id=lead.id,
        name=lead.name,
        email=lead.email,
        phone=lead.phone,
        postcode=lead.postcode,
        description=lead.description,
        status=_safe_enum(lead.status, LeadStatus, LeadStatus.NEW),
        timeframe=_safe_enum(lead.timeframe, Timeframe, Timeframe.UNKNOWN),
        scope_notes=lead.scope_notes,
        product_interest=lead.product_interest,
        lead_type=_safe_enum(getattr(lead, 'lead_type', None), LeadType, LeadType.UNKNOWN),
        lead_source=_safe_enum(getattr(lead, 'lead_source', None), LeadSource, LeadSource.UNKNOWN),
        facebook_advert_profile_id=lead.facebook_advert_profile_id,
        facebook_advert_profile=advert_profile_response,
        assigned_to_id=lead.assigned_to_id,
        customer_id=lead.customer_id,
        created_at=lead.created_at,
        updated_at=lead.updated_at,
        sla_badge=sla_badge,
        quote_locked=quote_locked,
        quote_lock_reason=quote_lock_reason,
        customer=customer_response,
        quote_viewed=quote_viewed,
        has_inbound_reply=has_inbound_reply,
        latest_quote_temperature=latest_quote_temperature,
        quotes_sent_count=quotes_sent_count,
    )


@router.get("", response_model=List[LeadResponse])
async def get_leads(
    status_filter: Optional[LeadStatus] = Query(None, alias="status"),
    lead_type: Optional[LeadType] = Query(None, alias="lead_type"),
    lead_source: Optional[LeadSource] = Query(None, alias="lead_source"),
    search: Optional[str] = Query(None),
    my_leads_only: bool = Query(False, alias="myLeads"),
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    try:
        statement = select(Lead)

        if status_filter:
            statement = statement.where(Lead.status == status_filter)

        if lead_type:
            statement = statement.where(Lead.lead_type == lead_type)

        if lead_source:
            statement = statement.where(Lead.lead_source == lead_source)

        if my_leads_only:
            statement = statement.where(Lead.assigned_to_id == current_user.id)

        if search:
            search_term = f"%{search}%"
            statement = statement.where(
                or_(
                    Lead.name.ilike(search_term),
                    Lead.email.ilike(search_term),
                    Lead.phone.ilike(search_term),
                    Lead.postcode.ilike(search_term)
                )
            )
        
        statement = statement.order_by(Lead.created_at.desc())
        leads = session.exec(statement).all()
        lead_list = list(leads)
        engagement_by_lead = compute_lead_engagement_flags(session, lead_list)
        quote_stats_by_lead = compute_lead_quote_list_stats(session, lead_list)
        return [
            enrich_lead_response(
                lead,
                session,
                current_user,
                engagement=engagement_by_lead.get(lead.id, (False, False)),
                quote_stats=quote_stats_by_lead.get(lead.id, (None, 0)),
            )
            for lead in leads
        ]
    except Exception as e:
        import traceback
        error_msg = f"Error fetching leads: {str(e)}"
        print(error_msg, file=__import__('sys').stderr, flush=True)
        print(traceback.format_exc(), file=__import__('sys').stderr, flush=True)
        raise HTTPException(status_code=500, detail=error_msg)


@router.get("/{lead_id}", response_model=LeadResponse)
async def get_lead(
    lead_id: int,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    statement = select(Lead).where(Lead.id == lead_id)
    lead = session.exec(statement).first()
    
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    
    return enrich_lead_response(lead, session, current_user)


@router.post("", response_model=LeadResponse)
async def create_lead(
    lead_data: LeadCreate,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    try:
        lead = Lead(**lead_data.dict())
        lead.assigned_to_id = current_user.id

        # Manual entry leads auto-qualify
        if lead.lead_source == LeadSource.MANUAL_ENTRY:
            lead.status = LeadStatus.QUALIFIED

        session.add(lead)
        session.commit()
        session.refresh(lead)

        # Create or link customer when manual lead is auto-qualified
        if lead.status == LeadStatus.QUALIFIED and not lead.customer_id:
            customer = find_or_create_customer(lead, session)
            lead.customer_id = customer.id
            session.add(lead)
            session.commit()
            session.refresh(lead)
            # Auto-create opportunity for quotable qualified lead
            from app.workflow import auto_create_opportunity
            auto_create_opportunity(customer.id, lead.id, session, current_user.id)

        # Create initial status history
        status_history = StatusHistory(
            lead_id=lead.id,
            new_status=lead.status,
            changed_by_id=current_user.id
        )
        session.add(status_history)
        session.commit()

        return enrich_lead_response(lead, session, current_user)
    except Exception as e:
        import traceback
        error_msg = f"Error creating lead: {str(e)}"
        print(error_msg, file=__import__('sys').stderr, flush=True)
        print(traceback.format_exc(), file=__import__('sys').stderr, flush=True)
        raise HTTPException(status_code=500, detail=error_msg)


@router.patch("/{lead_id}", response_model=LeadResponse)
async def update_lead(
    lead_id: int,
    lead_data: LeadUpdate,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    statement = select(Lead).where(Lead.id == lead_id)
    lead = session.exec(statement).first()
    
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    
    update_data = lead_data.dict(exclude_unset=True)
    advert_profile_id = update_data.get("facebook_advert_profile_id")
    if advert_profile_id is not None:
        advert_statement = select(FacebookAdvertProfile).where(
            FacebookAdvertProfile.id == advert_profile_id
        )
        advert_profile = session.exec(advert_statement).first()
        if not advert_profile:
            raise HTTPException(status_code=400, detail="Facebook advert profile not found")

    for field, value in update_data.items():
        setattr(lead, field, value)
    
    lead.updated_at = datetime.utcnow()
    session.add(lead)
    session.commit()
    session.refresh(lead)
    
    return enrich_lead_response(lead, session, current_user)


@router.post("/{lead_id}/transition", response_model=LeadResponse)
async def transition_lead_status(
    lead_id: int,
    transition: StatusTransitionRequest,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    statement = select(Lead).where(Lead.id == lead_id)
    lead = session.exec(statement).first()
    
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")

    if transition.new_status == LeadStatus.CLOSED:
        reason = (transition.override_reason or "").strip()
        if not reason:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"error": "CLOSE_REASON_REQUIRED", "message": "A reason is required to close this lead."},
            )
    
    is_override = transition.override_reason is not None and transition.override_reason.strip() != ""
    allowed, error = can_transition(
        current_user.role,
        lead.status,
        transition.new_status,
        lead,
        session,
        is_override=is_override
    )
    
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error
        )
    
    old_status = lead.status
    lead.status = transition.new_status
    lead.updated_at = datetime.utcnow()
    
    # Create or link customer when transitioning to QUALIFIED
    if transition.new_status == LeadStatus.QUALIFIED and not lead.customer_id:
        customer = find_or_create_customer(lead, session)
        lead.customer_id = customer.id

    if transition.new_status == LeadStatus.CLOSED:
        draft_stmt = select(Quote).where(
            Quote.lead_id == lead.id,
            Quote.status == QuoteStatus.DRAFT,
        )
        for q in list(session.exec(draft_stmt).all()):
            delete_quote_cascade(session, q.id)
    
    session.add(lead)
    
    # Log status change
    history_reason = (
        transition.override_reason.strip()
        if transition.new_status == LeadStatus.CLOSED
        else (transition.override_reason if is_override else None)
    )
    status_history = StatusHistory(
        lead_id=lead.id,
        old_status=old_status,
        new_status=transition.new_status,
        changed_by_id=current_user.id,
        override_reason=history_reason
    )
    session.add(status_history)
    session.commit()
    session.refresh(lead)
    
    return enrich_lead_response(lead, session, current_user)


@router.get("/{lead_id}/allowed-transitions")
async def get_allowed_transitions(
    lead_id: int,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    from app.workflow import get_allowed_transitions
    
    statement = select(Lead).where(Lead.id == lead_id)
    lead = session.exec(statement).first()
    
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    
    allowed = get_allowed_transitions(current_user.role, lead.status)
    
    # Director can override, so return all statuses except current
    if current_user.role.value == "DIRECTOR":
        all_statuses = [s for s in LeadStatus if s != lead.status]
        return {"allowed_transitions": [s.value for s in all_statuses], "can_override": True}
    
    return {"allowed_transitions": [s.value for s in allowed], "can_override": False}


@router.post("/{lead_id}/activities", response_model=ActivityResponse)
async def create_activity(
    lead_id: int,
    activity_data: ActivityCreate,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    statement = select(Lead).where(Lead.id == lead_id)
    lead = session.exec(statement).first()
    
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    
    # Get or create customer for activity
    customer_id = lead.customer_id
    if not customer_id:
        # Create customer for activity tracking (even for non-qualified leads)
        customer = find_or_create_customer(lead, session)
        lead.customer_id = customer.id
        customer_id = customer.id
        session.add(lead)
        session.commit()
    
    if not customer_id:
        raise HTTPException(status_code=400, detail="Unable to create customer for activity")
    
    activity = Activity(
        customer_id=customer_id,
        activity_type=activity_data.activity_type,
        notes=activity_data.notes,
        created_by_id=current_user.id
    )
    session.add(activity)
    session.commit()
    session.refresh(activity)
    
    # Auto-transition logic
    from app.workflow import auto_transition_lead_status, check_quote_prerequisites, find_leads_by_customer_id
    
    # NEW → ENGAGED: Transition when any activity is created
    if lead.status == LeadStatus.NEW:
        auto_transition_lead_status(
            lead.id,
            LeadStatus.ENGAGED,
            session,
            current_user.id,
            "Automatic transition: Activity created"
        )
        session.refresh(lead)
    
    # CONTACT_ATTEMPTED → ENGAGED: Keep existing logic for backward compatibility
    from app.workflow import ENGAGEMENT_PROOF_TYPES
    if activity.activity_type in ENGAGEMENT_PROOF_TYPES and lead.status == LeadStatus.CONTACT_ATTEMPTED:
        auto_transition_lead_status(
            lead.id,
            LeadStatus.ENGAGED,
            session,
            current_user.id,
            "Automatic transition: Engagement proof activity"
        )
        session.refresh(lead)
    
    # ENGAGED → QUALIFIED: Check if quote unlocks after activity creation
    if lead.status == LeadStatus.ENGAGED and lead.customer_id:
        statement = select(Customer).where(Customer.id == lead.customer_id)
        customer = session.exec(statement).first()
        if customer:
            can_quote, error = check_quote_prerequisites(customer, session)
            if can_quote:
                auto_transition_lead_status(
                    lead.id,
                    LeadStatus.QUALIFIED,
                    session,
                    current_user.id,
                    "Automatic transition: Quote unlocked"
                )
                session.refresh(lead)
                # Auto-create opportunity when lead becomes QUALIFIED
                from app.workflow import auto_create_opportunity
                auto_create_opportunity(
                    customer.id,
                    lead.id,
                    session,
                    current_user.id
                )
    
    return ActivityResponse(
        id=activity.id,
        customer_id=activity.customer_id,
        activity_type=activity.activity_type,
        notes=activity.notes,
        created_by_id=activity.created_by_id,
        created_at=activity.created_at,
        created_by_name=current_user.full_name
    )


@router.get("/{lead_id}/activities", response_model=List[ActivityResponse])
async def get_lead_activities(
    lead_id: int,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    statement = select(Lead).where(Lead.id == lead_id)
    lead = session.exec(statement).first()
    
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    
    # Get activities for the lead's customer, or return empty if no customer
    if not lead.customer_id:
        return []
    
    statement = select(Activity, User).join(User, Activity.created_by_id == User.id).where(
        Activity.customer_id == lead.customer_id
    ).order_by(Activity.created_at.desc())
    
    results = session.exec(statement).all()
    activities = []
    for activity, user in results:
        activities.append(ActivityResponse(
            id=activity.id,
            customer_id=activity.customer_id,
            activity_type=activity.activity_type,
            notes=activity.notes,
            created_by_id=activity.created_by_id,
            created_at=activity.created_at,
            created_by_name=user.full_name
        ))
    
    return activities


@router.get("/{lead_id}/status-history", response_model=List[StatusHistoryResponse])
async def get_status_history(
    lead_id: int,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    statement = select(StatusHistory, User).join(User, StatusHistory.changed_by_id == User.id).where(
        StatusHistory.lead_id == lead_id
    ).order_by(StatusHistory.created_at.desc())
    
    results = session.exec(statement).all()
    history = []
    for status_hist, user in results:
        history.append(StatusHistoryResponse(
            id=status_hist.id,
            lead_id=status_hist.lead_id,
            old_status=status_hist.old_status,
            new_status=status_hist.new_status,
            changed_by_id=status_hist.changed_by_id,
            override_reason=status_hist.override_reason,
            created_at=status_hist.created_at,
            changed_by_name=user.full_name
        ))
    
    return history


@router.get("/{lead_id}/customer", response_model=CustomerResponse)
async def get_lead_customer(
    lead_id: int,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """Get the customer associated with a lead."""
    statement = select(Lead).where(Lead.id == lead_id)
    lead = session.exec(statement).first()
    
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    
    if not lead.customer_id:
        raise HTTPException(status_code=404, detail="Lead has no associated customer")
    
    statement = select(Customer).where(Customer.id == lead.customer_id)
    customer = session.exec(statement).first()
    
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")
    
    return CustomerResponse(
        id=customer.id,
        customer_number=customer.customer_number,
        name=customer.name,
        email=customer.email,
        phone=customer.phone,
        address_line1=customer.address_line1,
        address_line2=customer.address_line2,
        city=customer.city,
        county=customer.county,
        postcode=customer.postcode,
        country=customer.country,
        customer_since=customer.customer_since,
        created_at=customer.created_at,
        updated_at=customer.updated_at,
        messenger_psid=customer.messenger_psid,
        source_system=customer.source_system,
    )


@router.get("/{lead_id}/quotes", response_model=List[QuoteResponse])
async def get_lead_quotes(
    lead_id: int,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """Get all quotes generated from this lead."""
    from app.routers.quotes import build_quote_response

    lead = session.exec(select(Lead).where(Lead.id == lead_id)).first()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")

    statement = (
        select(Quote)
        .where(
            Quote.lead_id == lead_id,
            Quote.status.notin_(QUOTE_LIST_EXCLUDED_STATUSES),
        )
        .order_by(Quote.created_at.desc())
    )
    quotes = session.exec(statement).all()

    result = []
    for quote in quotes:
        item_statement = select(QuoteItem).where(QuoteItem.quote_id == quote.id).order_by(QuoteItem.sort_order)
        quote_items = session.exec(item_statement).all()
        result.append(build_quote_response(quote, list(quote_items), session))

    return result
