from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session, select, or_
from typing import Optional, List
from app.database import get_session
from app.models import Customer, User, Activity, Quote, Lead, QuoteItem
from app.auth import get_current_user
from app.schemas import (
    CustomerResponse, CustomerUpdate, ActivityCreate, ActivityResponse, QuoteResponse, QuoteItemResponse
)
from app.workflow import check_quote_prerequisites
from datetime import datetime

router = APIRouter(prefix="/api/customers", tags=["customers"])


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
    from app.schemas import QuoteResponse
    from app.models import QuoteItem
    
    statement = select(Quote).where(Quote.customer_id == customer_id).order_by(Quote.created_at.desc())
    quotes = session.exec(statement).all()
    
    result = []
    for quote in quotes:
        item_statement = select(QuoteItem).where(QuoteItem.quote_id == quote.id).order_by(QuoteItem.sort_order)
        quote_items = session.exec(item_statement).all()
        
        result.append(QuoteResponse(
            id=quote.id,
            customer_id=quote.customer_id,
            quote_number=quote.quote_number,
            version=quote.version,
            status=quote.status,
            subtotal=quote.subtotal,
            discount_total=quote.discount_total,
            total_amount=quote.total_amount,
            currency=quote.currency,
            valid_until=quote.valid_until,
            terms_and_conditions=quote.terms_and_conditions,
            notes=quote.notes,
            created_by_id=quote.created_by_id,
            sent_at=quote.sent_at,
            viewed_at=quote.viewed_at,
            accepted_at=quote.accepted_at,
            created_at=quote.created_at,
            updated_at=quote.updated_at,
            items=[QuoteItemResponse(**item.dict()) for item in quote_items]
        ))
    
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
        
        statement = select(Activity, User).join(User, Activity.created_by_id == User.id).where(
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
                created_by_name=user.full_name
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
