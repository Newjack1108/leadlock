from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select
from typing import List
from app.database import get_session
from app.models import Quote, QuoteItem, Customer, User
from app.auth import get_current_user
from app.schemas import QuoteCreate, QuoteUpdate, QuoteResponse, QuoteItemCreate, QuoteItemResponse
from datetime import datetime
from decimal import Decimal

router = APIRouter(prefix="/api/quotes", tags=["quotes"])


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
    # Verify customer exists
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
        line_total = item_data.quantity * item_data.unit_price
        subtotal += line_total
        
        item = QuoteItem(
            quote_id=0,  # Will be set after quote is created
            product_id=item_data.product_id,
            description=item_data.description,
            quantity=item_data.quantity,
            unit_price=item_data.unit_price,
            line_total=line_total,
            discount_amount=Decimal(0),
            final_line_total=line_total,
            sort_order=item_data.sort_order,
            is_custom=item_data.is_custom
        )
        items.append(item)
    
    # Create quote
    quote = Quote(
        customer_id=quote_data.customer_id,
        quote_number=quote_number,
        version=quote_data.version,
        subtotal=subtotal,
        discount_total=Decimal(0),
        total_amount=subtotal,
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
