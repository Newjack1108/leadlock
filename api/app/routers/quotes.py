from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlmodel import Session, select, or_, and_
from typing import List, Optional
from app.database import get_session
from app.models import Quote, QuoteItem, Customer, User, QuoteEmail, Email, EmailDirection, Activity, ActivityType, CompanySettings, Lead, LeadStatus, QuoteStatus, OpportunityStage, LossCategory
from app.auth import get_current_user
from app.schemas import (
    QuoteCreate, QuoteUpdate, QuoteResponse, QuoteItemCreate, QuoteItemResponse,
    QuoteEmailSendRequest, QuoteEmailSendResponse, OpportunityWonRequest, OpportunityLostRequest
)
from app.quote_email_service import send_quote_email
from app.quote_pdf_service import generate_quote_pdf
from datetime import datetime
from decimal import Decimal

router = APIRouter(prefix="/api/quotes", tags=["quotes"])


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


def generate_quote_number(session: Session) -> str:
    """Generate a unique quote number like QT-2024-001."""
    from datetime import date
    year = date.today().year
    
    # Find the highest quote number for this year
    statement = select(Quote).where(Quote.quote_number.like(f"QT-{year}-%"))
    quotes = session.exec(statement).all()
    
    if not quotes:
        return f"QT-{year}-001"
    
    # Extract numbers and find max
    numbers = []
    for quote in quotes:
        try:
            num = int(quote.quote_number.split('-')[-1])
            numbers.append(num)
        except (ValueError, IndexError):
            continue
    
    if not numbers:
        return f"QT-{year}-001"
    
    next_num = max(numbers) + 1
    return f"QT-{year}-{next_num:03d}"


@router.post("", response_model=QuoteResponse)
async def create_quote(
    quote_data: QuoteCreate,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """Create a new quote."""
    try:
        # Verify customer exists
        if not quote_data.customer_id:
            raise HTTPException(status_code=400, detail="customer_id is required")
        
        statement = select(Customer).where(Customer.id == quote_data.customer_id)
        customer = session.exec(statement).first()
        
        if not customer:
            raise HTTPException(status_code=404, detail="Customer not found")
        
        # Generate quote number if not provided
        quote_number = quote_data.quote_number or generate_quote_number(session)
        
        # Calculate totals
        subtotal = Decimal(0)
        items = []
        
        for item_data in quote_data.items:
            # Ensure Decimal conversion
            quantity = Decimal(str(item_data.quantity))
            unit_price = Decimal(str(item_data.unit_price))
            line_total = quantity * unit_price
            subtotal += line_total
            
            item = QuoteItem(
                quote_id=0,  # Will be set after quote is created
                product_id=item_data.product_id,
                description=item_data.description,
                quantity=quantity,
                unit_price=unit_price,
                line_total=line_total,
                discount_amount=Decimal(0),
                final_line_total=line_total,
                sort_order=item_data.sort_order or 0,
                is_custom=item_data.is_custom if item_data.is_custom is not None else False
            )
            items.append(item)
    
        # Calculate deposit and balance
        # Default to 50% deposit if not provided
        total_amount = subtotal  # No discounts applied yet
        if quote_data.deposit_amount is not None:
            deposit_amount = Decimal(str(quote_data.deposit_amount))
        else:
            # Default to 50% of total
            deposit_amount = total_amount * Decimal("0.5")
        
        # Ensure deposit doesn't exceed total
        if deposit_amount > total_amount:
            deposit_amount = total_amount
        
        balance_amount = total_amount - deposit_amount
        
        # Create quote
        quote = Quote(
            customer_id=quote_data.customer_id,
            quote_number=quote_number,
            version=quote_data.version or 1,
            subtotal=subtotal,
            discount_total=Decimal(0),
            total_amount=total_amount,
            deposit_amount=deposit_amount,
            balance_amount=balance_amount,
            currency="GBP",
            valid_until=quote_data.valid_until,
            terms_and_conditions=quote_data.terms_and_conditions,
            notes=quote_data.notes,
            created_by_id=current_user.id
        )
        session.add(quote)
        session.commit()
        session.refresh(quote)
        
        # Add items with quote_id
        for item in items:
            item.quote_id = quote.id
            session.add(item)
        session.commit()
        
        # QUALIFIED → QUOTED: Transition lead when quote is created
        from app.workflow import auto_transition_lead_status, find_leads_by_customer_id
        leads = find_leads_by_customer_id(quote.customer_id, session)
        for lead in leads:
            if lead.status == LeadStatus.QUALIFIED:
                auto_transition_lead_status(
                    lead.id,
                    LeadStatus.QUOTED,
                    session,
                    current_user.id,
                    "Automatic transition: Quote created"
                )
        
        # Refresh to get items
        session.refresh(quote)
        statement = select(QuoteItem).where(QuoteItem.quote_id == quote.id)
        quote_items = session.exec(statement).all()
        
        return QuoteResponse(
            id=quote.id,
            customer_id=quote.customer_id,
            quote_number=quote.quote_number,
            version=quote.version,
            status=quote.status,
            subtotal=quote.subtotal,
            discount_total=quote.discount_total,
            total_amount=quote.total_amount,
            deposit_amount=quote.deposit_amount,
            balance_amount=quote.balance_amount,
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
            items=[quote_item_to_response(item) for item in quote_items],
            opportunity_stage=quote.opportunity_stage,
            close_probability=quote.close_probability,
            expected_close_date=quote.expected_close_date,
            next_action=quote.next_action,
            next_action_due_date=quote.next_action_due_date,
            loss_reason=quote.loss_reason,
            loss_category=quote.loss_category,
            owner_id=quote.owner_id
        )
    except Exception as e:
        import traceback
        error_detail = str(e)
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Error creating quote: {error_detail}")


@router.get("", response_model=List[QuoteResponse])
async def get_all_quotes(
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """Get all quotes."""
    statement = select(Quote).order_by(Quote.created_at.desc())
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
            deposit_amount=quote.deposit_amount,
            balance_amount=quote.balance_amount,
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
            items=[quote_item_to_response(item) for item in quote_items],
            opportunity_stage=quote.opportunity_stage,
            close_probability=quote.close_probability,
            expected_close_date=quote.expected_close_date,
            next_action=quote.next_action,
            next_action_due_date=quote.next_action_due_date,
            loss_reason=quote.loss_reason,
            loss_category=quote.loss_category,
            owner_id=quote.owner_id
        ))
    
    return result


# Opportunity Management Endpoints (must be before /{quote_id} to avoid route conflicts)

@router.get("/opportunities", response_model=List[QuoteResponse])
async def get_opportunities(
    stage: Optional[OpportunityStage] = None,
    owner_id: Optional[int] = None,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """Get all opportunities (quotes with opportunity_stage set)."""
    statement = select(Quote).where(Quote.opportunity_stage.isnot(None))
    
    if stage:
        statement = statement.where(Quote.opportunity_stage == stage)
    if owner_id:
        statement = statement.where(Quote.owner_id == owner_id)
    
    statement = statement.order_by(Quote.created_at.desc())
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
            deposit_amount=quote.deposit_amount,
            balance_amount=quote.balance_amount,
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
            items=[quote_item_to_response(item) for item in quote_items],
            opportunity_stage=quote.opportunity_stage,
            close_probability=quote.close_probability,
            expected_close_date=quote.expected_close_date,
            next_action=quote.next_action,
            next_action_due_date=quote.next_action_due_date,
            loss_reason=quote.loss_reason,
            loss_category=quote.loss_category,
            owner_id=quote.owner_id
        ))
    
    return result


@router.get("/opportunities/stale", response_model=List[QuoteResponse])
async def get_stale_opportunities(
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """Get opportunities that need attention (overdue next actions, stale, etc.)."""
    from datetime import datetime, timedelta
    
    now = datetime.utcnow()
    
    # Find opportunities with overdue next actions or expected close dates
    statement = select(Quote).where(
        and_(
            Quote.opportunity_stage.isnot(None),
            Quote.opportunity_stage.notin_([OpportunityStage.WON, OpportunityStage.LOST]),
            or_(
                and_(Quote.next_action_due_date.isnot(None), Quote.next_action_due_date < now),
                and_(Quote.expected_close_date.isnot(None), Quote.expected_close_date < now)
            )
        )
    ).order_by(Quote.next_action_due_date.asc())
    
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
            deposit_amount=quote.deposit_amount,
            balance_amount=quote.balance_amount,
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
            items=[quote_item_to_response(item) for item in quote_items],
            opportunity_stage=quote.opportunity_stage,
            close_probability=quote.close_probability,
            expected_close_date=quote.expected_close_date,
            next_action=quote.next_action,
            next_action_due_date=quote.next_action_due_date,
            loss_reason=quote.loss_reason,
            loss_category=quote.loss_category,
            owner_id=quote.owner_id
        ))
    
    return result


@router.get("/opportunities/{quote_id}", response_model=QuoteResponse)
async def get_opportunity(
    quote_id: int,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """Get a specific opportunity by quote ID."""
    statement = select(Quote).where(Quote.id == quote_id)
    quote = session.exec(statement).first()
    
    if not quote:
        raise HTTPException(status_code=404, detail="Opportunity not found")
    
    if quote.opportunity_stage is None:
        raise HTTPException(status_code=404, detail="Quote is not an opportunity")
    
    statement = select(QuoteItem).where(QuoteItem.quote_id == quote.id).order_by(QuoteItem.sort_order)
    quote_items = session.exec(statement).all()
    
    return QuoteResponse(
        id=quote.id,
        customer_id=quote.customer_id,
        quote_number=quote.quote_number,
        version=quote.version,
        status=quote.status,
        subtotal=quote.subtotal,
        discount_total=quote.discount_total,
        total_amount=quote.total_amount,
        deposit_amount=quote.deposit_amount,
        balance_amount=quote.balance_amount,
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
        items=[quote_item_to_response(item) for item in quote_items],
        opportunity_stage=quote.opportunity_stage,
        close_probability=quote.close_probability,
        expected_close_date=quote.expected_close_date,
        next_action=quote.next_action,
        next_action_due_date=quote.next_action_due_date,
        loss_reason=quote.loss_reason,
        loss_category=quote.loss_category,
        owner_id=quote.owner_id
    )


@router.get("/{quote_id}", response_model=QuoteResponse)
async def get_quote(
    quote_id: int,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """Get quote details."""
    statement = select(Quote).where(Quote.id == quote_id)
    quote = session.exec(statement).first()
    
    if not quote:
        raise HTTPException(status_code=404, detail="Quote not found")
    
    statement = select(QuoteItem).where(QuoteItem.quote_id == quote.id).order_by(QuoteItem.sort_order)
    quote_items = session.exec(statement).all()
    
    return QuoteResponse(
        id=quote.id,
        customer_id=quote.customer_id,
        quote_number=quote.quote_number,
        version=quote.version,
        status=quote.status,
        subtotal=quote.subtotal,
        discount_total=quote.discount_total,
        total_amount=quote.total_amount,
        deposit_amount=quote.deposit_amount,
        balance_amount=quote.balance_amount,
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
        items=[quote_item_to_response(item) for item in quote_items],
        opportunity_stage=quote.opportunity_stage,
        close_probability=quote.close_probability,
        expected_close_date=quote.expected_close_date,
        next_action=quote.next_action,
        next_action_due_date=quote.next_action_due_date,
        loss_reason=quote.loss_reason,
        loss_category=quote.loss_category,
        owner_id=quote.owner_id
    )


@router.get("/customers/{customer_id}", response_model=List[QuoteResponse])
async def get_customer_quotes(
    customer_id: int,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """Get all quotes for a customer."""
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
            deposit_amount=quote.deposit_amount,
            balance_amount=quote.balance_amount,
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
            items=[quote_item_to_response(item) for item in quote_items],
            opportunity_stage=quote.opportunity_stage,
            close_probability=quote.close_probability,
            expected_close_date=quote.expected_close_date,
            next_action=quote.next_action,
            next_action_due_date=quote.next_action_due_date,
            loss_reason=quote.loss_reason,
            loss_category=quote.loss_category,
            owner_id=quote.owner_id
        ))
    
    return result


@router.post("/{quote_id}/send-email", response_model=QuoteEmailSendResponse)
async def send_quote_email_endpoint(
    quote_id: int,
    email_data: QuoteEmailSendRequest,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """Send a quote as an email with PDF attachment."""
    try:
        # Get quote
        statement = select(Quote).where(Quote.id == quote_id)
        quote = session.exec(statement).first()
        
        if not quote:
            raise HTTPException(status_code=404, detail="Quote not found")
        
        # Get customer
        if not quote.customer_id:
            raise HTTPException(status_code=400, detail="Quote must be associated with a customer")
        
        statement = select(Customer).where(Customer.id == quote.customer_id)
        customer = session.exec(statement).first()
        
        if not customer:
            raise HTTPException(status_code=404, detail="Customer not found")
        
        # Check if user has email
        if not current_user.email:
            raise HTTPException(status_code=400, detail="User email is not configured")
        
        # Send quote email
        success, message_id, error, pdf_buffer, email_subject, email_body_html = send_quote_email(
            quote=quote,
            customer=customer,
            to_email=email_data.to_email,
            session=session,
            template_id=email_data.template_id,
            cc=email_data.cc,
            bcc=email_data.bcc,
            custom_message=email_data.custom_message,
            user_id=current_user.id
        )
        
        if not success:
            raise HTTPException(status_code=500, detail=f"Failed to send quote email: {error}")
        
        # Use rendered subject and body_html, fallback to defaults if None
        final_subject = email_subject or f"Quote {quote.quote_number}"
        final_body_html = email_body_html or f"<p>Please find attached your quote {quote.quote_number}.</p>"
        
        # Create Email record
        email_record = Email(
            customer_id=quote.customer_id,
            message_id=message_id,
            direction=EmailDirection.SENT,
            from_email=current_user.email,
            to_email=email_data.to_email,
            cc=email_data.cc,
            bcc=email_data.bcc,
            subject=final_subject,
            body_html=None,  # Will be stored in QuoteEmail
            sent_at=datetime.utcnow(),
            created_by_id=current_user.id
        )
        session.add(email_record)
        session.commit()
        session.refresh(email_record)
        
        # Create QuoteEmail record
        quote_email = QuoteEmail(
            quote_id=quote.id,
            to_email=email_data.to_email,
            subject=final_subject,
            body_html=final_body_html,  # Template rendered content
            tracking_id=message_id or f"quote-{quote.id}-{datetime.utcnow().timestamp()}"
        )
        session.add(quote_email)
        
        # Update quote sent_at
        quote.sent_at = datetime.utcnow()
        session.add(quote)
        
        session.commit()
        session.refresh(quote_email)
        
        # Create EMAIL_SENT activity
        activity = Activity(
            customer_id=quote.customer_id,
            activity_type=ActivityType.EMAIL_SENT,
            notes=f"Quote {quote.quote_number} sent to {email_data.to_email}",
            created_by_id=current_user.id
        )
        session.add(activity)
        session.commit()
        
        return QuoteEmailSendResponse(
            email_id=email_record.id,
            quote_email_id=quote_email.id,
            message="Quote email sent successfully"
        )
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        error_msg = f"Error sending quote email: {str(e)}"
        print(error_msg, file=__import__('sys').stderr, flush=True)
        print(traceback.format_exc(), file=__import__('sys').stderr, flush=True)
        session.rollback()
        raise HTTPException(status_code=500, detail=error_msg)


@router.patch("/{quote_id}", response_model=QuoteResponse)
async def update_quote(
    quote_id: int,
    quote_data: QuoteUpdate,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """Update a quote/opportunity."""
    statement = select(Quote).where(Quote.id == quote_id)
    quote = session.exec(statement).first()
    
    if not quote:
        raise HTTPException(status_code=404, detail="Quote not found")
    
    old_status = quote.status
    old_stage = quote.opportunity_stage
    
    # Update quote fields
    update_data = quote_data.dict(exclude_unset=True)
    for field, value in update_data.items():
        setattr(quote, field, value)
    
    # Mandatory next action validation (for open opportunities)
    if quote.opportunity_stage and quote.opportunity_stage not in [OpportunityStage.WON, OpportunityStage.LOST]:
        if not quote.next_action or not quote.next_action_due_date:
            raise HTTPException(
                status_code=400,
                detail="next_action and next_action_due_date are required for open opportunities"
            )
    
    # Set accepted_at if status changes to ACCEPTED
    if quote_data.status == QuoteStatus.ACCEPTED and old_status != QuoteStatus.ACCEPTED:
        quote.accepted_at = datetime.utcnow()
    
    # Update opportunity stage based on quote status if stage not explicitly set
    if quote_data.status and not quote_data.opportunity_stage:
        if quote_data.status == QuoteStatus.ACCEPTED:
            quote.opportunity_stage = OpportunityStage.WON
        elif quote_data.status == QuoteStatus.REJECTED:
            quote.opportunity_stage = OpportunityStage.LOST
        elif quote_data.status == QuoteStatus.SENT and quote.opportunity_stage == OpportunityStage.CONCEPT:
            quote.opportunity_stage = OpportunityStage.QUOTE_SENT
    
    quote.updated_at = datetime.utcnow()
    session.add(quote)
    session.commit()
    session.refresh(quote)
    
    # Update opportunity stage based on quote status if stage not explicitly set
    if quote_data.status and not quote_data.opportunity_stage:
        if quote_data.status == QuoteStatus.ACCEPTED:
            quote.opportunity_stage = OpportunityStage.WON
        elif quote_data.status == QuoteStatus.REJECTED:
            quote.opportunity_stage = OpportunityStage.LOST
        elif quote_data.status == QuoteStatus.SENT and quote.opportunity_stage == OpportunityStage.CONCEPT:
            quote.opportunity_stage = OpportunityStage.QUOTE_SENT
    
    # QUOTED → WON/LOST: Transition lead when quote status changes
    if quote_data.status and quote.customer_id:
        from app.workflow import auto_transition_lead_status, find_leads_by_customer_id
        leads = find_leads_by_customer_id(quote.customer_id, session)
        
        if quote_data.status == QuoteStatus.ACCEPTED:
            # Transition QUOTED → WON
            for lead in leads:
                if lead.status == LeadStatus.QUOTED:
                    auto_transition_lead_status(
                        lead.id,
                        LeadStatus.WON,
                        session,
                        current_user.id,
                        "Automatic transition: Quote accepted"
                    )
        elif quote_data.status == QuoteStatus.REJECTED:
            # Transition QUOTED → LOST
            for lead in leads:
                if lead.status == LeadStatus.QUOTED:
                    auto_transition_lead_status(
                        lead.id,
                        LeadStatus.LOST,
                        session,
                        current_user.id,
                        "Automatic transition: Quote rejected"
                    )
    
    # Get quote items for response
    statement = select(QuoteItem).where(QuoteItem.quote_id == quote.id).order_by(QuoteItem.sort_order)
    quote_items = session.exec(statement).all()
    
    return QuoteResponse(
        id=quote.id,
        customer_id=quote.customer_id,
        quote_number=quote.quote_number,
        version=quote.version,
        status=quote.status,
        subtotal=quote.subtotal,
        discount_total=quote.discount_total,
        total_amount=quote.total_amount,
        deposit_amount=quote.deposit_amount,
        balance_amount=quote.balance_amount,
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
        items=[quote_item_to_response(item) for item in quote_items],
        opportunity_stage=quote.opportunity_stage,
        close_probability=quote.close_probability,
        expected_close_date=quote.expected_close_date,
        next_action=quote.next_action,
        next_action_due_date=quote.next_action_due_date,
        loss_reason=quote.loss_reason,
        loss_category=quote.loss_category,
        owner_id=quote.owner_id
    )


@router.get("/{quote_id}/preview-pdf")
async def preview_quote_pdf(
    quote_id: int,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """Preview quote as PDF without sending email."""
    # Get quote
    statement = select(Quote).where(Quote.id == quote_id)
    quote = session.exec(statement).first()
    
    if not quote:
        raise HTTPException(status_code=404, detail="Quote not found")
    
    # Get customer
    if not quote.customer_id:
        raise HTTPException(status_code=400, detail="Quote must be associated with a customer")
    
    statement = select(Customer).where(Customer.id == quote.customer_id)
    customer = session.exec(statement).first()
    
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")
    
    # Get quote items
    statement = select(QuoteItem).where(QuoteItem.quote_id == quote.id).order_by(QuoteItem.sort_order)
    quote_items = session.exec(statement).all()
    
    # Get company settings
    statement = select(CompanySettings).limit(1)
    company_settings = session.exec(statement).first()
    
    # Generate PDF
    try:
        pdf_buffer = generate_quote_pdf(quote, customer, quote_items, company_settings, session)
        pdf_content = pdf_buffer.read()
        
        # Sanitize customer name for filename (remove invalid characters)
        import re
        safe_customer_name = re.sub(r'[<>:"/\\|?*]', '_', customer.name).strip()
        safe_customer_name = re.sub(r'\s+', '_', safe_customer_name)  # Replace spaces with underscores
        pdf_filename = f"Quote_{quote.quote_number}_{safe_customer_name}.pdf"
        
        return Response(
            content=pdf_content,
            media_type="application/pdf",
            headers={
                "Content-Disposition": f'inline; filename="{pdf_filename}"'
            }
        )
    except Exception as e:
        import traceback
        error_msg = f"Error generating PDF: {str(e)}"
        print(error_msg, file=__import__('sys').stderr, flush=True)
        print(traceback.format_exc(), file=__import__('sys').stderr, flush=True)
        raise HTTPException(status_code=500, detail=error_msg)
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Error generating PDF: {str(e)}")
