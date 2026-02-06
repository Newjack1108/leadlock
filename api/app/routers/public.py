"""
Public API routes (no authentication).
Used for quote view link tracking, public quote view page, and website visit pixel.
"""
import base64
from datetime import datetime
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlmodel import Session, select, func

from app.database import get_session
from app.models import (
    QuoteEmail,
    Quote,
    QuoteItem,
    Customer,
    QuoteTemperature,
    WebsiteVisit,
    TrackedWebsite,
)
from app.schemas import PublicQuoteViewResponse, PublicQuoteViewItemResponse
from app.constants import VAT_RATE_DECIMAL

router = APIRouter(prefix="/api/public", tags=["public"])

# 1x1 transparent GIF (43 bytes)
PIXEL_GIF_BYTES = base64.b64decode("R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7")

SITE_SLUG_TO_ENUM = {
    "cheshire_stables": TrackedWebsite.CHESHIRE_STABLES,
    "csgb": TrackedWebsite.CSGB,
    "blc": TrackedWebsite.BLC,
}


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

    # Set quote.viewed_at if not set (first open), always update last_viewed_at
    if quote.viewed_at is None:
        quote.viewed_at = now
    quote.last_viewed_at = now

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


@router.get("/pixel")
def get_pixel(
    token: str = Query(..., description="Customer number (e.g. CUST-2024-001)"),
    site: str = Query(..., description="Site slug: cheshire_stables, csgb, or blc"),
    session: Session = Depends(get_session),
):
    """
    Tracking pixel: 1x1 transparent GIF. When loaded with a valid token and site,
    records a website visit for that customer. Always returns 200 and the GIF
    (do not leak whether token was valid).
    """
    site_enum = SITE_SLUG_TO_ENUM.get(site.lower() if site else "")
    if site_enum is not None:
        customer = session.exec(
            select(Customer).where(Customer.customer_number == token)
        ).first()
        if customer:
            visit = WebsiteVisit(customer_id=customer.id, site=site_enum)
            session.add(visit)
            session.commit()
    return Response(
        content=PIXEL_GIF_BYTES,
        media_type="image/gif",
        headers={"Cache-Control": "no-store, no-cache, must-revalidate"},
    )
