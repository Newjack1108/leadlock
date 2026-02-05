"""
Public API routes (no authentication).
Used for quote view link tracking and public quote view page.
"""
from datetime import datetime
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select, func

from app.database import get_session
from app.models import QuoteEmail, Quote, QuoteItem, Customer, QuoteTemperature
from app.schemas import PublicQuoteViewResponse, PublicQuoteViewItemResponse
from app.constants import VAT_RATE_DECIMAL

router = APIRouter(prefix="/api/public", tags=["public"])


@router.get("/quotes/view/{view_token}", response_model=PublicQuoteViewResponse)
def get_public_quote_view(
    view_token: str,
    session: Session = Depends(get_session),
):
    """
    Public endpoint: load quote by view token and record an open.
    No authentication. Used when customer clicks "View your quote" link in email.
    """
    # Look up QuoteEmail by view_token
    statement = select(QuoteEmail).where(QuoteEmail.view_token == view_token)
    quote_email = session.exec(statement).first()
    if not quote_email:
        raise HTTPException(status_code=404, detail="Quote view not found")

    quote = session.get(Quote, quote_email.quote_id)
    if not quote:
        raise HTTPException(status_code=404, detail="Quote not found")

    now = datetime.utcnow()

    # Record open: set opened_at if first time, increment open_count
    if quote_email.opened_at is None:
        quote_email.opened_at = now
    quote_email.open_count = (quote_email.open_count or 0) + 1

    # Set quote.viewed_at if not set (first open)
    if quote.viewed_at is None:
        quote.viewed_at = now

    session.add(quote_email)
    session.add(quote)
    session.commit()
    session.refresh(quote_email)
    session.refresh(quote)

    # After commit: check total opens and set Hot if >= 3
    total_opens = session.exec(
        select(func.coalesce(func.sum(QuoteEmail.open_count), 0)).where(
            QuoteEmail.quote_id == quote.id
        )
    ).first() or 0
    if total_opens >= 3 and quote.temperature != QuoteTemperature.HOT:
        quote.temperature = QuoteTemperature.HOT
        session.add(quote)
        session.commit()
        session.refresh(quote)

    # Load customer name
    customer_name = ""
    if quote.customer_id:
        customer = session.get(Customer, quote.customer_id)
        if customer:
            customer_name = customer.name

    # Load items
    items_stmt = (
        select(QuoteItem)
        .where(QuoteItem.quote_id == quote.id)
        .order_by(QuoteItem.sort_order)
    )
    items = session.exec(items_stmt).all()

    vat_amount = (quote.total_amount or Decimal(0)) * VAT_RATE_DECIMAL
    total_inc_vat = (quote.total_amount or Decimal(0)) + vat_amount

    return PublicQuoteViewResponse(
        quote_number=quote.quote_number,
        customer_name=customer_name,
        currency=quote.currency,
        valid_until=quote.valid_until,
        subtotal=quote.subtotal,
        discount_total=quote.discount_total,
        total_amount=quote.total_amount,
        deposit_amount=quote.deposit_amount,
        balance_amount=quote.balance_amount,
        vat_amount=vat_amount,
        total_amount_inc_vat=total_inc_vat,
        items=[
            PublicQuoteViewItemResponse(
                description=item.description,
                quantity=item.quantity,
                unit_price=item.unit_price,
                line_total=item.line_total,
                final_line_total=item.final_line_total,
                sort_order=item.sort_order,
            )
            for item in items
        ],
        terms_and_conditions=quote.terms_and_conditions,
    )
