"""
Public API routes (no authentication).
Used for quote view link tracking, public quote view page, and website visit pixel.
"""
import base64
import os
import re
from datetime import datetime
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import Response
from sqlmodel import Session, select

from app.database import get_session
from app.bank_details_crypto import get_decrypted_bank_details
from app.models import (
    QuoteEmail,
    Quote,
    QuoteItem,
    Customer,
    QuoteStatus,
    QuoteTemperature,
    WebsiteVisit,
    TrackedWebsite,
    CompanySettings,
    AccessSheetRequest,
    Order,
    QuoteFulfillmentMethod,
)
from app.available_optional_extras import (
    get_available_optional_extras_for_quote,
    should_show_available_optional_extras_on_quote,
)
from app.specification_sheet import (
    resolve_specification_sheet_text,
    should_include_specification_sheet,
)
from app.configurator_layout_public import build_layout_for_public_view
from app.schemas import (
    PublicQuoteViewResponse,
    PublicQuoteViewItemResponse,
    PublicQuoteCompanyDisplay,
    PublicQuoteDiscountLineResponse,
    PublicQuoteDeliveryLocationResponse,
    AccessSheetContextResponse,
    AccessSheetSubmitRequest,
    CustomerHistoryEventType,
    ReviewPrizePublicContextResponse,
    ReviewPrizePublicPlatform,
    ReviewPrizePublicSubmitRequest,
    ReviewHubPublicContextResponse,
    ReviewHubPublicPlatform,
    ReviewHubPrizeDrawBlock,
)
from app.review_hub_service import get_hub_context
from app.review_prize_draw_service import (
    configured_platforms,
    get_entry_by_token,
    submit_prize_draw_entry,
)
from app.models import ReviewPrizeDrawEntryStatus
from app.constants import VAT_RATE_DECIMAL, DELIVERY_INSTALLATION_CONTACT_NOTE
from app.delivery_location import build_delivery_address
from app.order_audit import record_order_audit_event
from app.quote_pdf_service import aggregate_quote_discount_lines, generate_quote_pdf
from app.temperature_service import recompute_quote_temperature

router = APIRouter(prefix="/api/public", tags=["public"])

# 1x1 transparent GIF (43 bytes)
PIXEL_GIF_BYTES = base64.b64decode("R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7")

SITE_SLUG_TO_ENUM = {
    "cheshire_stables": TrackedWebsite.CHESHIRE_STABLES,
    "csgb": TrackedWebsite.CSGB,
    "blc": TrackedWebsite.BLC,
}


def _resolve_public_logo_url(
    request: Request,
    logo_url: str | None,
    logo_filename: str,
) -> str | None:
    """Build a single logo URL for the frontend (browser)."""
    url = (logo_url or "").strip()
    if url.startswith("http://") or url.startswith("https://"):
        return url
    if url.startswith("/static/"):
        base = str(request.base_url).rstrip("/")
        return f"{base}{url}"
    # Fallback: frontend base + filename (same as PDF uses)
    frontend = (os.getenv("FRONTEND_URL") or os.getenv("PUBLIC_FRONTEND_URL") or "").strip()
    if not frontend:
        frontend = "https://leadlock-frontend-production.up.railway.app"
    filename = logo_filename or "logo1.jpg"
    return f"{frontend.rstrip('/')}/{filename}"


@router.get("/company-logo")
def get_public_company_logo(
    request: Request,
    session: Session = Depends(get_session),
):
    """
    Public endpoint: return company logo URL for web app header and login page.
    No authentication required. Resolves Cloudinary, /static/, or fallback filename.
    """
    company_settings = session.exec(select(CompanySettings).limit(1)).first()
    if not company_settings:
        return {"logo_url": None}
    logo_url = _resolve_public_logo_url(
        request,
        company_settings.logo_url,
        company_settings.logo_filename or "logo1.jpg",
    )
    return {"logo_url": logo_url}


@router.get("/quotes/view/{view_token}", response_model=PublicQuoteViewResponse)
def get_public_quote_view(
    request: Request,
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

    # Recompute temperature from opens (and cooling); commit if updated
    recompute_quote_temperature(session, quote.id)
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

    order_row = session.exec(select(Order).where(Order.quote_id == quote.id)).first()
    order_number = order_row.order_number if order_row else None

    vat_amount = (quote.total_amount or Decimal(0)) * VAT_RATE_DECIMAL
    total_inc_vat = (quote.total_amount or Decimal(0)) + vat_amount

    discount_lines: list[PublicQuoteDiscountLineResponse] = []
    if quote.discount_total and quote.discount_total > 0:
        aggregated = aggregate_quote_discount_lines(session, quote.id)
        if aggregated:
            discount_lines = [
                PublicQuoteDiscountLineResponse(description=desc, discount_amount=amt)
                for desc, amt in aggregated
            ]
        else:
            discount_lines = [
                PublicQuoteDiscountLineResponse(
                    description="",
                    discount_amount=quote.discount_total,
                )
            ]

    # Company display for header (logo + contact) – same as PDF
    company_display = None
    company_settings = session.exec(select(CompanySettings).limit(1)).first()
    if company_settings:
        logo_url_resolved = _resolve_public_logo_url(
            request,
            company_settings.logo_url,
            company_settings.logo_filename or "logo1.jpg",
        )
        bank = get_decrypted_bank_details(company_settings)
        company_display = PublicQuoteCompanyDisplay(
            trading_name=company_settings.trading_name,
            logo_url=logo_url_resolved,
            address_line1=company_settings.address_line1,
            address_line2=company_settings.address_line2,
            city=company_settings.city,
            county=company_settings.county,
            postcode=company_settings.postcode,
            phone=company_settings.phone,
            email=company_settings.email,
            website=company_settings.website,
            bank_name=bank["bank_name"],
            bank_account_name=bank["bank_account_name"],
            sort_code=bank["sort_code"],
            account_number=bank["account_number"],
        )

    return PublicQuoteViewResponse(
        quote_number=quote.quote_number,
        order_number=order_number,
        customer_name=customer_name,
        currency=quote.currency,
        valid_until=quote.valid_until,
        subtotal=quote.subtotal,
        discount_total=quote.discount_total,
        discount_lines=discount_lines,
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
        specification_sheet=(
            resolve_specification_sheet_text(quote, company_settings)
            if should_include_specification_sheet(quote, quote_email=quote_email)
            else None
        ),
        show_specification_sheet=should_include_specification_sheet(quote, quote_email=quote_email),
        company_display=company_display,
        available_optional_extras=(
            get_available_optional_extras_for_quote(
                list(items),
                session,
                quote_id=quote.id,
                include_product_linked=(
                    getattr(quote, "include_available_optional_extras", False)
                    or getattr(quote_email, "include_available_extras", False)
                ),
            )
            if should_show_available_optional_extras_on_quote(
                quote, quote.id, session, quote_email=quote_email
            )
            else None
        ),
        delivery_installation_contact_note=(
            DELIVERY_INSTALLATION_CONTACT_NOTE
            if (
                getattr(quote, "include_delivery_installation_contact_note", False)
                and getattr(quote, "fulfillment_method", QuoteFulfillmentMethod.DELIVERY)
                != QuoteFulfillmentMethod.COLLECTION
            )
            else None
        ),
        fulfillment_method=getattr(quote, "fulfillment_method", QuoteFulfillmentMethod.DELIVERY),
        delivery_location=(
            PublicQuoteDeliveryLocationResponse(
                address=build_delivery_address(quote),
                postcode=(quote.delivery_postcode or "").strip(),
                notes=(quote.delivery_location_notes or "").strip() or None,
            )
            if (
                getattr(quote, "use_alternate_delivery_address", False)
                and getattr(quote, "fulfillment_method", QuoteFulfillmentMethod.DELIVERY)
                != QuoteFulfillmentMethod.COLLECTION
            )
            else None
        ),
        layout=build_layout_for_public_view(session, quote.id),
    )


@router.get("/quotes/view/{view_token}/pdf")
def get_public_quote_pdf(
    view_token: str,
    session: Session = Depends(get_session),
):
    """
    Public endpoint: return quote as PDF by view token. No auth.
    Records one open (same as view) and recomputes temperature when customer downloads PDF.
    """
    statement = select(QuoteEmail).where(QuoteEmail.view_token == view_token)
    quote_email = session.exec(statement).first()
    if not quote_email:
        raise HTTPException(status_code=404, detail="Quote view not found")

    quote = session.get(Quote, quote_email.quote_id)
    if not quote:
        raise HTTPException(status_code=404, detail="Quote not found")

    # Record PDF download as engagement: one open, update last_viewed_at, recompute temperature
    now = datetime.utcnow()
    if quote_email.opened_at is None:
        quote_email.opened_at = now
    quote_email.open_count = (quote_email.open_count or 0) + 1
    if quote.viewed_at is None:
        quote.viewed_at = now
    quote.last_viewed_at = now
    session.add(quote_email)
    session.add(quote)
    session.commit()
    session.refresh(quote_email)
    session.refresh(quote)
    recompute_quote_temperature(session, quote.id)
    session.commit()
    session.refresh(quote)

    if not quote.customer_id:
        raise HTTPException(status_code=400, detail="Quote has no customer")

    customer = session.get(Customer, quote.customer_id)
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")

    items_stmt = (
        select(QuoteItem)
        .where(QuoteItem.quote_id == quote.id)
        .order_by(QuoteItem.sort_order)
    )
    quote_items = session.exec(items_stmt).all()
    company_settings = session.exec(select(CompanySettings).limit(1)).first()

    try:
        include_spec_sheets = getattr(quote, "include_spec_sheets", True)
        show_optional_extras = should_show_available_optional_extras_on_quote(
            quote, quote.id, session, quote_email=quote_email
        )
        use_specification_sheet = should_include_specification_sheet(quote, quote_email=quote_email)
        spec_sheet_text = (
            resolve_specification_sheet_text(quote, company_settings)
            if use_specification_sheet
            else ""
        )
        available_extras = (
            get_available_optional_extras_for_quote(
                list(quote_items),
                session,
                quote_id=quote.id,
                include_product_linked=(
                    getattr(quote, "include_available_optional_extras", False)
                    or getattr(quote_email, "include_available_extras", False)
                ),
            )
            if show_optional_extras
            else None
        )
        pdf_buffer = generate_quote_pdf(
            quote,
            customer,
            list(quote_items),
            company_settings,
            session,
            include_spec_sheets=include_spec_sheets,
            available_optional_extras=available_extras,
            include_specification_sheet=use_specification_sheet and bool(spec_sheet_text),
            specification_sheet_text=spec_sheet_text or None,
            layout=build_layout_for_public_view(session, quote.id),
        )
        pdf_content = pdf_buffer.read()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error generating PDF: {str(e)}")

    safe_customer_name = re.sub(r'[<>:"/\\|?*]', '_', customer.name).strip()
    safe_customer_name = re.sub(r'\s+', '_', safe_customer_name)
    pdf_filename = f"Quote_{quote.quote_number}_{safe_customer_name}.pdf"

    return Response(
        content=pdf_content,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{pdf_filename}"',
        },
    )


@router.get("/access-sheet/{token}", response_model=AccessSheetContextResponse)
def get_access_sheet_context(
    token: str,
    session: Session = Depends(get_session),
):
    """
    Public endpoint: load access sheet context by token.
    Returns customer name, order number, and any existing answers if already completed.
    No authentication.
    """
    req = session.exec(
        select(AccessSheetRequest).where(AccessSheetRequest.access_token == token)
    ).first()
    if not req:
        raise HTTPException(status_code=404, detail="Access sheet not found")

    order = session.get(Order, req.order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    customer_name = ""
    if order.customer_id:
        customer = session.get(Customer, order.customer_id)
        if customer:
            customer_name = customer.name

    return AccessSheetContextResponse(
        customer_name=customer_name,
        order_number=order.order_number,
        completed=req.completed_at is not None,
        completed_at=req.completed_at,
        answers=req.answers,
    )


@router.post("/access-sheet/{token}")
def submit_access_sheet(
    token: str,
    data: AccessSheetSubmitRequest,
    session: Session = Depends(get_session),
):
    """
    Public endpoint: submit access sheet form. No authentication.
    Saves answers and sets completed_at.
    """
    req = session.exec(
        select(AccessSheetRequest).where(AccessSheetRequest.access_token == token)
    ).first()
    if not req:
        raise HTTPException(status_code=404, detail="Access sheet not found")

    if req.completed_at:
        raise HTTPException(status_code=400, detail="Access sheet already submitted")

    order = session.get(Order, req.order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    # Build answers dict from request (exclude None)
    answers = {}
    for field, value in data.model_dump(exclude_none=True).items():
        if value is not None:
            answers[field] = value

    req.answers = answers if answers else None
    req.completed_at = datetime.utcnow()

    session.add(req)
    record_order_audit_event(
        session,
        event_type=CustomerHistoryEventType.ORDER_ACCESS_SHEET_COMPLETED.value,
        title="Access Sheet Completed",
        description=f"Customer completed the access sheet for order {order.order_number}",
        order=order,
        metadata={"completed_by": "customer"},
        created_at=req.completed_at,
    )
    session.commit()

    return {"message": "Access sheet submitted successfully"}


@router.get("/review/{token}", response_model=ReviewHubPublicContextResponse)
def get_review_hub_context(
    token: str,
    session: Session = Depends(get_session),
):
    """Public endpoint: review hub page context. No authentication."""
    data, err = get_hub_context(token, session)
    if err or not data:
        raise HTTPException(status_code=404, detail=err or "Review link not found")

    prize_draw = None
    if data.get("prize_draw"):
        pd = data["prize_draw"]
        prize_draw = ReviewHubPrizeDrawBlock(
            title=pd["title"],
            terms=pd.get("terms"),
            min_platforms=pd.get("min_platforms", 2),
            url=pd["url"],
        )

    return ReviewHubPublicContextResponse(
        company_name=data["company_name"],
        customer_name=data.get("customer_name"),
        order_number=data["order_number"],
        platforms=[
            ReviewHubPublicPlatform(code=p["code"], label=p["label"], url=p["url"])
            for p in data.get("platforms", [])
        ],
        prize_draw=prize_draw,
    )


@router.get("/review-prize/{token}", response_model=ReviewPrizePublicContextResponse)
def get_review_prize_context(
    token: str,
    session: Session = Depends(get_session),
):
    """Public endpoint: prize draw form context. No authentication."""
    entry = get_entry_by_token(session, token)
    if not entry:
        raise HTTPException(status_code=404, detail="Prize draw entry not found")

    order = session.get(Order, entry.order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    settings = session.exec(select(CompanySettings).limit(1)).first()
    customer_name = ""
    if order.customer_id:
        customer = session.get(Customer, order.customer_id)
        if customer:
            customer_name = customer.name

    platforms = [
        ReviewPrizePublicPlatform(code=code, label=label)
        for code, label in configured_platforms(settings)
    ]
    status_val = entry.status.value if entry.status else None
    can_submit = (
        entry.status == ReviewPrizeDrawEntryStatus.REJECTED
        or (entry.status == ReviewPrizeDrawEntryStatus.PENDING and not entry.submitted_at)
    )

    return ReviewPrizePublicContextResponse(
        customer_name=customer_name,
        order_number=order.order_number,
        prize_title=settings.review_prize_draw_title if settings else None,
        prize_terms=settings.review_prize_draw_terms if settings else None,
        min_platforms=max(1, int(settings.review_prize_draw_min_platforms or 2)) if settings else 2,
        platforms=platforms,
        status=status_val,
        platforms_claimed=entry.platforms_claimed or [],
        submitted_at=entry.submitted_at,
        can_submit=can_submit,
    )


@router.post("/review-prize/{token}")
def submit_review_prize(
    token: str,
    data: ReviewPrizePublicSubmitRequest,
    session: Session = Depends(get_session),
):
    """Public endpoint: submit prize draw entry. No authentication."""
    entry, err = submit_prize_draw_entry(token, data.platforms, session)
    if err:
        raise HTTPException(status_code=400, detail=err)
    session.commit()
    return {"message": "Prize draw entry submitted successfully"}


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
            # Warm latest SENT quote if it is COLD or null (customer visited site)
            latest_sent = session.exec(
                select(Quote)
                .where(
                    Quote.customer_id == customer.id,
                    Quote.status == QuoteStatus.SENT,
                )
                .order_by(Quote.sent_at.desc())
                .limit(1)
            ).first()
            if latest_sent and latest_sent.temperature in (None, QuoteTemperature.COLD):
                latest_sent.temperature = QuoteTemperature.WARM
                session.add(latest_sent)
                session.commit()
    return Response(
        content=PIXEL_GIF_BYTES,
        media_type="image/gif",
        headers={"Cache-Control": "no-store, no-cache, must-revalidate"},
    )
