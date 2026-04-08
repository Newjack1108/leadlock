import json
from pathlib import Path
from fastapi import APIRouter, Body, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import Response
from sqlmodel import Session, select, or_, and_
from sqlalchemy import func
from typing import Dict, List, Optional, Union
from app.database import get_session
from app.models import Quote, QuoteItem, QuoteTemplate, QuoteTemplateSalesDocument, SalesDocument, Customer, User, QuoteEmail, Email, EmailDirection, Activity, ActivityType, CompanySettings, Lead, LeadStatus, QuoteStatus, QuoteTemperature, OpportunityStage, LossCategory, DiscountTemplate, QuoteDiscount, DiscountType, DiscountScope, Order, OrderItem, QuoteItemLineType, DiscountRequest, SmsMessage, SmsDirection
from app.auth import get_current_user
from app.schemas import (
    QuoteCreate, QuoteUpdate, QuoteDraftUpdate, QuoteResponse, QuoteItemCreate, QuoteItemResponse,
    QuoteEmailSendRequest, QuoteEmailSendResponse, QuoteViewLinkResponse,
    QuoteShareLinkRequest, QuoteShareLinkResponse, QuoteSendSmsRequest, QuoteSendSmsResponse,
    OpportunityWonRequest, OpportunityLostRequest, OpportunityCloseRequest,
    QuoteDiscountResponse
)
from app.quote_email_service import send_quote_email
from app.routers.emails import (
    MAX_ATTACHMENT_SIZE,
    MAX_TOTAL_ATTACHMENTS,
    _normalize_upload_files,
    _sanitize_filename,
)
from app.customer_view_links import customer_view_path_segment
from app.email_service import is_email_configured
from app.sms_service import send_sms, normalize_phone
from app.quote_pdf_service import generate_quote_pdf
from app.available_optional_extras import get_available_optional_extras_for_quote
from app.reminder_service import get_last_activity_date
from app.constants import QUOTE_LIST_EXCLUDED_STATUSES, VAT_RATE_DECIMAL
from app.quote_delete import delete_quote_cascade
from app.discount_limits import assert_templates_not_expired_for_apply, validate_and_record_redemptions_on_accept
from datetime import datetime
from decimal import Decimal
import os
import uuid

router = APIRouter(prefix="/api/quotes", tags=["quotes"])


def apply_qualified_to_quoted_transition_for_customer(
    customer_id: int,
    session: Session,
    current_user_id: int,
    reason: str = "Automatic transition: Quote created",
) -> None:
    """QUALIFIED → QUOTED for leads on this customer (same as after create_quote when not deferred)."""
    from app.workflow import auto_transition_lead_status, find_leads_by_customer_id

    leads = find_leads_by_customer_id(customer_id, session)
    for lead in leads:
        if lead.status == LeadStatus.QUALIFIED:
            auto_transition_lead_status(
                lead.id,
                LeadStatus.QUOTED,
                session,
                current_user_id,
                reason,
            )


def _frontend_base_url() -> Optional[str]:
    return (os.getenv("FRONTEND_BASE_URL") or os.getenv("FRONTEND_URL") or os.getenv("PUBLIC_FRONTEND_URL") or "").strip() or None


def ensure_quote_share_link(
    session: Session,
    quote: Quote,
    customer: Customer,
    current_user: User,
    include_available_extras: bool,
) -> tuple[QuoteEmail, str, bool]:
    """
    Ensure a QuoteEmail row with view_token exists (reuse latest with token).
    If newly created: set quote to SENT, add NOTE activity.
    If reusing and include_available_extras is True, upgrade the flag on the row.
    Returns (quote_email, view_url, created_new).
    """
    base_url = _frontend_base_url()
    if not base_url:
        raise HTTPException(
            status_code=400,
            detail="Public view URL not configured. Set FRONTEND_BASE_URL (or FRONTEND_URL / PUBLIC_FRONTEND_URL) on the API.",
        )

    statement = (
        select(QuoteEmail)
        .where(QuoteEmail.quote_id == quote.id, QuoteEmail.view_token.isnot(None))
        .order_by(QuoteEmail.sent_at.desc())
        .limit(1)
    )
    quote_email = session.exec(statement).first()

    if quote_email and quote_email.view_token:
        if include_available_extras and not getattr(quote_email, "include_available_extras", False):
            quote_email.include_available_extras = True
            session.add(quote_email)
            session.commit()
            session.refresh(quote_email)
        view_url = f"{base_url.rstrip('/')}/{customer_view_path_segment(session, quote.id, quote_email.view_token)}"
        return quote_email, view_url, False

    view_token = uuid.uuid4().hex
    to_email = (customer.email or "").strip() or "share@local.invalid"
    subject = f"Quote {quote.quote_number} — link shared"
    body_html = "<p>Customer view link was shared outside email.</p>"
    tracking_id = f"share-{quote.id}-{uuid.uuid4().hex}"

    quote_email = QuoteEmail(
        quote_id=quote.id,
        to_email=to_email,
        subject=subject,
        body_html=body_html,
        tracking_id=tracking_id,
        view_token=view_token,
        include_available_extras=include_available_extras,
    )
    session.add(quote_email)

    quote.status = QuoteStatus.SENT
    quote.sent_at = datetime.utcnow()
    quote.updated_at = datetime.utcnow()
    if quote.temperature is None:
        quote.temperature = QuoteTemperature.COLD
    if quote.opportunity_stage == OpportunityStage.CONCEPT:
        quote.opportunity_stage = OpportunityStage.QUOTE_SENT
    session.add(quote)

    session.commit()
    session.refresh(quote_email)

    activity = Activity(
        customer_id=quote.customer_id,
        activity_type=ActivityType.NOTE,
        notes=f"Quote {quote.quote_number} customer view link created (shared outside email)",
        created_by_id=current_user.id,
    )
    session.add(activity)
    session.commit()

    view_url = f"{base_url.rstrip('/')}/{customer_view_path_segment(session, quote.id, view_token)}"
    return quote_email, view_url, True


def quote_item_to_response(item: QuoteItem) -> QuoteItemResponse:
    """Convert a QuoteItem SQLModel instance to QuoteItemResponse."""
    return QuoteItemResponse(
        id=item.id,
        quote_id=item.quote_id,
        product_id=item.product_id,
        parent_quote_item_id=item.parent_quote_item_id,
        description=item.description,
        quantity=item.quantity,
        unit_price=item.unit_price,
        line_total=item.line_total,
        discount_amount=item.discount_amount,
        final_line_total=item.final_line_total,
        sort_order=item.sort_order,
        is_custom=item.is_custom,
        line_type=getattr(item, "line_type", None),
        include_in_building_discount=getattr(item, "include_in_building_discount", True),
    )


def _item_eligible_for_product_scope_discount(item: QuoteItem) -> bool:
    """Main lines only; respects include_in_building_discount and delivery/install exclusions."""
    if item.parent_quote_item_id is not None:
        return False
    if not getattr(item, "include_in_building_discount", True):
        return False
    line_type = getattr(item, "line_type", None)
    if line_type in (QuoteItemLineType.DELIVERY, QuoteItemLineType.INSTALLATION):
        return False
    if item.description == "Delivery & Installation":
        return False
    return True


def build_quote_response(quote: Quote, quote_items: List[QuoteItem], session: Session) -> QuoteResponse:
    """Build a QuoteResponse with items and discounts."""
    discount_statement = select(QuoteDiscount).where(QuoteDiscount.quote_id == quote.id)
    quote_discounts = session.exec(discount_statement).all()
    customer_name = None
    customer_last_interacted_at = None
    lead_name = None
    lead_type = None
    if quote.customer_id:
        customer = session.exec(select(Customer).where(Customer.id == quote.customer_id)).first()
        customer_name = customer.name if customer else None
        customer_last_interacted_at = get_last_activity_date(quote.customer_id, session)
    if quote.lead_id:
        lead = session.exec(select(Lead).where(Lead.id == quote.lead_id)).first()
        lead_name = lead.name if lead else None
        lead_type = lead.lead_type if lead else None

    # Computed VAT (total_amount is Ex VAT @ 20%; deposit/balance stored as inc VAT)
    vat_amount = quote.total_amount * VAT_RATE_DECIMAL
    total_amount_inc_vat = quote.total_amount + vat_amount
    deposit_amount_inc_vat = quote.deposit_amount  # Stored as inc VAT
    balance_amount_inc_vat = quote.balance_amount  # Stored as inc VAT

    total_open_count = session.exec(
        select(func.coalesce(func.sum(QuoteEmail.open_count), 0)).where(QuoteEmail.quote_id == quote.id)
    ).first() or 0
    if hasattr(total_open_count, "__int__"):
        total_open_count = int(total_open_count)

    order_id = None
    if quote.status == QuoteStatus.ACCEPTED:
        order = session.exec(select(Order).where(Order.quote_id == quote.id)).first()
        if order:
            order_id = order.id

    return QuoteResponse(
        id=quote.id,
        customer_id=quote.customer_id,
        customer_name=customer_name,
        lead_id=quote.lead_id,
        lead_name=lead_name,
        lead_type=lead_type,
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
        last_viewed_at=quote.last_viewed_at,
        accepted_at=quote.accepted_at,
        created_at=quote.created_at,
        updated_at=quote.updated_at,
        vat_amount=vat_amount,
        total_amount_inc_vat=total_amount_inc_vat,
        deposit_amount_inc_vat=deposit_amount_inc_vat,
        balance_amount_inc_vat=balance_amount_inc_vat,
        items=[quote_item_to_response(item) for item in quote_items],
        discounts=[QuoteDiscountResponse(**discount.dict()) for discount in quote_discounts],
        opportunity_stage=quote.opportunity_stage,
        close_probability=quote.close_probability,
        expected_close_date=quote.expected_close_date,
        next_action=quote.next_action,
        next_action_due_date=quote.next_action_due_date,
        loss_reason=quote.loss_reason,
        loss_category=quote.loss_category,
        owner_id=quote.owner_id,
        temperature=quote.temperature,
        include_spec_sheets=getattr(quote, "include_spec_sheets", True),
        include_available_optional_extras=getattr(quote, "include_available_optional_extras", False),
        include_delivery_installation_contact_note=getattr(quote, "include_delivery_installation_contact_note", False),
        total_open_count=total_open_count,
        order_id=order_id,
        customer_last_interacted_at=customer_last_interacted_at,
    )


def apply_discount_to_quote(
    quote: Quote,
    discount_template: DiscountTemplate,
    quote_items: List[QuoteItem],
    session: Session,
    current_user: User
) -> Decimal:
    """
    Apply a discount template to a quote.
    Returns the total discount amount applied.
    """
    total_discount = Decimal(0)
    
    if discount_template.scope == DiscountScope.PRODUCT:
        # Apply discount only to main/building items (exclude extras, delivery, installation, opt-outs)
        for item in quote_items:
            if not _item_eligible_for_product_scope_discount(item):
                continue
            if item.line_total > 0:  # Only apply to items with value
                # Calculate discount based on current line total (before other discounts)
                base_amount = item.line_total + item.discount_amount  # Original line total
                if discount_template.discount_type == DiscountType.PERCENTAGE:
                    discount_amount = base_amount * (discount_template.discount_value / Decimal(100))
                else:  # FIXED_AMOUNT
                    discount_amount = min(discount_template.discount_value, base_amount)
                
                # Update item discount (additive with other discounts)
                item.discount_amount += discount_amount
                item.final_line_total = item.line_total - item.discount_amount
                # Ensure final_line_total doesn't go negative
                if item.final_line_total < 0:
                    item.final_line_total = Decimal(0)
                total_discount += discount_amount
                
                # Create QuoteDiscount record for this item
                quote_discount = QuoteDiscount(
                    quote_id=quote.id,
                    quote_item_id=item.id,
                    template_id=discount_template.id,
                    discount_type=discount_template.discount_type,
                    discount_value=discount_template.discount_value,
                    scope=discount_template.scope,
                    discount_amount=discount_amount,
                    description=discount_template.name,
                    applied_by_id=current_user.id
                )
                session.add(quote_discount)
    else:  # QUOTE scope
        # Apply discount to entire quote subtotal (before item discounts)
        # Quote-level discounts apply to the original subtotal
        if discount_template.discount_type == DiscountType.PERCENTAGE:
            discount_amount = quote.subtotal * (discount_template.discount_value / Decimal(100))
        else:  # FIXED_AMOUNT
            discount_amount = min(discount_template.discount_value, quote.subtotal)
        
        total_discount = discount_amount
        
        # Create QuoteDiscount record for quote-level discount
        quote_discount = QuoteDiscount(
            quote_id=quote.id,
            quote_item_id=None,
            template_id=discount_template.id,
            discount_type=discount_template.discount_type,
            discount_value=discount_template.discount_value,
            scope=discount_template.scope,
            discount_amount=discount_amount,
            description=discount_template.name,
            applied_by_id=current_user.id
        )
        session.add(quote_discount)
    
    return total_discount


def apply_custom_discount_to_quote(
    quote: Quote,
    discount_type: DiscountType,
    discount_value: Decimal,
    scope: DiscountScope,
    description: str,
    quote_items: List[QuoteItem],
    session: Session,
    current_user: User
) -> Decimal:
    """
    Apply an ad-hoc (custom) discount to a quote (no template).
    Creates QuoteDiscount records with template_id=None.
    Returns the total discount amount applied.
    """
    total_discount = Decimal(0)

    if scope == DiscountScope.PRODUCT:
        for item in quote_items:
            if not _item_eligible_for_product_scope_discount(item):
                continue
            if item.line_total > 0:
                base_amount = item.line_total + item.discount_amount
                if discount_type == DiscountType.PERCENTAGE:
                    discount_amount = base_amount * (discount_value / Decimal(100))
                else:
                    discount_amount = min(discount_value, base_amount)

                item.discount_amount += discount_amount
                item.final_line_total = item.line_total - item.discount_amount
                if item.final_line_total < 0:
                    item.final_line_total = Decimal(0)
                total_discount += discount_amount

                quote_discount = QuoteDiscount(
                    quote_id=quote.id,
                    quote_item_id=item.id,
                    template_id=None,
                    discount_type=discount_type,
                    discount_value=discount_value,
                    scope=scope,
                    discount_amount=discount_amount,
                    description=description,
                    applied_by_id=current_user.id
                )
                session.add(quote_discount)
    else:
        if discount_type == DiscountType.PERCENTAGE:
            discount_amount = quote.subtotal * (discount_value / Decimal(100))
        else:
            discount_amount = min(discount_value, quote.subtotal)
        total_discount = discount_amount

        quote_discount = QuoteDiscount(
            quote_id=quote.id,
            quote_item_id=None,
            template_id=None,
            discount_type=discount_type,
            discount_value=discount_value,
            scope=scope,
            discount_amount=discount_amount,
            description=description,
            applied_by_id=current_user.id
        )
        session.add(quote_discount)

    # Recalculate quote totals
    item_discount_total = sum(item.discount_amount for item in quote_items)
    discount_statement = select(QuoteDiscount).where(
        QuoteDiscount.quote_id == quote.id,
        QuoteDiscount.quote_item_id.is_(None)
    )
    quote_level_discounts = session.exec(discount_statement).all()
    quote_level_discount_total = sum(d.discount_amount for d in quote_level_discounts)
    quote.discount_total = item_discount_total + quote_level_discount_total
    quote.total_amount = quote.subtotal - quote.discount_total
    if quote.total_amount < 0:
        quote.total_amount = Decimal(0)
    total_inc_vat = quote.total_amount * (Decimal("1") + VAT_RATE_DECIMAL)
    if quote.deposit_amount > total_inc_vat:
        quote.deposit_amount = total_inc_vat
    quote.balance_amount = total_inc_vat - quote.deposit_amount
    session.add(quote)
    return total_discount


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


def generate_order_number(session: Session) -> str:
    """Generate a unique order number like ORD-2025-001."""
    from datetime import date
    year = date.today().year
    statement = select(Order).where(Order.order_number.like(f"ORD-{year}-%"))
    orders = session.exec(statement).all()
    if not orders:
        return f"ORD-{year}-001"
    numbers = []
    for order in orders:
        try:
            num = int(order.order_number.split("-")[-1])
            numbers.append(num)
        except (ValueError, IndexError):
            continue
    if not numbers:
        return f"ORD-{year}-001"
    next_num = max(numbers) + 1
    return f"ORD-{year}-{next_num:03d}"


def create_order_from_quote(quote: Quote, session: Session, created_by_id: int) -> Order:
    """Create an Order from an accepted quote (idempotent: returns existing order if already created)."""
    existing = session.exec(select(Order).where(Order.quote_id == quote.id)).first()
    if existing:
        return existing
    order_number = generate_order_number(session)
    order = Order(
        quote_id=quote.id,
        customer_id=quote.customer_id,
        order_number=order_number,
        subtotal=quote.subtotal,
        discount_total=quote.discount_total,
        total_amount=quote.total_amount,
        deposit_amount=quote.deposit_amount,
        balance_amount=quote.balance_amount,
        currency=quote.currency,
        terms_and_conditions=quote.terms_and_conditions,
        notes=quote.notes,
        created_by_id=created_by_id,
    )
    session.add(order)
    session.flush()
    quote_items = session.exec(
        select(QuoteItem).where(QuoteItem.quote_id == quote.id).order_by(QuoteItem.sort_order)
    ).all()
    for qi in quote_items:
        order_item = OrderItem(
            order_id=order.id,
            quote_item_id=qi.id,
            product_id=qi.product_id,
            description=qi.description,
            quantity=qi.quantity,
            unit_price=qi.unit_price,
            line_total=qi.line_total,
            discount_amount=qi.discount_amount,
            final_line_total=qi.final_line_total,
            sort_order=qi.sort_order,
            is_custom=qi.is_custom,
        )
        session.add(order_item)
    return order


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

        if not quote_data.lead_id:
            raise HTTPException(status_code=400, detail="lead_id is required - quotes must be linked to an enquiry (lead)")

        lead = session.exec(select(Lead).where(Lead.id == quote_data.lead_id)).first()
        if not lead:
            raise HTTPException(status_code=404, detail="Lead not found")
        if lead.customer_id != quote_data.customer_id:
            raise HTTPException(status_code=400, detail="Lead must belong to the same customer")
        lead_id = lead.id

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
                is_custom=item_data.is_custom if item_data.is_custom is not None else False,
                line_type=getattr(item_data, "line_type", None),
                include_in_building_discount=getattr(item_data, "include_in_building_discount", True),
            )
            items.append(item)
    
        # Calculate deposit and balance (inc VAT)
        # Default to 50% of total inc VAT if not provided
        total_amount = subtotal  # No discounts applied yet
        total_inc_vat = total_amount * (Decimal("1") + VAT_RATE_DECIMAL)
        if quote_data.deposit_amount is not None:
            deposit_amount = Decimal(str(quote_data.deposit_amount))  # Client sends inc VAT
        else:
            deposit_amount = total_inc_vat * Decimal("0.5")
        
        if deposit_amount > total_inc_vat:
            deposit_amount = total_inc_vat
        
        balance_amount = total_inc_vat - deposit_amount
        
        # Create quote
        quote = Quote(
            customer_id=quote_data.customer_id,
            lead_id=lead_id,
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
            created_by_id=current_user.id,
            temperature=quote_data.temperature,
            include_spec_sheets=getattr(quote_data, "include_spec_sheets", True),
            include_available_optional_extras=getattr(quote_data, "include_available_optional_extras", False),
            include_delivery_installation_contact_note=getattr(quote_data, "include_delivery_installation_contact_note", False),
        )
        session.add(quote)
        session.commit()
        session.refresh(quote)
        
        # Add items with quote_id (parent_quote_item_id set in next step after we have IDs)
        for item in items:
            item.quote_id = quote.id
            item.parent_quote_item_id = None
            session.add(item)
        session.commit()
        
        # Refresh to get items with IDs in sort_order
        session.refresh(quote)
        statement = select(QuoteItem).where(QuoteItem.quote_id == quote.id).order_by(QuoteItem.sort_order)
        quote_items = list(session.exec(statement).all())
        
        # Set parent_quote_item_id for optional-extra items (parent_index from payload)
        for i, db_item in enumerate(quote_items):
            if i < len(quote_data.items):
                item_data = quote_data.items[i]
                parent_index = getattr(item_data, "parent_index", None)
                if parent_index is not None and 0 <= parent_index < len(quote_items):
                    db_item.parent_quote_item_id = quote_items[parent_index].id
                    session.add(db_item)
        if quote_items and any(getattr(quote_data.items[i], "parent_index", None) is not None for i in range(min(len(quote_data.items), len(quote_items)))):
            session.commit()
            statement = select(QuoteItem).where(QuoteItem.quote_id == quote.id).order_by(QuoteItem.sort_order)
            quote_items = list(session.exec(statement).all())
        
        # Apply discounts if provided
        discount_total = Decimal(0)
        if quote_data.discount_template_ids:
            assert_templates_not_expired_for_apply(session, quote_data.discount_template_ids)
            for template_id in quote_data.discount_template_ids:
                template_statement = select(DiscountTemplate).where(
                    DiscountTemplate.id == template_id,
                    DiscountTemplate.is_active == True
                )
                discount_template = session.exec(template_statement).first()
                
                if discount_template:
                    # Handle giveaway discounts
                    if discount_template.is_giveaway:
                        # For giveaways, we expect the product to already be in the items
                        # with a 100% discount applied. The discount template just marks it.
                        # Apply 100% discount to matching products if needed (building items only, not extras)
                        for item in quote_items:
                            if not _item_eligible_for_product_scope_discount(item):
                                continue
                            if item.product_id and discount_template.scope == DiscountScope.PRODUCT:
                                # Apply 100% discount to this item
                                item.discount_amount = item.line_total
                                item.final_line_total = Decimal(0)
                                discount_total += item.line_total
                                
                                quote_discount = QuoteDiscount(
                                    quote_id=quote.id,
                                    quote_item_id=item.id,
                                    template_id=discount_template.id,
                                    discount_type=DiscountType.PERCENTAGE,
                                    discount_value=Decimal(100),
                                    scope=discount_template.scope,
                                    discount_amount=item.line_total,
                                    description=discount_template.name,
                                    applied_by_id=current_user.id
                                )
                                session.add(quote_discount)
                    else:
                        # Apply regular discount
                        discount_amount = apply_discount_to_quote(
                            quote, discount_template, quote_items, session, current_user
                        )
                        discount_total += discount_amount
                    
                    # Update items after discount application
                    for item in quote_items:
                        session.add(item)
        
        # Recalculate totals with discounts
        # Commit item changes first
        session.commit()
        
        # Refresh items to get updated discount amounts
        session.refresh(quote)
        statement = select(QuoteItem).where(QuoteItem.quote_id == quote.id)
        quote_items = session.exec(statement).all()
        
        # Sum up all item-level discounts
        item_discount_total = sum(item.discount_amount for item in quote_items)
        
        # Get quote-level discounts
        discount_statement = select(QuoteDiscount).where(
            QuoteDiscount.quote_id == quote.id,
            QuoteDiscount.quote_item_id.is_(None)
        )
        quote_level_discounts = session.exec(discount_statement).all()
        quote_level_discount_total = sum(d.discount_amount for d in quote_level_discounts)
        
        quote.discount_total = item_discount_total + quote_level_discount_total
        quote.total_amount = quote.subtotal - quote.discount_total
        # Ensure total doesn't go negative
        if quote.total_amount < 0:
            quote.total_amount = Decimal(0)
        
        # Recalculate deposit and balance (inc VAT)
        total_inc_vat = quote.total_amount * (Decimal("1") + VAT_RATE_DECIMAL)
        if quote_data.deposit_amount is not None:
            deposit_amount = Decimal(str(quote_data.deposit_amount))  # Client sends inc VAT
        else:
            deposit_amount = total_inc_vat * Decimal("0.5")
        
        if deposit_amount > total_inc_vat:
            deposit_amount = total_inc_vat
        
        quote.deposit_amount = deposit_amount
        quote.balance_amount = total_inc_vat - deposit_amount
        
        session.add(quote)
        session.commit()
        
        if not quote_data.defer_qualified_to_quoted_transition:
            apply_qualified_to_quoted_transition_for_customer(
                quote.customer_id,
                session,
                current_user.id,
                "Automatic transition: Quote created",
            )
        
        # Refresh to get items
        session.refresh(quote)
        statement = select(QuoteItem).where(QuoteItem.quote_id == quote.id)
        quote_items = session.exec(statement).all()
        
        return build_quote_response(quote, quote_items, session)
    except Exception as e:
        import traceback
        error_detail = str(e)
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Error creating quote: {error_detail}")


@router.get("", response_model=List[QuoteResponse])
async def get_all_quotes(
    status: Optional[QuoteStatus] = Query(None),
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """Get all quotes. By default excludes REJECTED and EXPIRED; pass status= to list only that status."""
    try:
        statement = select(Quote)
        if status is not None:
            statement = statement.where(Quote.status == status)
        else:
            statement = statement.where(Quote.status.notin_(QUOTE_LIST_EXCLUDED_STATUSES))
        statement = statement.order_by(Quote.created_at.desc())
        quotes = session.exec(statement).all()
        
        result = []
        for quote in quotes:
            item_statement = select(QuoteItem).where(QuoteItem.quote_id == quote.id).order_by(QuoteItem.sort_order)
            quote_items = session.exec(item_statement).all()
            result.append(build_quote_response(quote, quote_items, session))
        
        return result
    except Exception as e:
        import traceback
        error_detail = str(e)
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Error fetching quotes: {error_detail}")


# Opportunity Management Endpoints (must be before /{quote_id} to avoid route conflicts)

@router.get("/opportunities", response_model=List[QuoteResponse])
async def get_opportunities(
    stage: Optional[OpportunityStage] = None,
    owner_id: Optional[int] = None,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """Get all opportunities (quotes with opportunity_stage set)."""
    statement = select(Quote).where(
        Quote.opportunity_stage.isnot(None),
        Quote.status.notin_(QUOTE_LIST_EXCLUDED_STATUSES),
    )

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
        result.append(build_quote_response(quote, quote_items, session))
    
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
            Quote.status.notin_(QUOTE_LIST_EXCLUDED_STATUSES),
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
        result.append(build_quote_response(quote, quote_items, session))
    
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
    
    return build_quote_response(quote, quote_items, session)


@router.post("/opportunities/{quote_id}/won", response_model=QuoteResponse)
async def mark_opportunity_won(
    quote_id: int,
    body: OpportunityWonRequest,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """Mark an opportunity as WON (quote accepted)."""
    statement = select(Quote).where(Quote.id == quote_id)
    quote = session.exec(statement).first()
    if not quote:
        raise HTTPException(status_code=404, detail="Opportunity not found")
    if quote.opportunity_stage is None:
        raise HTTPException(status_code=404, detail="Quote is not an opportunity")
    old_status = quote.status
    if old_status != QuoteStatus.ACCEPTED:
        validate_and_record_redemptions_on_accept(session, quote.id)
        create_order_from_quote(quote, session, current_user.id)
    quote.status = QuoteStatus.ACCEPTED
    quote.opportunity_stage = OpportunityStage.WON
    quote.accepted_at = datetime.utcnow()
    quote.updated_at = datetime.utcnow()
    session.add(quote)
    session.commit()
    session.refresh(quote)
    if quote.customer_id and old_status != QuoteStatus.ACCEPTED:
        from app.workflow import auto_transition_lead_status, find_leads_by_customer_id
        leads = find_leads_by_customer_id(quote.customer_id, session)
        for lead in leads:
            if lead.status == LeadStatus.QUOTED:
                auto_transition_lead_status(
                    lead.id, LeadStatus.WON, session, current_user.id,
                    "Automatic transition: Quote accepted"
                )
    statement = select(QuoteItem).where(QuoteItem.quote_id == quote.id).order_by(QuoteItem.sort_order)
    quote_items = session.exec(statement).all()
    return build_quote_response(quote, quote_items, session)


@router.post("/opportunities/{quote_id}/close", response_model=QuoteResponse)
async def mark_opportunity_close(
    quote_id: int,
    body: Optional[OpportunityCloseRequest] = Body(None),
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """Mark a quote as closed without transitioning leads (e.g. another quote from same lead won)."""
    statement = select(Quote).where(Quote.id == quote_id)
    quote = session.exec(statement).first()
    if not quote:
        raise HTTPException(status_code=404, detail="Quote not found")
    if quote.status not in (QuoteStatus.SENT, QuoteStatus.VIEWED):
        raise HTTPException(
            status_code=400,
            detail=f"Only sent or viewed quotes can be closed. This quote has status: {quote.status}"
        )
    quote.status = QuoteStatus.REJECTED
    quote.opportunity_stage = OpportunityStage.LOST
    if body and body.reason:
        quote.loss_reason = body.reason
    quote.updated_at = datetime.utcnow()
    session.add(quote)
    session.commit()
    session.refresh(quote)
    # Do NOT transition leads - close means another quote may have won
    statement = select(QuoteItem).where(QuoteItem.quote_id == quote.id).order_by(QuoteItem.sort_order)
    quote_items = session.exec(statement).all()
    return build_quote_response(quote, quote_items, session)


@router.post("/opportunities/{quote_id}/lost", response_model=QuoteResponse)
async def mark_opportunity_lost(
    quote_id: int,
    body: OpportunityLostRequest,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """Mark an opportunity as LOST (quote rejected). Transitions associated leads to LOST."""
    statement = select(Quote).where(Quote.id == quote_id)
    quote = session.exec(statement).first()
    if not quote:
        raise HTTPException(status_code=404, detail="Opportunity not found")
    if quote.status not in (QuoteStatus.SENT, QuoteStatus.VIEWED):
        raise HTTPException(
            status_code=400,
            detail=f"Only sent or viewed quotes can be marked as lost. This quote has status: {quote.status}"
        )
    # Promote to opportunity if not already (allows Lose on any sent quote)
    if quote.opportunity_stage is None:
        quote.opportunity_stage = OpportunityStage.LOST
    old_status = quote.status
    quote.status = QuoteStatus.REJECTED
    quote.opportunity_stage = OpportunityStage.LOST
    quote.loss_reason = body.loss_reason
    quote.loss_category = body.loss_category
    quote.updated_at = datetime.utcnow()
    session.add(quote)
    session.commit()
    session.refresh(quote)
    if quote.customer_id and old_status != QuoteStatus.REJECTED:
        from app.workflow import auto_transition_lead_status, find_leads_by_customer_id
        leads = find_leads_by_customer_id(quote.customer_id, session)
        for lead in leads:
            if lead.status == LeadStatus.QUOTED:
                auto_transition_lead_status(
                    lead.id, LeadStatus.LOST, session, current_user.id,
                    "Automatic transition: Quote rejected"
                )
    statement = select(QuoteItem).where(QuoteItem.quote_id == quote.id).order_by(QuoteItem.sort_order)
    quote_items = session.exec(statement).all()
    return build_quote_response(quote, quote_items, session)


@router.post("/{quote_id}/apply-qualified-to-quoted", status_code=204)
async def apply_qualified_to_quoted_for_quote(
    quote_id: int,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """Run deferred QUALIFIED→QUOTED transition after a draft is finalized (e.g. bootstrap create flow)."""
    statement = select(Quote).where(Quote.id == quote_id)
    quote = session.exec(statement).first()
    if not quote:
        raise HTTPException(status_code=404, detail="Quote not found")
    apply_qualified_to_quoted_transition_for_customer(
        quote.customer_id,
        session,
        current_user.id,
        "Automatic transition: Quote created",
    )
    return Response(status_code=204)


def _build_duplicate_draft_payload_from_source(source: Quote, session: Session) -> QuoteDraftUpdate:
    """
    Build QuoteDraftUpdate from a persisted quote using pre-discount line fields (unit_price × qty).
    Template-based discounts are passed as discount_template_ids for re-application.
    QuoteDiscount rows with template_id NULL are not reproduced; staff may need to re-enter manual deals.
    """
    items_db = list(
        session.exec(
            select(QuoteItem)
            .where(QuoteItem.quote_id == source.id)
            .order_by(QuoteItem.sort_order)
        ).all()
    )
    if not items_db:
        raise HTTPException(status_code=400, detail="Source quote has no line items to duplicate.")

    id_to_index: Dict[int, int] = {}
    for i, row in enumerate(items_db):
        if row.id is not None:
            id_to_index[row.id] = i

    item_rows: List[QuoteItemCreate] = []
    for row in items_db:
        parent_idx = None
        if row.parent_quote_item_id is not None and row.parent_quote_item_id in id_to_index:
            parent_idx = id_to_index[row.parent_quote_item_id]
        item_rows.append(
            QuoteItemCreate(
                product_id=row.product_id,
                description=row.description,
                quantity=row.quantity,
                unit_price=row.unit_price,
                is_custom=row.is_custom,
                sort_order=row.sort_order,
                parent_index=parent_idx,
                line_type=row.line_type,
                include_in_building_discount=row.include_in_building_discount,
            )
        )

    discount_rows = session.exec(
        select(QuoteDiscount).where(QuoteDiscount.quote_id == source.id)
    ).all()
    template_ids: List[int] = []
    seen: set[int] = set()
    for d in discount_rows:
        if d.template_id is not None and d.template_id not in seen:
            seen.add(d.template_id)
            template_ids.append(d.template_id)

    return QuoteDraftUpdate(
        valid_until=source.valid_until,
        terms_and_conditions=source.terms_and_conditions,
        notes=source.notes,
        deposit_amount=source.deposit_amount,
        items=item_rows,
        discount_template_ids=template_ids if template_ids else None,
        temperature=source.temperature,
        include_spec_sheets=source.include_spec_sheets,
        include_available_optional_extras=source.include_available_optional_extras,
        include_delivery_installation_contact_note=source.include_delivery_installation_contact_note,
    )


@router.post("/{quote_id}/duplicate-to-draft", response_model=QuoteResponse)
async def duplicate_quote_to_draft(
    quote_id: int,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """Clone a non-draft quote into a new DRAFT with a new id and quote_number (see _build_duplicate_draft_payload_from_source)."""
    source = session.exec(select(Quote).where(Quote.id == quote_id)).first()
    if not source:
        raise HTTPException(status_code=404, detail="Quote not found")
    if source.status == QuoteStatus.DRAFT:
        raise HTTPException(
            status_code=400,
            detail="Source quote is already a draft. Use Edit to change it.",
        )
    if not source.customer_id or not source.lead_id:
        raise HTTPException(
            status_code=400,
            detail="Source quote must have customer_id and lead_id to duplicate.",
        )

    payload = _build_duplicate_draft_payload_from_source(source, session)

    new_quote = Quote(
        customer_id=source.customer_id,
        lead_id=source.lead_id,
        quote_number=generate_quote_number(session),
        version=1,
        status=QuoteStatus.DRAFT,
        subtotal=Decimal(0),
        discount_total=Decimal(0),
        total_amount=Decimal(0),
        deposit_amount=Decimal(0),
        balance_amount=Decimal(0),
        currency=source.currency or "GBP",
        created_by_id=current_user.id,
        sent_at=None,
        viewed_at=None,
        last_viewed_at=None,
        accepted_at=None,
        opportunity_stage=None,
        close_probability=None,
        expected_close_date=None,
        next_action=None,
        next_action_due_date=None,
        loss_reason=None,
        loss_category=None,
        owner_id=None,
        include_spec_sheets=source.include_spec_sheets,
        include_available_optional_extras=source.include_available_optional_extras,
        include_delivery_installation_contact_note=source.include_delivery_installation_contact_note,
    )
    session.add(new_quote)
    session.commit()
    session.refresh(new_quote)

    return _update_draft_quote_impl(new_quote.id, payload, session, current_user)


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
    return build_quote_response(quote, list(quote_items), session)


@router.delete("/{quote_id}", status_code=204)
async def delete_draft_quote(
    quote_id: int,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """Delete a draft quote. Only allowed when status is DRAFT."""
    statement = select(Quote).where(Quote.id == quote_id)
    quote = session.exec(statement).first()
    if not quote:
        raise HTTPException(status_code=404, detail="Quote not found")
    if quote.status != QuoteStatus.DRAFT:
        raise HTTPException(
            status_code=400,
            detail=f"Only draft quotes can be cancelled. This quote has status: {quote.status}"
        )
    delete_quote_cascade(session, quote_id)
    session.commit()
    return Response(status_code=204)


@router.put("/{quote_id}/draft", response_model=QuoteResponse)
async def update_draft_quote(
    quote_id: int,
    quote_data: QuoteDraftUpdate,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """Update a draft quote (items, metadata, discounts). Only allowed when status is DRAFT."""
    import traceback
    import sys
    try:
        return _update_draft_quote_impl(quote_id, quote_data, session, current_user)
    except HTTPException:
        raise
    except Exception as e:
        print(f"update_draft_quote error: {e}", file=sys.stderr, flush=True)
        print(traceback.format_exc(), file=sys.stderr, flush=True)
        raise HTTPException(
            status_code=500,
            detail=os.getenv("DEBUG", "false").lower() == "true"
            and str(e)
            or "Failed to update draft quote. Check server logs for details."
        )


def _update_draft_quote_impl(
    quote_id: int,
    quote_data: QuoteDraftUpdate,
    session: Session,
    current_user: User
):
    """Implementation of update_draft_quote."""
    statement = select(Quote).where(Quote.id == quote_id)
    quote = session.exec(statement).first()
    
    if not quote:
        raise HTTPException(status_code=404, detail="Quote not found")
    
    if quote.status != QuoteStatus.DRAFT:
        raise HTTPException(
            status_code=400,
            detail=f"Only draft quotes can be edited. This quote has status: {quote.status}"
        )
    
    # Delete existing items and discounts for this quote.
    # 1. Delete discounts first (QuoteDiscount.quote_item_id references QuoteItem)
    # 2. Null out parent_quote_item_id to avoid FK violation when deleting items (autoflush can reorder deletes)
    discount_statement = select(QuoteDiscount).where(QuoteDiscount.quote_id == quote_id)
    for discount in session.exec(discount_statement).all():
        session.delete(discount)
    session.flush()
    existing_items = list(session.exec(select(QuoteItem).where(QuoteItem.quote_id == quote_id)).all())
    for item in existing_items:
        if item.parent_quote_item_id is not None:
            item.parent_quote_item_id = None
            session.add(item)
    session.flush()
    for item in existing_items:
        session.delete(item)
    session.commit()
    
    # Build new items (same logic as create)
    subtotal = Decimal(0)
    items = []
    for item_data in quote_data.items:
        quantity = Decimal(str(item_data.quantity))
        unit_price = Decimal(str(item_data.unit_price))
        line_total = quantity * unit_price
        subtotal += line_total
        item = QuoteItem(
            quote_id=quote_id,
            product_id=item_data.product_id,
            description=item_data.description,
            quantity=quantity,
            unit_price=unit_price,
            line_total=line_total,
            discount_amount=Decimal(0),
            final_line_total=line_total,
            sort_order=item_data.sort_order or 0,
            is_custom=item_data.is_custom if item_data.is_custom is not None else False,
            line_type=getattr(item_data, "line_type", None),
            include_in_building_discount=getattr(item_data, "include_in_building_discount", True),
        )
        items.append(item)
    
    for item in items:
        session.add(item)
    session.commit()
    
    # Refresh to get item IDs, then set parent_quote_item_id
    statement = select(QuoteItem).where(QuoteItem.quote_id == quote_id).order_by(QuoteItem.sort_order)
    quote_items = list(session.exec(statement).all())
    for i, db_item in enumerate(quote_items):
        if i < len(quote_data.items):
            item_data = quote_data.items[i]
            parent_index = getattr(item_data, "parent_index", None)
            if parent_index is not None and 0 <= parent_index < len(quote_items):
                db_item.parent_quote_item_id = quote_items[parent_index].id
                session.add(db_item)
    if quote_items and any(getattr(quote_data.items[i], "parent_index", None) is not None for i in range(min(len(quote_data.items), len(quote_items)))):
        session.commit()
        statement = select(QuoteItem).where(QuoteItem.quote_id == quote_id).order_by(QuoteItem.sort_order)
        quote_items = list(session.exec(statement).all())
    
    # Update quote metadata
    quote.subtotal = subtotal
    quote.discount_total = Decimal(0)
    quote.total_amount = subtotal
    if quote_data.valid_until is not None:
        quote.valid_until = quote_data.valid_until
    if quote_data.terms_and_conditions is not None:
        quote.terms_and_conditions = quote_data.terms_and_conditions
    if quote_data.notes is not None:
        quote.notes = quote_data.notes
    if quote_data.temperature is not None:
        quote.temperature = quote_data.temperature
    if quote_data.include_spec_sheets is not None:
        quote.include_spec_sheets = quote_data.include_spec_sheets
    if quote_data.include_available_optional_extras is not None:
        quote.include_available_optional_extras = quote_data.include_available_optional_extras
    if quote_data.include_delivery_installation_contact_note is not None:
        quote.include_delivery_installation_contact_note = quote_data.include_delivery_installation_contact_note

    # Apply discounts if provided
    if quote_data.discount_template_ids:
        assert_templates_not_expired_for_apply(session, quote_data.discount_template_ids)
        for template_id in quote_data.discount_template_ids:
            template_statement = select(DiscountTemplate).where(
                DiscountTemplate.id == template_id,
                DiscountTemplate.is_active == True
            )
            discount_template = session.exec(template_statement).first()
            if not discount_template:
                continue
            statement = select(QuoteItem).where(QuoteItem.quote_id == quote_id)
            quote_items = list(session.exec(statement).all())
            if discount_template.is_giveaway:
                for item in quote_items:
                    if not _item_eligible_for_product_scope_discount(item):
                        continue
                    if item.product_id and discount_template.scope == DiscountScope.PRODUCT:
                        item.discount_amount = item.line_total
                        item.final_line_total = Decimal(0)
                        session.add(item)
                        quote_discount = QuoteDiscount(
                            quote_id=quote.id,
                            quote_item_id=item.id,
                            template_id=discount_template.id,
                            discount_type=DiscountType.PERCENTAGE,
                            discount_value=Decimal(100),
                            scope=discount_template.scope,
                            discount_amount=item.line_total,
                            description=discount_template.name,
                            applied_by_id=current_user.id
                        )
                        session.add(quote_discount)
            else:
                apply_discount_to_quote(quote, discount_template, quote_items, session, current_user)
            for item in quote_items:
                session.add(item)
    
    session.commit()
    session.refresh(quote)
    statement = select(QuoteItem).where(QuoteItem.quote_id == quote_id)
    quote_items = list(session.exec(statement).all())
    item_discount_total = sum(item.discount_amount for item in quote_items)
    discount_statement = select(QuoteDiscount).where(
        QuoteDiscount.quote_id == quote_id,
        QuoteDiscount.quote_item_id.is_(None)
    )
    quote_level_discounts = session.exec(discount_statement).all()
    quote_level_discount_total = sum(d.discount_amount for d in quote_level_discounts)
    quote.discount_total = item_discount_total + quote_level_discount_total
    quote.total_amount = quote.subtotal - quote.discount_total
    if quote.total_amount < 0:
        quote.total_amount = Decimal(0)
    total_inc_vat = quote.total_amount * (Decimal("1") + VAT_RATE_DECIMAL)
    # Recalculate deposit and balance (inc VAT) — same as create_quote: after final totals
    if quote_data.deposit_amount is not None:
        deposit_amount = Decimal(str(quote_data.deposit_amount))  # Client sends inc VAT
    else:
        deposit_amount = total_inc_vat * Decimal("0.5")
    if deposit_amount > total_inc_vat:
        deposit_amount = total_inc_vat
    quote.deposit_amount = deposit_amount
    quote.balance_amount = total_inc_vat - deposit_amount
    quote.updated_at = datetime.utcnow()
    session.add(quote)
    session.commit()
    session.refresh(quote)
    statement = select(QuoteItem).where(QuoteItem.quote_id == quote_id).order_by(QuoteItem.sort_order)
    quote_items = session.exec(statement).all()
    return build_quote_response(quote, quote_items, session)


@router.get("/customers/{customer_id}", response_model=List[QuoteResponse])
async def get_customer_quotes(
    customer_id: int,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """Get all quotes for a customer."""
    customer = session.exec(select(Customer).where(Customer.id == customer_id)).first()
    customer_name = customer.name if customer else None
    statement = (
        select(Quote)
        .where(
            Quote.customer_id == customer_id,
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


@router.get("/{quote_id}/view-link", response_model=QuoteViewLinkResponse)
async def get_quote_view_link(
    quote_id: int,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """Return the latest customer view URL for this quote; mints a share link if none exists yet."""
    quote = session.exec(select(Quote).where(Quote.id == quote_id)).first()
    if not quote:
        raise HTTPException(status_code=404, detail="Quote not found")
    statement = (
        select(QuoteEmail)
        .where(QuoteEmail.quote_id == quote_id, QuoteEmail.view_token.isnot(None))
        .order_by(QuoteEmail.sent_at.desc())
        .limit(1)
    )
    quote_email = session.exec(statement).first()
    base_url = _frontend_base_url()
    if quote_email and quote_email.view_token:
        if base_url:
            view_url = f"{base_url.rstrip('/')}/{customer_view_path_segment(session, quote.id, quote_email.view_token)}"
            return QuoteViewLinkResponse(view_url=view_url)
        return QuoteViewLinkResponse(view_url=None)

    if not quote.customer_id:
        raise HTTPException(status_code=400, detail="Quote must be associated with a customer")
    customer = session.exec(select(Customer).where(Customer.id == quote.customer_id)).first()
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")

    _, view_url, _ = ensure_quote_share_link(
        session,
        quote,
        customer,
        current_user,
        include_available_extras=getattr(quote, "include_available_optional_extras", False),
    )
    return QuoteViewLinkResponse(view_url=view_url)


@router.post("/{quote_id}/share-link", response_model=QuoteShareLinkResponse)
async def post_quote_share_link(
    quote_id: int,
    body: Optional[QuoteShareLinkRequest] = Body(default=None),
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """Ensure a customer view token exists and return the URL (no email or SMS)."""
    req = body or QuoteShareLinkRequest()
    quote = session.exec(select(Quote).where(Quote.id == quote_id)).first()
    if not quote:
        raise HTTPException(status_code=404, detail="Quote not found")
    if not quote.customer_id:
        raise HTTPException(status_code=400, detail="Quote must be associated with a customer")
    customer = session.exec(select(Customer).where(Customer.id == quote.customer_id)).first()
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")

    quote_email, view_url, _ = ensure_quote_share_link(
        session,
        quote,
        customer,
        current_user,
        include_available_extras=bool(req.include_available_extras),
    )
    return QuoteShareLinkResponse(view_url=view_url, quote_email_id=quote_email.id)


@router.post("/{quote_id}/send-sms", response_model=QuoteSendSmsResponse)
async def post_quote_send_sms(
    quote_id: int,
    data: Optional[QuoteSendSmsRequest] = Body(default=None),
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """Send the customer view link by SMS (Twilio). Mints a share link if needed."""
    req = data or QuoteSendSmsRequest()
    quote = session.exec(select(Quote).where(Quote.id == quote_id)).first()
    if not quote:
        raise HTTPException(status_code=404, detail="Quote not found")
    if not quote.customer_id:
        raise HTTPException(status_code=400, detail="Quote must be associated with a customer")
    customer = session.exec(select(Customer).where(Customer.id == quote.customer_id)).first()
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")

    quote_email, view_url, _ = ensure_quote_share_link(
        session,
        quote,
        customer,
        current_user,
        include_available_extras=bool(req.include_available_extras),
    )

    to_phone = (req.to_phone or "").strip() or (customer.phone or "").strip()
    if not to_phone:
        raise HTTPException(
            status_code=400,
            detail="No phone number; set to_phone in the request or add a phone on the customer.",
        )

    if (req.body or "").strip():
        sms_body = (req.body or "").strip()
    else:
        has_order = session.exec(select(Order).where(Order.quote_id == quote.id)).first() is not None
        label = "order" if has_order else "quote"
        sms_body = f"View your {label}: {view_url}"

    success, sid, error = send_sms(to_phone, sms_body)
    if not success:
        raise HTTPException(status_code=500, detail=error or "Failed to send SMS")

    from_phone = (os.getenv("TWILIO_PHONE_NUMBER") or "").strip()
    now = datetime.utcnow()
    msg = SmsMessage(
        customer_id=customer.id,
        lead_id=quote.lead_id,
        direction=SmsDirection.SENT,
        from_phone=from_phone,
        to_phone=normalize_phone(to_phone),
        body=sms_body,
        twilio_sid=sid,
        sent_at=now,
        created_by_id=current_user.id,
    )
    session.add(msg)
    session.commit()
    session.refresh(msg)

    activity = Activity(
        customer_id=quote.customer_id,
        activity_type=ActivityType.SMS_SENT,
        notes=f"Quote {quote.quote_number} link sent by SMS to {to_phone}",
        created_by_id=current_user.id,
    )
    session.add(activity)
    session.commit()

    return QuoteSendSmsResponse(
        view_url=view_url,
        quote_email_id=quote_email.id,
        message="SMS sent successfully",
    )


@router.post("/{quote_id}/send-email", response_model=QuoteEmailSendResponse)
async def send_quote_email_endpoint(
    quote_id: int,
    email_data: str = Form(..., description="JSON string matching QuoteEmailSendRequest"),
    attachments: Optional[Union[UploadFile, List[UploadFile]]] = File(None),
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """Send a quote email with a link to view the quote online. Optional file attachments (same limits as compose email: 10MB each, 25MB total)."""
    try:
        try:
            req = QuoteEmailSendRequest.model_validate(json.loads(email_data))
        except json.JSONDecodeError as e:
            raise HTTPException(status_code=400, detail=f"Invalid email_data JSON: {e}")
        except Exception as e:
            raise HTTPException(status_code=400, detail=str(e))

        # Check email configured: Microsoft Graph, Resend, or SMTP
        if not is_email_configured(current_user.id):
            raise HTTPException(
                status_code=400,
                detail="Email not configured. Add Microsoft Graph vars (CLIENT_ID, CLIENT_SECRET, TENANT_ID, MSGRAPH_FROM_EMAIL), RESEND_API_KEY in Railway, or configure SMTP in My Settings → Email Settings."
            )
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

        # Generate view token for "View your quote" link (open tracking)
        view_token = uuid.uuid4().hex
        frontend_base_url = (os.getenv("FRONTEND_BASE_URL") or os.getenv("FRONTEND_URL") or os.getenv("PUBLIC_FRONTEND_URL") or "").strip() or None

        qt_statement = select(QuoteTemplate).where(QuoteTemplate.id == req.template_id)
        if not session.exec(qt_statement).first():
            raise HTTPException(status_code=404, detail="Quote template not found")

        attachment_list: List[dict] = []
        attachment_metadata: List[dict] = []
        total_size = 0

        template_docs_statement = (
            select(QuoteTemplateSalesDocument, SalesDocument)
            .join(SalesDocument, QuoteTemplateSalesDocument.sales_document_id == SalesDocument.id)
            .where(QuoteTemplateSalesDocument.quote_template_id == req.template_id)
            .order_by(QuoteTemplateSalesDocument.sort_order)
        )
        for _link, sales_doc in session.exec(template_docs_statement).all():
            path = Path(sales_doc.file_path)
            if not path.is_file():
                raise HTTPException(
                    status_code=400,
                    detail=(
                        f"Quote template attachment file is missing on disk: "
                        f"{sales_doc.name} ({sales_doc.filename}). Re-upload the document in Sales Documents or remove it from the template."
                    ),
                )
            content = path.read_bytes()
            size = len(content)
            if size > MAX_ATTACHMENT_SIZE:
                raise HTTPException(
                    status_code=400,
                    detail=(
                        f"Template-linked document '{sales_doc.filename}' exceeds 10MB limit"
                    ),
                )
            total_size += size
            if total_size > MAX_TOTAL_ATTACHMENTS:
                raise HTTPException(
                    status_code=400,
                    detail="Total attachments (template + uploads) exceed 25MB limit",
                )
            safe_name = _sanitize_filename(sales_doc.filename)
            attachment_list.append({"filename": safe_name, "content": content})
            attachment_metadata.append({"filename": safe_name, "from_template": True})

        for f in _normalize_upload_files(attachments):
            if not f.filename:
                continue
            content = await f.read()
            size = len(content)
            if size > MAX_ATTACHMENT_SIZE:
                raise HTTPException(
                    status_code=400,
                    detail=f"Attachment '{f.filename}' exceeds 10MB limit",
                )
            total_size += size
            if total_size > MAX_TOTAL_ATTACHMENTS:
                raise HTTPException(
                    status_code=400,
                    detail="Total attachments exceed 25MB limit",
                )
            safe_name = _sanitize_filename(f.filename)
            attachment_list.append({"filename": safe_name, "content": content})
            attachment_metadata.append({"filename": safe_name})

        success, message_id, error, pdf_buffer, email_subject, email_body_html, email_body_text = send_quote_email(
            quote=quote,
            customer=customer,
            to_email=req.to_email,
            session=session,
            template_id=req.template_id,
            cc=req.cc,
            bcc=req.bcc,
            custom_message=req.custom_message,
            user_id=current_user.id,
            view_token=view_token,
            frontend_base_url=frontend_base_url,
            attachments=attachment_list if attachment_list else None,
        )
        
        if not success:
            import sys
            print(f"Quote email send failed: {error}", file=sys.stderr, flush=True)
            raise HTTPException(status_code=500, detail=f"Failed to send quote email: {error}")
        
        # Use rendered subject and body_html, fallback to defaults if None
        final_subject = email_subject or f"Quote {quote.quote_number}"
        final_body_html = email_body_html or f"<p>Please use the link in the email to view quote {quote.quote_number}.</p>"
        
        # Create Email record (body_html matches QuoteEmail so thread/history views can show content)
        attachments_json = json.dumps(attachment_metadata) if attachment_metadata else None
        email_record = Email(
            customer_id=quote.customer_id,
            message_id=message_id,
            thread_id=message_id,
            direction=EmailDirection.SENT,
            from_email=current_user.email,
            to_email=req.to_email,
            cc=req.cc,
            bcc=req.bcc,
            subject=final_subject,
            body_html=final_body_html,
            body_text=email_body_text,
            attachments=attachments_json,
            sent_at=datetime.utcnow(),
            created_by_id=current_user.id
        )
        session.add(email_record)
        session.commit()
        session.refresh(email_record)
        
        # Create QuoteEmail record (view_token for public view link / open tracking)
        quote_email = QuoteEmail(
            quote_id=quote.id,
            to_email=req.to_email,
            subject=final_subject,
            body_html=final_body_html,
            body_text=email_body_text,
            tracking_id=message_id or f"quote-{quote.id}-{datetime.utcnow().timestamp()}",
            view_token=view_token,
            include_available_extras=getattr(req, "include_available_extras", False) or False,
        )
        session.add(quote_email)
        
        # Update quote: status to SENT and sent_at
        quote.status = QuoteStatus.SENT
        quote.sent_at = datetime.utcnow()
        quote.updated_at = datetime.utcnow()
        if quote.temperature is None:
            quote.temperature = QuoteTemperature.COLD
        if quote.opportunity_stage == OpportunityStage.CONCEPT:
            quote.opportunity_stage = OpportunityStage.QUOTE_SENT
        session.add(quote)
        
        session.commit()
        session.refresh(quote_email)
        
        # Create EMAIL_SENT activity
        activity = Activity(
            customer_id=quote.customer_id,
            activity_type=ActivityType.EMAIL_SENT,
            notes=f"Quote {quote.quote_number} sent to {req.to_email}",
            created_by_id=current_user.id
        )
        session.add(activity)
        session.commit()
        
        view_url = None
        if view_token and frontend_base_url:
            base = frontend_base_url.rstrip("/")
            view_url = f"{base}/{customer_view_path_segment(session, quote.id, view_token)}"
        test_mode = getattr(current_user, "email_test_mode", False)

        return QuoteEmailSendResponse(
            email_id=email_record.id,
            quote_email_id=quote_email.id,
            message="Quote email sent successfully",
            view_url=view_url,
            test_mode=test_mode,
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
    
    # Recalculate balance when deposit is updated (deposit/balance are inc VAT)
    if "deposit_amount" in update_data:
        total_inc_vat = quote.total_amount * (Decimal("1") + VAT_RATE_DECIMAL)
        deposit = Decimal(str(update_data["deposit_amount"]))
        if deposit > total_inc_vat:
            deposit = total_inc_vat
        quote.deposit_amount = deposit
        quote.balance_amount = total_inc_vat - deposit
    
    # Sync quote status from opportunity_stage when stage is WON/LOST (so status updates when only stage is sent)
    if quote.opportunity_stage == OpportunityStage.WON and quote.status != QuoteStatus.ACCEPTED:
        quote.status = QuoteStatus.ACCEPTED
        quote.accepted_at = datetime.utcnow()
    elif quote.opportunity_stage == OpportunityStage.LOST and quote.status != QuoteStatus.REJECTED:
        quote.status = QuoteStatus.REJECTED
    
    # Update opportunity stage from quote status when status was sent but stage was not
    if quote_data.status and not quote_data.opportunity_stage:
        if quote_data.status == QuoteStatus.ACCEPTED:
            quote.opportunity_stage = OpportunityStage.WON
        elif quote_data.status == QuoteStatus.REJECTED:
            quote.opportunity_stage = OpportunityStage.LOST
        elif quote_data.status == QuoteStatus.SENT and quote.opportunity_stage == OpportunityStage.CONCEPT:
            quote.opportunity_stage = OpportunityStage.QUOTE_SENT
    
    # Set accepted_at if status changed to ACCEPTED (when status was sent explicitly)
    if quote.status == QuoteStatus.ACCEPTED and old_status != QuoteStatus.ACCEPTED:
        if not quote.accepted_at:
            quote.accepted_at = datetime.utcnow()
        validate_and_record_redemptions_on_accept(session, quote.id)
        create_order_from_quote(quote, session, current_user.id)
    
    # Mandatory next action validation (for open opportunities)
    if quote.opportunity_stage and quote.opportunity_stage not in [OpportunityStage.WON, OpportunityStage.LOST]:
        if not quote.next_action or not quote.next_action_due_date:
            raise HTTPException(
                status_code=400,
                detail="next_action and next_action_due_date are required for open opportunities"
            )
    
    quote.updated_at = datetime.utcnow()
    session.add(quote)
    session.commit()
    session.refresh(quote)
    
    # QUOTED → WON/LOST: Transition lead when quote status changed to ACCEPTED or REJECTED
    if quote.customer_id and (quote.status == QuoteStatus.ACCEPTED or quote.status == QuoteStatus.REJECTED):
        from app.workflow import auto_transition_lead_status, find_leads_by_customer_id
        leads = find_leads_by_customer_id(quote.customer_id, session)
        
        if quote.status == QuoteStatus.ACCEPTED and old_status != QuoteStatus.ACCEPTED:
            for lead in leads:
                if lead.status == LeadStatus.QUOTED:
                    auto_transition_lead_status(
                        lead.id,
                        LeadStatus.WON,
                        session,
                        current_user.id,
                        "Automatic transition: Quote accepted"
                    )
        elif quote.status == QuoteStatus.REJECTED and old_status != QuoteStatus.REJECTED:
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
    
    return build_quote_response(quote, quote_items, session)


@router.post("/{quote_id}/discounts")
async def apply_discount_to_quote_endpoint(
    quote_id: int,
    template_id: int = Query(...),
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """Apply a discount template to an existing quote."""
    # Get quote
    statement = select(Quote).where(Quote.id == quote_id)
    quote = session.exec(statement).first()
    
    if not quote:
        raise HTTPException(status_code=404, detail="Quote not found")
    
    # Get discount template
    template_statement = select(DiscountTemplate).where(
        DiscountTemplate.id == template_id,
        DiscountTemplate.is_active == True
    )
    discount_template = session.exec(template_statement).first()
    
    if not discount_template:
        raise HTTPException(status_code=404, detail="Discount template not found")
    
    assert_templates_not_expired_for_apply(session, [template_id])
    
    # Get quote items
    item_statement = select(QuoteItem).where(QuoteItem.quote_id == quote.id)
    quote_items = session.exec(item_statement).all()
    
    if not quote_items:
        raise HTTPException(status_code=400, detail="Quote has no items")
    
    # Apply discount
    if discount_template.is_giveaway:
        # Handle giveaway - apply 100% discount to building products only (not optional extras)
        for item in quote_items:
            if not _item_eligible_for_product_scope_discount(item):
                continue
            if item.product_id and discount_template.scope == DiscountScope.PRODUCT:
                item.discount_amount = item.line_total
                item.final_line_total = Decimal(0)
                session.add(item)
                
                quote_discount = QuoteDiscount(
                    quote_id=quote.id,
                    quote_item_id=item.id,
                    template_id=discount_template.id,
                    discount_type=DiscountType.PERCENTAGE,
                    discount_value=Decimal(100),
                    scope=discount_template.scope,
                    discount_amount=item.line_total,
                    description=discount_template.name,
                    applied_by_id=current_user.id
                )
                session.add(quote_discount)
    else:
        # Apply regular discount
        apply_discount_to_quote(quote, discount_template, quote_items, session, current_user)
    
    # Recalculate totals
    item_discount_total = sum(item.discount_amount for item in quote_items)
    discount_statement = select(QuoteDiscount).where(
        QuoteDiscount.quote_id == quote.id,
        QuoteDiscount.quote_item_id.is_(None)
    )
    quote_level_discounts = session.exec(discount_statement).all()
    quote_level_discount_total = sum(d.discount_amount for d in quote_level_discounts)
    
    quote.discount_total = item_discount_total + quote_level_discount_total
    quote.total_amount = quote.subtotal - quote.discount_total
    if quote.total_amount < 0:
        quote.total_amount = Decimal(0)
    
    # Recalculate deposit and balance (inc VAT)
    total_inc_vat = quote.total_amount * (Decimal("1") + VAT_RATE_DECIMAL)
    if quote.deposit_amount > total_inc_vat:
        quote.deposit_amount = total_inc_vat
    quote.balance_amount = total_inc_vat - quote.deposit_amount
    
    session.add(quote)
    session.commit()
    session.refresh(quote)
    
    return build_quote_response(quote, quote_items, session)


@router.get("/{quote_id}/preview-pdf")
async def preview_quote_pdf(
    quote_id: int,
    include_spec_sheets: bool | None = Query(default=None, description="Override quote setting. False to exclude spec sheets (e.g. for order/invoice context)."),
    include_optional_extras: bool | None = Query(
        default=None,
        description="Override quote setting for 'Other Available Options' section. None uses quote.include_available_optional_extras.",
    ),
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
        use_spec_sheets = include_spec_sheets if include_spec_sheets is not None else getattr(quote, "include_spec_sheets", True)
        use_optional_extras = (
            include_optional_extras
            if include_optional_extras is not None
            else getattr(quote, "include_available_optional_extras", False)
        )
        available_extras = (
            get_available_optional_extras_for_quote(list(quote_items), session)
            if use_optional_extras
            else None
        )
        pdf_buffer = generate_quote_pdf(
            quote, customer, quote_items, company_settings, session,
            include_spec_sheets=use_spec_sheets,
            available_optional_extras=available_extras,
        )
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
