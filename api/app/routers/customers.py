from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session, select, or_
from typing import Optional, List
from app.database import get_session
from app.models import Customer, User, Activity, Quote, Lead, QuoteItem, StatusHistory, Email, QuoteEmail, EmailDirection, QuoteStatus
from app.auth import get_current_user
from app.schemas import (
    CustomerResponse, CustomerUpdate, ActivityCreate, ActivityResponse, QuoteResponse, QuoteItemResponse,
    CustomerHistoryResponse, CustomerHistoryEvent, CustomerHistoryEventType
)
from app.workflow import check_quote_prerequisites
from datetime import datetime

router = APIRouter(prefix="/api/customers", tags=["customers"])


def quote_item_to_response(item: QuoteItem) -> QuoteItemResponse:
    """Convert a QuoteItem SQLModel instance to QuoteItemResponse."""
    return QuoteItemResponse(
        id=item.id,
        quote_id=item.quote_id,
        product_id=item.product_id,
        description=item.description,
        quantity=item.quantity,
        unit_price=item.unit_price,
        line_total=item.line_total,
        discount_amount=item.discount_amount,
        final_line_total=item.final_line_total,
        sort_order=item.sort_order,
        is_custom=item.is_custom
    )


@router.get("", response_model=List[CustomerResponse])
async def get_customers(
    search: Optional[str] = Query(None),
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """Get all customers."""
    statement = select(Customer)
    
    if search:
        search_term = f"%{search}%"
        statement = statement.where(
            or_(
                Customer.name.ilike(search_term),
                Customer.email.ilike(search_term),
                Customer.phone.ilike(search_term),
                Customer.customer_number.ilike(search_term),
                Customer.postcode.ilike(search_term)
            )
        )
    
    statement = statement.order_by(Customer.created_at.desc())
    customers = session.exec(statement).all()
    
    return [
        CustomerResponse(
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
            updated_at=customer.updated_at
        )
        for customer in customers
    ]


@router.get("/{customer_id}", response_model=CustomerResponse)
async def get_customer(
    customer_id: int,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """Get customer details."""
    statement = select(Customer).where(Customer.id == customer_id)
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
        updated_at=customer.updated_at
    )


@router.get("/{customer_id}/quote-status")
async def get_customer_quote_status(
    customer_id: int,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """Get quote lock status for customer."""
    import sys
    statement = select(Customer).where(Customer.id == customer_id)
    customer = session.exec(statement).first()
    
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")
    
    # Debug: Check what activities exist
    from app.models import Activity
    from app.workflow import ENGAGEMENT_PROOF_TYPES
    debug_statement = select(Activity).where(Activity.customer_id == customer.id)
    all_activities = session.exec(debug_statement).all()
    engagement_statement = select(Activity).where(
        Activity.customer_id == customer.id,
        Activity.activity_type.in_(list(ENGAGEMENT_PROOF_TYPES))
    )
    engagement_activities = session.exec(engagement_statement).all()
    
    print(f"[DEBUG] Customer {customer_id} - All activities: {len(all_activities)}", file=sys.stderr, flush=True)
    print(f"[DEBUG] Customer {customer_id} - Engagement activities: {len(engagement_activities)}", file=sys.stderr, flush=True)
    for act in engagement_activities:
        print(f"[DEBUG] Engagement activity: {act.activity_type} (id={act.id})", file=sys.stderr, flush=True)
    
    can_quote, error = check_quote_prerequisites(customer, session)
    
    return {
        "quote_locked": not can_quote,
        "quote_lock_reason": error if not can_quote else None
    }


@router.patch("/{customer_id}", response_model=CustomerResponse)
async def update_customer(
    customer_id: int,
    customer_data: CustomerUpdate,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """Update customer profile."""
    statement = select(Customer).where(Customer.id == customer_id)
    customer = session.exec(statement).first()
    
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")
    
    update_data = customer_data.dict(exclude_unset=True)
    for field, value in update_data.items():
        setattr(customer, field, value)
    
    customer.updated_at = datetime.utcnow()
    session.add(customer)
    session.commit()
    session.refresh(customer)
    
    # Check if quote unlocks and transition ENGAGED → QUALIFIED
    from app.workflow import check_quote_prerequisites, auto_transition_lead_status, find_leads_by_customer_id, auto_create_opportunity
    can_quote, error = check_quote_prerequisites(customer, session)
    if can_quote:
        # Find all ENGAGED leads for this customer and transition to QUALIFIED
        leads = find_leads_by_customer_id(customer.id, session)
        for lead in leads:
            if lead.status == LeadStatus.ENGAGED:
                auto_transition_lead_status(
                    lead.id,
                    LeadStatus.QUALIFIED,
                    session,
                    current_user.id,
                    "Automatic transition: Quote unlocked"
                )
                # Auto-create opportunity when lead becomes QUALIFIED
                auto_create_opportunity(
                    customer.id,
                    lead.id,
                    session,
                    current_user.id
                )
    
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
        updated_at=customer.updated_at
    )


@router.get("/{customer_id}/quotes")
async def get_customer_quotes(
    customer_id: int,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """Get all quotes for a customer."""
    from app.routers.quotes import build_quote_response
    from app.models import QuoteItem

    statement = select(Quote).where(Quote.customer_id == customer_id).order_by(Quote.created_at.desc())
    quotes = session.exec(statement).all()

    result = []
    for quote in quotes:
        item_statement = select(QuoteItem).where(QuoteItem.quote_id == quote.id).order_by(QuoteItem.sort_order)
        quote_items = session.exec(item_statement).all()
        result.append(build_quote_response(quote, list(quote_items), session))

    return result


@router.get("/{customer_id}/activities", response_model=List[ActivityResponse])
async def get_customer_activities(
    customer_id: int,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """Get all activities for a customer."""
    try:
        statement = select(Customer).where(Customer.id == customer_id)
        customer = session.exec(statement).first()
        
        if not customer:
            raise HTTPException(status_code=404, detail="Customer not found")
        
        statement = select(Activity, User).outerjoin(User, Activity.created_by_id == User.id).where(
            Activity.customer_id == customer_id
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
                created_by_name=user.full_name if user else "Unknown"
            ))
        
        return activities
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        error_msg = f"Error fetching activities: {str(e)}"
        print(error_msg, file=__import__('sys').stderr, flush=True)
        print(traceback.format_exc(), file=__import__('sys').stderr, flush=True)
        raise HTTPException(status_code=500, detail=error_msg)


@router.post("/{customer_id}/activities", response_model=ActivityResponse)
async def create_customer_activity(
    customer_id: int,
    activity_data: ActivityCreate,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """Create an activity for a customer."""
    try:
        statement = select(Customer).where(Customer.id == customer_id)
        customer = session.exec(statement).first()
        
        if not customer:
            raise HTTPException(status_code=404, detail="Customer not found")
        
        activity = Activity(
            customer_id=customer_id,
            activity_type=activity_data.activity_type,
            notes=activity_data.notes,
            created_by_id=current_user.id
        )
        session.add(activity)
        session.commit()
        session.refresh(activity)
        
        # Check if quote unlocks and transition ENGAGED → QUALIFIED
        from app.workflow import check_quote_prerequisites, auto_transition_lead_status, find_leads_by_customer_id, auto_create_opportunity
        can_quote, error = check_quote_prerequisites(customer, session)
        if can_quote:
            # Find all ENGAGED leads for this customer and transition to QUALIFIED
            leads = find_leads_by_customer_id(customer.id, session)
            for lead in leads:
                if lead.status == LeadStatus.ENGAGED:
                    auto_transition_lead_status(
                        lead.id,
                        LeadStatus.QUALIFIED,
                        session,
                        current_user.id,
                        "Automatic transition: Quote unlocked"
                    )
                    # Auto-create opportunity when lead becomes QUALIFIED
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
    except Exception as e:
        import traceback
        error_msg = f"Error creating activity: {str(e)}"
        print(error_msg, file=__import__('sys').stderr, flush=True)
        print(traceback.format_exc(), file=__import__('sys').stderr, flush=True)
        session.rollback()
        raise HTTPException(status_code=500, detail=error_msg)


@router.get("/{customer_id}/leads")
async def get_customer_leads(
    customer_id: int,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """Get all leads associated with a customer."""
    from app.schemas import LeadResponse
    from app.routers.leads import enrich_lead_response
    
    statement = select(Customer).where(Customer.id == customer_id)
    customer = session.exec(statement).first()
    
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")
    
    statement = select(Lead).where(Lead.customer_id == customer_id).order_by(Lead.created_at.desc())
    leads = session.exec(statement).all()
    
    return [enrich_lead_response(lead, session, current_user) for lead in leads]


@router.get("/{customer_id}/history", response_model=CustomerHistoryResponse)
async def get_customer_history(
    customer_id: int,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """Get unified customer history timeline with all events."""
    # Verify customer exists
    statement = select(Customer).where(Customer.id == customer_id)
    customer = session.exec(statement).first()
    
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")
    
    events = []
    
    # 1. Customer creation event
    events.append(CustomerHistoryEvent(
        event_type=CustomerHistoryEventType.CUSTOMER_CREATED,
        timestamp=customer.created_at,
        title="Customer Created",
        description=f"Customer {customer.customer_number} was created",
        metadata={"customer_number": customer.customer_number},
        created_by_id=None,
        created_by_name=None
    ))
    
    # 2. Customer updates (track via updated_at if different from created_at)
    if customer.updated_at and customer.updated_at != customer.created_at:
        events.append(CustomerHistoryEvent(
            event_type=CustomerHistoryEventType.CUSTOMER_UPDATED,
            timestamp=customer.updated_at,
            title="Customer Profile Updated",
            description="Customer profile information was updated",
            metadata={},
            created_by_id=None,
            created_by_name=None
        ))
    
    # 3. Activities
    statement = select(Activity, User).outerjoin(User, Activity.created_by_id == User.id).where(
        Activity.customer_id == customer_id
    ).order_by(Activity.created_at)
    activity_results = session.exec(statement).all()
    
    for activity, user in activity_results:
        activity_type_name = activity.activity_type.value.replace("_", " ").title()
        events.append(CustomerHistoryEvent(
            event_type=CustomerHistoryEventType.ACTIVITY,
            timestamp=activity.created_at,
            title=activity_type_name,
            description=activity.notes or f"{activity_type_name} activity recorded",
            metadata={"activity_type": activity.activity_type.value, "activity_id": activity.id},
            created_by_id=activity.created_by_id,
            created_by_name=user.full_name if user else "Unknown"
        ))
    
    # 4. Lead status changes (for leads linked to this customer)
    statement = select(StatusHistory, User, Lead).join(
        User, StatusHistory.changed_by_id == User.id
    ).join(
        Lead, StatusHistory.lead_id == Lead.id
    ).where(
        Lead.customer_id == customer_id
    ).order_by(StatusHistory.created_at)
    status_results = session.exec(statement).all()
    
    for status_hist, user, lead in status_results:
        old_status = status_hist.old_status.value if status_hist.old_status else "New"
        new_status = status_hist.new_status.value
        
        # Special handling for QUALIFIED status
        if status_hist.new_status.value == "QUALIFIED":
            events.append(CustomerHistoryEvent(
                event_type=CustomerHistoryEventType.LEAD_QUALIFIED,
                timestamp=status_hist.created_at,
                title="Lead Qualified",
                description=f"Lead '{lead.name}' was qualified and linked to this customer",
                metadata={
                    "lead_id": lead.id,
                    "lead_name": lead.name,
                    "old_status": old_status,
                    "new_status": new_status,
                    "override_reason": status_hist.override_reason
                },
                created_by_id=status_hist.changed_by_id,
                created_by_name=user.full_name if user else "Unknown"
            ))
        else:
            events.append(CustomerHistoryEvent(
                event_type=CustomerHistoryEventType.LEAD_STATUS_CHANGE,
                timestamp=status_hist.created_at,
                title="Lead Status Changed",
                description=f"Lead '{lead.name}' status changed from {old_status} to {new_status}",
                metadata={
                    "lead_id": lead.id,
                    "lead_name": lead.name,
                    "old_status": old_status,
                    "new_status": new_status,
                    "override_reason": status_hist.override_reason
                },
                created_by_id=status_hist.changed_by_id,
                created_by_name=user.full_name if user else "Unknown"
            ))
    
    # 5. Quotes/Opportunities
    statement = select(Quote, User).outerjoin(User, Quote.created_by_id == User.id).where(
        Quote.customer_id == customer_id
    ).order_by(Quote.created_at)
    quote_results = session.exec(statement).all()
    
    for quote, user in quote_results:
        # Quote created
        events.append(CustomerHistoryEvent(
            event_type=CustomerHistoryEventType.QUOTE_CREATED,
            timestamp=quote.created_at,
            title="Quote Created",
            description=f"Quote {quote.quote_number} was created",
            metadata={
                "quote_id": quote.id,
                "quote_number": quote.quote_number,
                "total_amount": float(quote.total_amount) if quote.total_amount else 0
            },
            created_by_id=quote.created_by_id,
            created_by_name=user.full_name if user else "Unknown"
        ))
        
        # Opportunity created (if it's in DISCOVERY stage, it's an opportunity)
        if quote.opportunity_stage and quote.opportunity_stage.value == "DISCOVERY":
            events.append(CustomerHistoryEvent(
                event_type=CustomerHistoryEventType.OPPORTUNITY_CREATED,
                timestamp=quote.created_at,
                title="Opportunity Created",
                description=f"New opportunity created with quote {quote.quote_number}",
                metadata={
                    "quote_id": quote.id,
                    "quote_number": quote.quote_number,
                    "stage": quote.opportunity_stage.value
                },
                created_by_id=quote.created_by_id,
                created_by_name=user.full_name if user else "Unknown"
            ))
        
        # Quote sent
        if quote.sent_at:
            events.append(CustomerHistoryEvent(
                event_type=CustomerHistoryEventType.QUOTE_SENT,
                timestamp=quote.sent_at,
                title="Quote Sent",
                description=f"Quote {quote.quote_number} was sent to customer",
                metadata={
                    "quote_id": quote.id,
                    "quote_number": quote.quote_number
                },
                created_by_id=quote.created_by_id,
                created_by_name=user.full_name if user else "Unknown"
            ))
        
        # Quote viewed
        if quote.viewed_at:
            events.append(CustomerHistoryEvent(
                event_type=CustomerHistoryEventType.QUOTE_VIEWED,
                timestamp=quote.viewed_at,
                title="Quote Viewed",
                description=f"Customer viewed quote {quote.quote_number}",
                metadata={
                    "quote_id": quote.id,
                    "quote_number": quote.quote_number
                },
                created_by_id=None,
                created_by_name=None
            ))
        
        # Quote accepted/rejected/expired
        if quote.status == QuoteStatus.ACCEPTED and quote.accepted_at:
            events.append(CustomerHistoryEvent(
                event_type=CustomerHistoryEventType.QUOTE_ACCEPTED,
                timestamp=quote.accepted_at,
                title="Quote Accepted",
                description=f"Quote {quote.quote_number} was accepted by customer",
                metadata={
                    "quote_id": quote.id,
                    "quote_number": quote.quote_number,
                    "total_amount": float(quote.total_amount) if quote.total_amount else 0
                },
                created_by_id=None,
                created_by_name=None
            ))
        elif quote.status == QuoteStatus.REJECTED:
            events.append(CustomerHistoryEvent(
                event_type=CustomerHistoryEventType.QUOTE_REJECTED,
                timestamp=quote.updated_at,
                title="Quote Rejected",
                description=f"Quote {quote.quote_number} was rejected",
                metadata={
                    "quote_id": quote.id,
                    "quote_number": quote.quote_number
                },
                created_by_id=None,
                created_by_name=None
            ))
        elif quote.status == QuoteStatus.EXPIRED:
            events.append(CustomerHistoryEvent(
                event_type=CustomerHistoryEventType.QUOTE_EXPIRED,
                timestamp=quote.updated_at,
                title="Quote Expired",
                description=f"Quote {quote.quote_number} has expired",
                metadata={
                    "quote_id": quote.id,
                    "quote_number": quote.quote_number
                },
                created_by_id=None,
                created_by_name=None
            ))
        
        # Quote updated (if updated_at differs from created_at and not already covered)
        if quote.updated_at and quote.updated_at != quote.created_at and not quote.sent_at and not quote.viewed_at and not quote.accepted_at:
            events.append(CustomerHistoryEvent(
                event_type=CustomerHistoryEventType.QUOTE_UPDATED,
                timestamp=quote.updated_at,
                title="Quote Updated",
                description=f"Quote {quote.quote_number} was updated",
                metadata={
                    "quote_id": quote.id,
                    "quote_number": quote.quote_number
                },
                created_by_id=quote.created_by_id,
                created_by_name=user.full_name if user else "Unknown"
            ))
    
    # 6. Quote emails (QuoteEmail records)
    statement = select(QuoteEmail, Quote).join(Quote, QuoteEmail.quote_id == Quote.id).where(
        Quote.customer_id == customer_id
    ).order_by(QuoteEmail.sent_at)
    quote_email_results = session.exec(statement).all()
    
    for quote_email, quote in quote_email_results:
        events.append(CustomerHistoryEvent(
            event_type=CustomerHistoryEventType.QUOTE_SENT,
            timestamp=quote_email.sent_at,
            title="Quote Email Sent",
            description=f"Quote {quote.quote_number} email sent to {quote_email.to_email}",
            metadata={
                "quote_id": quote.id,
                "quote_number": quote.quote_number,
                "to_email": quote_email.to_email,
                "email_id": quote_email.id
            },
            created_by_id=None,
            created_by_name=None
        ))
    
    # 7. Regular emails (Email records)
    statement = select(Email, User).outerjoin(User, Email.created_by_id == User.id).where(
        Email.customer_id == customer_id
    ).order_by(Email.created_at)
    email_results = session.exec(statement).all()
    
    for email, user in email_results:
        if email.direction == EmailDirection.SENT:
            events.append(CustomerHistoryEvent(
                event_type=CustomerHistoryEventType.EMAIL_SENT,
                timestamp=email.sent_at or email.created_at,
                title="Email Sent",
                description=f"Email sent to {email.to_email}: {email.subject}",
                metadata={
                    "email_id": email.id,
                    "to_email": email.to_email,
                    "subject": email.subject
                },
                created_by_id=email.created_by_id,
                created_by_name=user.full_name if user else "Unknown"
            ))
        elif email.direction == EmailDirection.RECEIVED:
            events.append(CustomerHistoryEvent(
                event_type=CustomerHistoryEventType.EMAIL_RECEIVED,
                timestamp=email.received_at or email.created_at,
                title="Email Received",
                description=f"Email received from {email.from_email}: {email.subject}",
                metadata={
                    "email_id": email.id,
                    "from_email": email.from_email,
                    "subject": email.subject
                },
                created_by_id=None,
                created_by_name=None
            ))
    
    # Sort all events by timestamp (most recent first)
    events.sort(key=lambda x: x.timestamp, reverse=True)
    
    return CustomerHistoryResponse(events=events)
