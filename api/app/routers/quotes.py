import json
from pathlib import Path
from pydantic import ValidationError
from fastapi import APIRouter, Body, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import Response
from sqlmodel import Session, select, or_, and_
from sqlalchemy import func, true, String as SAString, delete, update
from datetime import datetime
from typing import Dict, List, Literal, Optional, Tuple
from html import escape
from app.database import get_session
from app.models import (
    Quote,
    QuoteConfiguration,
    QuoteItem,
    QuoteTemplate,
    QuoteTemplateSalesDocument,
    SalesDocument,
    Customer,
    User,
    QuoteEmail,
    Email,
    EmailDirection,
    Activity,
    ActivityType,
    CompanySettings,
    Lead,
    LeadType,
    LeadStatus,
    QuoteStatus,
    QuoteTemperature,
    OpportunityStage,
    LossCategory,
    DiscountTemplate,
    QuoteDiscount,
    DiscountType,
    DiscountScope,
    CustomerFile,
    Order,
    OrderItem,
    QuoteItemLineType,
    QuoteFulfillmentMethod,
    DiscountRequest,
    DiscountRequestStatus,
    SmsMessage,
    SmsDirection,
    MessengerMessage,
    MessengerDirection,
    EmailTemplate,
    SmsTemplate,
)
from app.auth import get_current_user, require_configurator_access
from app.configurator_service import build_configurator_preview, resolve_quote_customer_postcode
from app.schemas import (
    ConfiguratorGeneratedLine,
    QuoteConfigurationPayload,
    ConfiguratorDeliveryEstimateInclusion,
    QuoteConfigurationResponse,
    QuoteCreate, QuoteUpdate, QuoteDraftUpdate, QuoteResponse, QuoteListResponse, QuoteItemCreate, QuoteItemResponse,
    QuoteEmailSendRequest, QuoteEmailSendResponse, QuoteViewLinkResponse,
    QuoteShareLinkRequest, QuoteShareLinkResponse, QuoteSendSmsRequest, QuoteSendSmsResponse,
    QuoteSendPaymentLinkRequest, QuoteSendPaymentLinkResponse,
    OpportunityWonRequest, OpportunityLostRequest, OpportunityCloseRequest,
    QuoteDiscountResponse, CustomerHistoryEventType
)
from app.order_audit import record_order_audit_event
from app.delivery_location import (
    assert_alternate_delivery_valid,
    copy_delivery_location_fields,
    delivery_location_response_fields,
    sync_delivery_location_from_payload,
)
from app.quote_email_service import send_quote_email
from app.routers.emails import (
    MAX_ATTACHMENT_SIZE,
    MAX_TOTAL_ATTACHMENTS,
    _normalize_upload_files,
    _sanitize_filename,
)
from app.sales_document_service import load_sales_document_bytes
from app.customer_view_links import customer_view_path_segment
from app.email_service import is_email_configured, build_activity_email_notes, send_email, _html_to_plain
from app.email_template_service import render_email_template
from app.sms_template_service import render_sms_template
from app.payment_link_service import (
    validate_payment_url,
    quote_payment_link_template_context,
    default_quote_payment_sms_body,
    default_quote_payment_email_subject,
    default_quote_payment_email_html,
)
from app.sms_service import (
    send_sms,
    normalize_phone,
    is_unsubscribed_recipient_error,
    resolve_sms_to_phone,
)
from app.quote_pdf_service import generate_quote_pdf
from app.available_optional_extras import (
    get_available_optional_extras_for_quote,
    should_show_available_optional_extras_on_quote,
)
from app.specification_sheet import (
    resolve_specification_sheet_text,
    resolve_specification_sheet_image_url,
    has_specification_sheet_content,
    should_include_specification_sheet,
    should_include_specification_sheet_for_staff_preview,
)
from app.quote_displayed_optional_extras import (
    get_displayed_optional_extra_ids,
    sync_quote_displayed_optional_extras,
)
from app.reminder_service import get_last_activity_date, dismiss_open_reminders_for_quote
from app.constants import (
    QUOTE_LIST_EXCLUDED_STATUSES,
    QUOTE_LIVE_STATUSES,
    QUOTE_CLOSED_STATUSES,
    VAT_RATE_DECIMAL,
    LIST_PAGE_SIZE_DEFAULT,
    LIST_PAGE_SIZE_MAX,
)
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


def _transition_customer_leads_to_quoted_after_send(
    customer_id: Optional[int],
    session: Session,
    current_user_id: int,
) -> None:
    """Move all QUALIFIED leads on the customer to QUOTED after a quote is sent or shared."""
    if not customer_id:
        return
    apply_qualified_to_quoted_transition_for_customer(
        customer_id,
        session,
        current_user_id,
        reason="Automatic transition: Quote sent",
    )


def _frontend_base_url() -> Optional[str]:
    return (os.getenv("FRONTEND_BASE_URL") or os.getenv("FRONTEND_URL") or os.getenv("PUBLIC_FRONTEND_URL") or "").strip() or None


def ensure_quote_share_link(
    session: Session,
    quote: Quote,
    customer: Customer,
    current_user: User,
    include_available_extras: bool,
    include_specification_sheet: bool = False,
) -> tuple[QuoteEmail, str, bool]:
    """
    Ensure a QuoteEmail row with view_token exists (reuse latest with token).
    If newly created: set quote to SENT, add NOTE activity.
    If reusing and include_available_extras or include_specification_sheet is True, upgrade flags on the row.
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
        upgraded = False
        if include_available_extras and not getattr(quote_email, "include_available_extras", False):
            quote_email.include_available_extras = True
            upgraded = True
        if include_specification_sheet and not getattr(quote_email, "include_specification_sheet", False):
            quote_email.include_specification_sheet = True
            upgraded = True
        if upgraded:
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
        include_specification_sheet=include_specification_sheet,
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

    _transition_customer_leads_to_quoted_after_send(
        quote.customer_id, session, current_user.id
    )

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
        installation_hours=getattr(item, "installation_hours", None),
    )


def _installation_hours_for_quote_item_create(item_data: QuoteItemCreate) -> Optional[Decimal]:
    """Persist per-unit install hours only on custom lines (no catalog product)."""
    is_custom = item_data.is_custom if item_data.is_custom is not None else False
    if item_data.product_id is not None and not is_custom:
        return None
    if item_data.installation_hours is None:
        return None
    return Decimal(str(item_data.installation_hours))


_DELIVERY_LINE_DESCRIPTIONS = frozenset(
    ("Delivery & Installation", "Delivery only", "Delivery", "Installation")
)


def _assert_collection_fulfillment_items_valid(
    fulfillment_method: QuoteFulfillmentMethod,
    items: List[QuoteItemCreate],
) -> None:
    """Collection quotes must not include delivery or installation lines."""
    if fulfillment_method != QuoteFulfillmentMethod.COLLECTION:
        return
    for item_data in items:
        line_type = getattr(item_data, "line_type", None)
        if line_type in (QuoteItemLineType.DELIVERY, QuoteItemLineType.INSTALLATION):
            raise HTTPException(
                status_code=400,
                detail="Collection quotes cannot include delivery or installation line items.",
            )
        desc = (item_data.description or "").strip()
        if desc in _DELIVERY_LINE_DESCRIPTIONS:
            raise HTTPException(
                status_code=400,
                detail="Collection quotes cannot include delivery or installation line items.",
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
    if item.description in ("Delivery & Installation", "Delivery only"):
        return False
    return True


def batch_lead_quotes_sent_counts(session: Session, lead_ids: List[int]) -> Dict[int, int]:
    """Per lead_id: count of quotes with sent_at set (matches leads list `quotes_sent_count` idea)."""
    if not lead_ids:
        return {}
    rows = session.exec(
        select(Quote.lead_id, func.count(Quote.id))
        .where(Quote.lead_id.in_(lead_ids), Quote.sent_at.isnot(None))
        .group_by(Quote.lead_id)
    ).all()
    out: Dict[int, int] = {}
    for row in rows:
        lid, cnt = row[0], row[1]
        if lid is not None:
            out[int(lid)] = int(cnt)
    return out


def batch_reply_metrics_since_sent(session: Session, quotes: List[Quote]) -> Dict[int, Tuple[bool, int]]:
    """
    Per quote id: (customer_replied_since_quote_sent, inbound_count_since_quote_sent).
    Inbound = Email/SMS/Messenger RECEIVED for the quote's customer and/or lead, timestamp strictly after quote.sent_at.
    """
    out: Dict[int, Tuple[bool, int]] = {}
    dated = [q for q in quotes if q.sent_at and (q.customer_id or q.lead_id)]
    if not dated:
        for q in quotes:
            out[q.id] = (False, 0)
        return out

    customer_ids = list({q.customer_id for q in dated if q.customer_id})
    lead_ids = list({q.lead_id for q in dated if q.lead_id})
    min_ts = min(q.sent_at for q in dated if q.sent_at)

    email_events: List[Tuple[int, datetime]] = []
    if customer_ids:
        ts_col = func.coalesce(Email.received_at, Email.created_at)
        rows = session.exec(
            select(Email.customer_id, ts_col).where(
                Email.direction == EmailDirection.RECEIVED,
                Email.customer_id.in_(customer_ids),
                ts_col >= min_ts,
            )
        ).all()
        for row in rows:
            cid, ts = row[0], row[1]
            if ts is not None and cid is not None:
                email_events.append((int(cid), ts))

    sms_events: List[Tuple[Optional[int], Optional[int], datetime]] = []
    if customer_ids or lead_ids:
        ts_sms = func.coalesce(SmsMessage.received_at, SmsMessage.created_at)
        parts = []
        if customer_ids:
            parts.append(SmsMessage.customer_id.in_(customer_ids))
        if lead_ids:
            parts.append(SmsMessage.lead_id.in_(lead_ids))
        cond_or = or_(*parts) if len(parts) > 1 else parts[0]
        rows = session.exec(
            select(SmsMessage.customer_id, SmsMessage.lead_id, ts_sms).where(
                SmsMessage.direction == SmsDirection.RECEIVED,
                cond_or,
                ts_sms >= min_ts,
            )
        ).all()
        for row in rows:
            scid, slid, ts = row[0], row[1], row[2]
            if ts is not None:
                sms_events.append((scid, slid, ts))

    messenger_events: List[Tuple[Optional[int], Optional[int], datetime]] = []
    if customer_ids or lead_ids:
        ts_mm = func.coalesce(MessengerMessage.received_at, MessengerMessage.created_at)
        parts_m = []
        if customer_ids:
            parts_m.append(MessengerMessage.customer_id.in_(customer_ids))
        if lead_ids:
            parts_m.append(MessengerMessage.lead_id.in_(lead_ids))
        cond_m = or_(*parts_m) if len(parts_m) > 1 else parts_m[0]
        rows = session.exec(
            select(MessengerMessage.customer_id, MessengerMessage.lead_id, ts_mm).where(
                MessengerMessage.direction == MessengerDirection.RECEIVED,
                cond_m,
                ts_mm >= min_ts,
            )
        ).all()
        for row in rows:
            mcid, mlid, ts = row[0], row[1], row[2]
            if ts is not None:
                messenger_events.append((mcid, mlid, ts))

    for q in quotes:
        if not q.sent_at or (not q.customer_id and not q.lead_id):
            out[q.id] = (False, 0)
            continue
        st = q.sent_at
        cid = q.customer_id
        lid = q.lead_id
        cnt = 0
        for ecid, ts in email_events:
            if cid and ecid == cid and ts > st:
                cnt += 1
        for scid, slid, ts in sms_events:
            if ts <= st:
                continue
            matched = False
            if cid and scid is not None and scid == cid:
                matched = True
            if lid and slid is not None and slid == lid:
                matched = True
            if matched:
                cnt += 1
        for mcid, mlid, ts in messenger_events:
            if ts <= st:
                continue
            matched = False
            if cid and mcid is not None and mcid == cid:
                matched = True
            if lid and mlid is not None and mlid == lid:
                matched = True
            if matched:
                cnt += 1
        out[q.id] = (cnt > 0, cnt)
    return out


def batch_quote_list_lookups(
    session: Session, quotes: List[Quote]
) -> Tuple[
    Dict[int, Customer],
    Dict[int, Lead],
    Dict[int, int],
    Dict[int, int],
    Dict[int, Optional[datetime]],
]:
    """One round-trip per lookup type for paginated quote list (avoids N+1 in build_quote_response)."""
    customer_ids = {q.customer_id for q in quotes if q.customer_id}
    lead_ids = {q.lead_id for q in quotes if q.lead_id}
    quote_ids = [q.id for q in quotes if q.id is not None]

    customers_by_id: Dict[int, Customer] = {}
    if customer_ids:
        for customer in session.exec(select(Customer).where(Customer.id.in_(customer_ids))).all():
            if customer.id is not None:
                customers_by_id[int(customer.id)] = customer

    leads_by_id: Dict[int, Lead] = {}
    if lead_ids:
        for lead in session.exec(select(Lead).where(Lead.id.in_(lead_ids))).all():
            if lead.id is not None:
                leads_by_id[int(lead.id)] = lead

    open_counts_by_quote: Dict[int, int] = {}
    if quote_ids:
        rows = session.exec(
            select(QuoteEmail.quote_id, func.coalesce(func.sum(QuoteEmail.open_count), 0))
            .where(QuoteEmail.quote_id.in_(quote_ids))
            .group_by(QuoteEmail.quote_id)
        ).all()
        for qid, cnt in rows:
            if qid is not None:
                open_counts_by_quote[int(qid)] = int(cnt) if cnt is not None else 0

    order_id_by_quote: Dict[int, int] = {}
    accepted_quote_ids = [q.id for q in quotes if q.status == QuoteStatus.ACCEPTED and q.id is not None]
    if accepted_quote_ids:
        for row in session.exec(
            select(Order.quote_id, Order.id).where(Order.quote_id.in_(accepted_quote_ids))
        ).all():
            qid, oid = row[0], row[1]
            if qid is not None and oid is not None:
                order_id_by_quote[int(qid)] = int(oid)

    last_activity_by_customer: Dict[int, Optional[datetime]] = {}
    if customer_ids:
        rows = session.exec(
            select(Activity.customer_id, func.max(Activity.created_at))
            .where(Activity.customer_id.in_(customer_ids))
            .group_by(Activity.customer_id)
        ).all()
        for cid, ts in rows:
            if cid is not None:
                last_activity_by_customer[int(cid)] = ts

    return (
        customers_by_id,
        leads_by_id,
        open_counts_by_quote,
        order_id_by_quote,
        last_activity_by_customer,
    )


def _resolved_spec_sheet_response_fields(
    quote: Quote,
    company_settings: Optional[CompanySettings],
) -> dict:
    resolved_text = resolve_specification_sheet_text(quote, company_settings)
    company_url = resolve_specification_sheet_image_url(company_settings)
    return {
        "resolved_specification_sheet_text": resolved_text or None,
        "company_specification_sheet_url": company_url or None,
        "has_specification_sheet_content": has_specification_sheet_content(
            quote, company_settings
        ),
    }


def build_quote_list_response(
    quote: Quote,
    *,
    customer_name: Optional[str],
    lead_name: Optional[str],
    lead_type: Optional[LeadType],
    total_open_count: int,
    order_id: Optional[int],
    customer_last_interacted_at: Optional[datetime],
    lead_quotes_sent_count: Optional[int] = None,
    customer_replied_since_quote_sent: bool = False,
    inbound_count_since_quote_sent: int = 0,
    company_settings: Optional[CompanySettings] = None,
) -> QuoteResponse:
    """Lightweight quote row for GET /api/quotes (no line items, discounts, or per-row DB queries)."""
    vat_amount = quote.total_amount * VAT_RATE_DECIMAL
    total_amount_inc_vat = quote.total_amount + vat_amount
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
        specification_sheet=quote.specification_sheet,
        **_resolved_spec_sheet_response_fields(quote, company_settings),
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
        deposit_amount_inc_vat=quote.deposit_amount,
        balance_amount_inc_vat=quote.balance_amount,
        items=[],
        discounts=[],
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
        include_specification_sheet=getattr(quote, "include_specification_sheet", False),
        include_available_optional_extras=getattr(quote, "include_available_optional_extras", False),
        include_delivery_installation_contact_note=getattr(
            quote, "include_delivery_installation_contact_note", False
        ),
        fulfillment_method=getattr(quote, "fulfillment_method", QuoteFulfillmentMethod.DELIVERY),
        **delivery_location_response_fields(quote),
        total_open_count=total_open_count,
        order_id=order_id,
        customer_last_interacted_at=customer_last_interacted_at,
        archived_at=getattr(quote, "archived_at", None),
        dealer_customer_name=getattr(quote, "dealer_customer_name", None),
        dealer_customer_email=getattr(quote, "dealer_customer_email", None),
        dealer_customer_phone=getattr(quote, "dealer_customer_phone", None),
        dealer_customer_address=getattr(quote, "dealer_customer_address", None),
        dealer_customer_postcode=getattr(quote, "dealer_customer_postcode", None),
        lead_quotes_sent_count=lead_quotes_sent_count,
        customer_replied_since_quote_sent=customer_replied_since_quote_sent,
        inbound_count_since_quote_sent=inbound_count_since_quote_sent,
        displayed_optional_extra_ids=[],
        payment_link_url=getattr(quote, "payment_link_url", None),
    )


def build_quote_response(
    quote: Quote,
    quote_items: List[QuoteItem],
    session: Session,
    *,
    lead_quotes_sent_count: Optional[int] = None,
    customer_replied_since_quote_sent: bool = False,
    inbound_count_since_quote_sent: int = 0,
    draft_save_response: bool = False,
) -> QuoteResponse:
    """Build a QuoteResponse with items and discounts.

    When draft_save_response is True (PUT draft autosave), skip expensive aggregates that
    the editor does not need to refresh on every keystroke (activity scan, email open sum).
    """
    discount_statement = select(QuoteDiscount).where(QuoteDiscount.quote_id == quote.id)
    quote_discounts = session.exec(discount_statement).all()
    customer_name = None
    customer_last_interacted_at = None
    lead_name = None
    lead_type = None
    if quote.customer_id:
        customer = session.exec(select(Customer).where(Customer.id == quote.customer_id)).first()
        customer_name = customer.name if customer else None
        if not draft_save_response:
            customer_last_interacted_at = get_last_activity_date(quote.customer_id, session)
    elif quote.dealer_customer_name:
        customer_name = quote.dealer_customer_name
    if quote.lead_id:
        lead = session.exec(select(Lead).where(Lead.id == quote.lead_id)).first()
        lead_name = lead.name if lead else None
        lead_type = lead.lead_type if lead else None

    # Computed VAT (total_amount is Ex VAT @ 20%; deposit/balance stored as inc VAT)
    vat_amount = quote.total_amount * VAT_RATE_DECIMAL
    total_amount_inc_vat = quote.total_amount + vat_amount
    deposit_amount_inc_vat = quote.deposit_amount  # Stored as inc VAT
    balance_amount_inc_vat = quote.balance_amount  # Stored as inc VAT

    if draft_save_response:
        total_open_count = 0
    else:
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

    company_settings = session.exec(select(CompanySettings).limit(1)).first()

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
        specification_sheet=quote.specification_sheet,
        **_resolved_spec_sheet_response_fields(quote, company_settings),
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
        include_specification_sheet=getattr(quote, "include_specification_sheet", False),
        include_available_optional_extras=getattr(quote, "include_available_optional_extras", False),
        include_delivery_installation_contact_note=getattr(quote, "include_delivery_installation_contact_note", False),
        fulfillment_method=getattr(quote, "fulfillment_method", QuoteFulfillmentMethod.DELIVERY),
        **delivery_location_response_fields(quote),
        total_open_count=total_open_count,
        order_id=order_id,
        customer_last_interacted_at=customer_last_interacted_at,
        archived_at=getattr(quote, "archived_at", None),
        dealer_customer_name=getattr(quote, "dealer_customer_name", None),
        dealer_customer_email=getattr(quote, "dealer_customer_email", None),
        dealer_customer_phone=getattr(quote, "dealer_customer_phone", None),
        dealer_customer_address=getattr(quote, "dealer_customer_address", None),
        dealer_customer_postcode=getattr(quote, "dealer_customer_postcode", None),
        lead_quotes_sent_count=lead_quotes_sent_count,
        customer_replied_since_quote_sent=customer_replied_since_quote_sent,
        inbound_count_since_quote_sent=inbound_count_since_quote_sent,
        displayed_optional_extra_ids=get_displayed_optional_extra_ids(session, quote.id),
        payment_link_url=getattr(quote, "payment_link_url", None),
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
        specification_sheet=quote.specification_sheet,
        notes=quote.notes,
        created_by_id=created_by_id,
        fulfillment_method=getattr(quote, "fulfillment_method", QuoteFulfillmentMethod.DELIVERY),
    )
    copy_delivery_location_fields(quote, order)
    if getattr(quote, "payment_link_url", None) and not order.payment_link_url:
        order.payment_link_url = quote.payment_link_url
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
    # Inherit any files attached to the quote so they appear on the order too.
    for cf in session.exec(
        select(CustomerFile).where(CustomerFile.quote_id == quote.id)
    ).all():
        cf.order_id = order.id
        session.add(cf)
    record_order_audit_event(
        session,
        event_type=CustomerHistoryEventType.ORDER_CREATED.value,
        title="Order Created",
        description=f"Order {order.order_number} was created from accepted quote {quote.quote_number}",
        order=order,
        metadata={"quote_number": quote.quote_number},
        created_by_id=created_by_id,
        created_at=order.created_at,
    )
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

        fulfillment_method = getattr(
            quote_data, "fulfillment_method", QuoteFulfillmentMethod.DELIVERY
        )
        _assert_collection_fulfillment_items_valid(fulfillment_method, quote_data.items)
        assert_alternate_delivery_valid(
            quote_data.use_alternate_delivery_address,
            fulfillment_method,
            quote_data.delivery_address_line1,
            quote_data.delivery_city,
            quote_data.delivery_postcode,
        )
        
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
                installation_hours=_installation_hours_for_quote_item_create(item_data),
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
            specification_sheet=getattr(quote_data, "specification_sheet", None),
            notes=quote_data.notes,
            created_by_id=current_user.id,
            temperature=quote_data.temperature,
            include_spec_sheets=getattr(quote_data, "include_spec_sheets", True),
            include_specification_sheet=getattr(quote_data, "include_specification_sheet", False),
            include_available_optional_extras=getattr(quote_data, "include_available_optional_extras", False),
            include_delivery_installation_contact_note=getattr(quote_data, "include_delivery_installation_contact_note", False),
            fulfillment_method=fulfillment_method,
            use_alternate_delivery_address=quote_data.use_alternate_delivery_address,
            delivery_address_line1=quote_data.delivery_address_line1 if quote_data.use_alternate_delivery_address else None,
            delivery_address_line2=quote_data.delivery_address_line2 if quote_data.use_alternate_delivery_address else None,
            delivery_city=quote_data.delivery_city if quote_data.use_alternate_delivery_address else None,
            delivery_county=quote_data.delivery_county if quote_data.use_alternate_delivery_address else None,
            delivery_postcode=quote_data.delivery_postcode if quote_data.use_alternate_delivery_address else None,
            delivery_country=quote_data.delivery_country if quote_data.use_alternate_delivery_address else "United Kingdom",
            delivery_location_notes=quote_data.delivery_location_notes if quote_data.use_alternate_delivery_address else None,
        )
        session.add(quote)
        session.commit()
        session.refresh(quote)

        sync_quote_displayed_optional_extras(
            session, quote.id, quote_data.displayed_optional_extra_ids
        )
        if quote_data.displayed_optional_extra_ids is not None:
            session.commit()
        
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
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        error_detail = str(e)
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Error creating quote: {error_detail}")


@router.get("", response_model=QuoteListResponse)
async def get_all_quotes(
    status: Optional[QuoteStatus] = Query(None),
    lifecycle: Optional[Literal["live", "closed"]] = Query(None),
    search: Optional[str] = Query(None),
    temperature: Optional[QuoteTemperature] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(LIST_PAGE_SIZE_DEFAULT, ge=1, le=LIST_PAGE_SIZE_MAX),
    include_archived: bool = Query(False, alias="includeArchived"),
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """Paginated quotes.

    Default: excludes REJECTED and EXPIRED (pipeline list).
    Pass status= for a single status (special case: VIEWED includes SENT rows with viewed_at set); lifecycle is ignored.
    Pass lifecycle=live for DRAFT/SENT/VIEWED only, or lifecycle=closed for ACCEPTED/REJECTED/EXPIRED only.
    """
    try:
        effective_include_archived = include_archived or (bool(search and search.strip()))
        conditions = []

        if status is not None:
            if status == QuoteStatus.VIEWED:
                conditions.append(
                    or_(
                        Quote.status == QuoteStatus.VIEWED,
                        and_(
                            Quote.status == QuoteStatus.SENT,
                            Quote.viewed_at.isnot(None),
                        ),
                    )
                )
            else:
                conditions.append(Quote.status == status)
        elif lifecycle == "live":
            conditions.append(Quote.status.in_(QUOTE_LIVE_STATUSES))
        elif lifecycle == "closed":
            conditions.append(Quote.status.in_(QUOTE_CLOSED_STATUSES))
        else:
            conditions.append(Quote.status.notin_(QUOTE_LIST_EXCLUDED_STATUSES))

        if not effective_include_archived:
            conditions.append(Quote.archived_at.is_(None))

        if temperature is not None:
            conditions.append(Quote.temperature == temperature)

        if search and search.strip():
            term = f"%{search.strip()}%"
            conditions.append(
                or_(
                    Quote.quote_number.ilike(term),
                    Customer.name.ilike(term),
                    func.cast(Lead.lead_type, SAString).ilike(term),
                )
            )

        where_clause = and_(*conditions) if conditions else true()

        count_stmt = (
            select(func.count(Quote.id))
            .select_from(Quote)
            .outerjoin(Customer, Quote.customer_id == Customer.id)
            .outerjoin(Lead, Quote.lead_id == Lead.id)
            .where(where_clause)
        )
        _total_row = session.exec(count_stmt).one()
        total = int(_total_row[0]) if isinstance(_total_row, (tuple, list)) else int(_total_row)

        statement = (
            select(Quote)
            .outerjoin(Customer, Quote.customer_id == Customer.id)
            .outerjoin(Lead, Quote.lead_id == Lead.id)
            .where(where_clause)
            .order_by(Quote.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        quotes = session.exec(statement).all()

        quote_list = list(quotes)
        lead_ids_page = list({q.lead_id for q in quote_list if q.lead_id})
        lead_sent_map = batch_lead_quotes_sent_counts(session, lead_ids_page)
        reply_map = batch_reply_metrics_since_sent(session, quote_list)
        (
            customers_by_id,
            leads_by_id,
            open_counts_by_quote,
            order_id_by_quote,
            last_activity_by_customer,
        ) = batch_quote_list_lookups(session, quote_list)

        company_settings = session.exec(select(CompanySettings).limit(1)).first()

        result = []
        for quote in quote_list:
            if quote.id is None:
                continue
            qid = int(quote.id)
            customer_name = None
            customer_last_interacted_at = None
            if quote.customer_id:
                cid = int(quote.customer_id)
                customer = customers_by_id.get(cid)
                customer_name = customer.name if customer else None
                customer_last_interacted_at = last_activity_by_customer.get(cid)
            elif quote.dealer_customer_name:
                customer_name = quote.dealer_customer_name
            lead_name = None
            lead_type = None
            if quote.lead_id:
                lead = leads_by_id.get(int(quote.lead_id))
                if lead:
                    lead_name = lead.name
                    lead_type = lead.lead_type
            replied, inbound_n = reply_map.get(qid, (False, 0))
            lead_n = lead_sent_map.get(int(quote.lead_id), 0) if quote.lead_id else None
            result.append(
                build_quote_list_response(
                    quote,
                    customer_name=customer_name,
                    lead_name=lead_name,
                    lead_type=lead_type,
                    total_open_count=open_counts_by_quote.get(qid, 0),
                    order_id=order_id_by_quote.get(qid),
                    customer_last_interacted_at=customer_last_interacted_at,
                    lead_quotes_sent_count=lead_n,
                    customer_replied_since_quote_sent=replied,
                    inbound_count_since_quote_sent=inbound_n,
                    company_settings=company_settings,
                )
            )

        return QuoteListResponse(items=result, total=total, page=page, page_size=page_size)
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
    if old_status != QuoteStatus.ACCEPTED:
        dismiss_open_reminders_for_quote(session, quote.id)
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
    now = datetime.utcnow()
    for d in discount_rows:
        if d.template_id is not None and d.template_id not in seen:
            template = session.get(DiscountTemplate, d.template_id)
            # Duplication should succeed even if source template has since expired.
            if template and template.expires_at is not None and template.expires_at < now:
                continue
            seen.add(d.template_id)
            template_ids.append(d.template_id)

    displayed_extra_ids = get_displayed_optional_extra_ids(session, source.id)

    return QuoteDraftUpdate(
        valid_until=source.valid_until,
        terms_and_conditions=source.terms_and_conditions,
        specification_sheet=source.specification_sheet,
        notes=source.notes,
        deposit_amount=source.deposit_amount,
        items=item_rows,
        discount_template_ids=template_ids if template_ids else None,
        temperature=source.temperature,
        include_spec_sheets=source.include_spec_sheets,
        include_specification_sheet=source.include_specification_sheet,
        include_available_optional_extras=source.include_available_optional_extras,
        include_delivery_installation_contact_note=source.include_delivery_installation_contact_note,
        fulfillment_method=getattr(source, "fulfillment_method", QuoteFulfillmentMethod.DELIVERY),
        use_alternate_delivery_address=getattr(source, "use_alternate_delivery_address", False),
        delivery_address_line1=getattr(source, "delivery_address_line1", None),
        delivery_address_line2=getattr(source, "delivery_address_line2", None),
        delivery_city=getattr(source, "delivery_city", None),
        delivery_county=getattr(source, "delivery_county", None),
        delivery_postcode=getattr(source, "delivery_postcode", None),
        delivery_country=getattr(source, "delivery_country", None),
        delivery_location_notes=getattr(source, "delivery_location_notes", None),
        displayed_optional_extra_ids=displayed_extra_ids if displayed_extra_ids else None,
    )


def _serialize_quote_configuration(record: QuoteConfiguration) -> QuoteConfigurationResponse:
    return QuoteConfigurationResponse(
        quote_id=record.quote_id,
        version=record.version,
        configuration=QuoteConfigurationPayload.model_validate(record.configuration_json or {}),
        created_by_id=record.created_by_id,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


def _generated_line_to_quote_item(line: ConfiguratorGeneratedLine) -> QuoteItemCreate:
    return QuoteItemCreate(
        product_id=line.product_id,
        description=line.description,
        quantity=line.quantity,
        unit_price=line.unit_price,
        is_custom=line.is_custom,
        sort_order=line.sort_order,
        parent_index=line.parent_index,
        include_in_building_discount=line.include_in_building_discount,
        line_type=line.line_type,
    )


def _get_quote_configuration_record(session: Session, quote_id: int) -> QuoteConfiguration:
    record = session.exec(
        select(QuoteConfiguration).where(QuoteConfiguration.quote_id == quote_id)
    ).first()
    if not record:
        raise HTTPException(status_code=404, detail="Quote configuration not found")
    return record


@router.get("/{quote_id}/configuration", response_model=QuoteConfigurationResponse)
async def get_quote_configuration(
    quote_id: int,
    session: Session = Depends(get_session),
    current_user: User = Depends(require_configurator_access),
):
    del current_user
    quote = session.exec(select(Quote).where(Quote.id == quote_id)).first()
    if not quote:
        raise HTTPException(status_code=404, detail="Quote not found")
    return _serialize_quote_configuration(_get_quote_configuration_record(session, quote_id))


@router.put("/{quote_id}/configuration", response_model=QuoteConfigurationResponse)
async def save_quote_configuration(
    quote_id: int,
    payload: QuoteConfigurationPayload,
    session: Session = Depends(get_session),
    current_user: User = Depends(require_configurator_access),
):
    quote = session.exec(select(Quote).where(Quote.id == quote_id)).first()
    if not quote:
        raise HTTPException(status_code=404, detail="Quote not found")
    if quote.status != QuoteStatus.DRAFT:
        raise HTTPException(status_code=400, detail="Only draft quotes can store configurator layouts")

    record = session.exec(
        select(QuoteConfiguration).where(QuoteConfiguration.quote_id == quote_id)
    ).first()
    if record:
        record.version += 1
        record.configuration_json = payload.model_dump(mode="json")
        record.updated_at = datetime.utcnow()
        session.add(record)
    else:
        record = QuoteConfiguration(
            quote_id=quote_id,
            version=1,
            configuration_json=payload.model_dump(mode="json"),
            created_by_id=current_user.id,
        )
        session.add(record)
    session.commit()
    session.refresh(record)
    return _serialize_quote_configuration(record)


@router.post("/{quote_id}/configuration/apply", response_model=QuoteResponse)
async def apply_quote_configuration(
    quote_id: int,
    session: Session = Depends(get_session),
    current_user: User = Depends(require_configurator_access),
):
    quote = session.exec(select(Quote).where(Quote.id == quote_id)).first()
    if not quote:
        raise HTTPException(status_code=404, detail="Quote not found")
    if quote.status != QuoteStatus.DRAFT:
        raise HTTPException(status_code=400, detail="Only draft quotes can apply configurator layouts")

    record = _get_quote_configuration_record(session, quote_id)
    payload = QuoteConfigurationPayload.model_validate(record.configuration_json or {})
    preview = build_configurator_preview(
        payload,
        session,
        customer_postcode=resolve_quote_customer_postcode(quote, session),
    )
    if not preview.valid:
        raise HTTPException(
            status_code=422,
            detail={
                "message": "Configurator layout has validation errors",
                "issues": [issue.model_dump(mode="json") for issue in preview.issues],
            },
        )
    if not preview.items:
        raise HTTPException(status_code=422, detail="Configurator layout generated no quote lines")

    try:
        draft_payload = _build_duplicate_draft_payload_from_source(quote, session)
    except HTTPException as exc:
        if exc.status_code != 400:
            raise
        draft_payload = QuoteDraftUpdate(
            valid_until=quote.valid_until,
            terms_and_conditions=quote.terms_and_conditions,
            specification_sheet=quote.specification_sheet,
            notes=quote.notes,
            deposit_amount=quote.deposit_amount,
            items=[],
            temperature=quote.temperature,
            include_spec_sheets=quote.include_spec_sheets,
            include_specification_sheet=quote.include_specification_sheet,
            include_available_optional_extras=quote.include_available_optional_extras,
            include_delivery_installation_contact_note=quote.include_delivery_installation_contact_note,
            fulfillment_method=getattr(quote, "fulfillment_method", QuoteFulfillmentMethod.DELIVERY),
        )
    draft_payload.items = [_generated_line_to_quote_item(line) for line in preview.items]
    draft_payload.include_spec_sheets = False
    draft_payload.include_specification_sheet = False
    draft_payload.include_available_optional_extras = False
    if payload.delivery_estimate_inclusion == ConfiguratorDeliveryEstimateInclusion.COLLECTION:
        draft_payload.fulfillment_method = QuoteFulfillmentMethod.COLLECTION
    else:
        draft_payload.fulfillment_method = QuoteFulfillmentMethod.DELIVERY
    return _update_draft_quote_impl(quote_id, draft_payload, session, current_user)


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
        include_specification_sheet=source.include_specification_sheet,
        include_available_optional_extras=source.include_available_optional_extras,
        include_delivery_installation_contact_note=source.include_delivery_installation_contact_note,
        fulfillment_method=getattr(source, "fulfillment_method", QuoteFulfillmentMethod.DELIVERY),
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


@router.post("/{quote_id}/ensure-order", response_model=QuoteResponse)
async def ensure_quote_order(
    quote_id: int,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """Recreate a missing order for an accepted quote."""
    statement = select(Quote).where(Quote.id == quote_id)
    quote = session.exec(statement).first()

    if not quote:
        raise HTTPException(status_code=404, detail="Quote not found")

    is_accepted = (
        quote.status == QuoteStatus.ACCEPTED
        or quote.opportunity_stage == OpportunityStage.WON
        or quote.accepted_at is not None
    )
    if not is_accepted:
        raise HTTPException(status_code=400, detail="Only accepted quotes can recreate a missing order")

    create_order_from_quote(quote, session, current_user.id)
    session.commit()
    session.refresh(quote)

    quote_items = session.exec(
        select(QuoteItem).where(QuoteItem.quote_id == quote.id).order_by(QuoteItem.sort_order)
    ).all()
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

    if quote_data.fulfillment_method is not None:
        quote.fulfillment_method = quote_data.fulfillment_method
    effective_fulfillment = getattr(quote, "fulfillment_method", QuoteFulfillmentMethod.DELIVERY)
    _assert_collection_fulfillment_items_valid(effective_fulfillment, quote_data.items)
    sync_delivery_location_from_payload(quote, quote_data, partial=True)
    assert_alternate_delivery_valid(
        quote.use_alternate_delivery_address,
        effective_fulfillment,
        quote.delivery_address_line1,
        quote.delivery_city,
        quote.delivery_postcode,
    )
    
    # Delete existing items and discounts for this quote (single transaction; flush for FK order).
    # 1. Delete discounts first (QuoteDiscount.quote_item_id references QuoteItem)
    # 2. Null parent_quote_item_id then bulk-delete items (avoids per-row ORM deletes)
    session.exec(delete(QuoteDiscount).where(QuoteDiscount.quote_id == quote_id))
    session.flush()
    session.exec(
        update(QuoteItem)
        .where(QuoteItem.quote_id == quote_id)
        .values(parent_quote_item_id=None)
    )
    session.flush()
    session.exec(delete(QuoteItem).where(QuoteItem.quote_id == quote_id))
    session.flush()

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
            installation_hours=_installation_hours_for_quote_item_create(item_data),
        )
        items.append(item)
    
    for item in items:
        session.add(item)
    session.flush()

    # Resolve new item IDs, then set parent_quote_item_id
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
        session.flush()
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
    if quote_data.specification_sheet is not None:
        quote.specification_sheet = quote_data.specification_sheet
    if quote_data.notes is not None:
        quote.notes = quote_data.notes
    if quote_data.temperature is not None:
        quote.temperature = quote_data.temperature
    if quote_data.include_spec_sheets is not None:
        quote.include_spec_sheets = quote_data.include_spec_sheets
    if quote_data.include_specification_sheet is not None:
        quote.include_specification_sheet = quote_data.include_specification_sheet
    if quote_data.include_available_optional_extras is not None:
        quote.include_available_optional_extras = quote_data.include_available_optional_extras
    if quote_data.include_delivery_installation_contact_note is not None:
        quote.include_delivery_installation_contact_note = quote_data.include_delivery_installation_contact_note
    if quote_data.fulfillment_method is not None:
        quote.fulfillment_method = quote_data.fulfillment_method

    sync_quote_displayed_optional_extras(
        session, quote_id, quote_data.displayed_optional_extra_ids
    )

    # Apply template discounts selected in the editor.
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

    # Reapply approved custom discount requests for this quote.
    # These discounts are persisted independently of discount_template_ids and
    # would otherwise be lost when draft save rebuilds QuoteDiscount rows.
    approved_requests = list(
        session.exec(
            select(DiscountRequest).where(
                DiscountRequest.quote_id == quote_id,
                DiscountRequest.status == DiscountRequestStatus.APPROVED,
            )
        ).all()
    )
    for dr in approved_requests:
        apply_custom_discount_to_quote(
            quote,
            dr.discount_type,
            dr.discount_value,
            dr.scope,
            f"Custom discount (Request #{dr.id})",
            quote_items,
            session,
            current_user,
        )
        for item in quote_items:
            session.add(item)

    session.flush()
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
    quote_items = list(session.exec(statement).all())
    return build_quote_response(quote, quote_items, session, draft_save_response=True)


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
        include_specification_sheet=getattr(quote, "include_specification_sheet", False),
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
        include_specification_sheet=bool(req.include_specification_sheet),
    )
    _transition_customer_leads_to_quoted_after_send(
        quote.customer_id, session, current_user.id
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
        include_specification_sheet=bool(req.include_specification_sheet),
    )

    to_phone = resolve_sms_to_phone(
        session,
        customer,
        explicit_to=(req.to_phone or "").strip() or None,
        lead_id=quote.lead_id,
    )
    if not to_phone:
        raise HTTPException(
            status_code=400,
            detail="No phone number; set to_phone in the request, add a phone on the customer, or ensure the quote’s lead has a phone.",
        )

    if (req.body or "").strip():
        sms_body = (req.body or "").strip()
    else:
        has_order = session.exec(select(Order).where(Order.quote_id == quote.id)).first() is not None
        label = "order" if has_order else "quote"
        sms_body = f"Here is your {label} link to review online: {view_url}"

    success, sid, error = send_sms(to_phone, sms_body)
    if not success:
        if is_unsubscribed_recipient_error(error):
            customer.automated_reminder_outreach_opt_out = True
            session.add(customer)
            session.commit()
            raise HTTPException(
                status_code=400,
                detail=(
                    "Recipient has unsubscribed from SMS (Twilio 21610). "
                    "Customer has been opted out from automated reminder outreach."
                ),
            )
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
        notes=f"Quote {quote.quote_number} link sent by SMS to {to_phone}\n{sms_body}",
        created_by_id=current_user.id,
    )
    session.add(activity)
    session.commit()

    _transition_customer_leads_to_quoted_after_send(
        quote.customer_id, session, current_user.id
    )

    return QuoteSendSmsResponse(
        view_url=view_url,
        quote_email_id=quote_email.id,
        message="SMS sent successfully",
    )


@router.post("/{quote_id}/send-payment-link", response_model=QuoteSendPaymentLinkResponse)
async def send_quote_payment_link(
    quote_id: int,
    data: Optional[QuoteSendPaymentLinkRequest] = Body(default=None),
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """Send an external payment URL to the customer by email or SMS."""
    req = data or QuoteSendPaymentLinkRequest(channel="sms")
    channel = (req.channel or "").strip().lower()
    if channel not in ("email", "sms"):
        raise HTTPException(status_code=400, detail="channel must be 'email' or 'sms'")

    quote = session.exec(select(Quote).where(Quote.id == quote_id)).first()
    if not quote:
        raise HTTPException(status_code=404, detail="Quote not found")
    if not quote.customer_id:
        raise HTTPException(status_code=400, detail="Quote must be associated with a customer")

    customer = session.exec(select(Customer).where(Customer.id == quote.customer_id)).first()
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")

    raw_url = (req.payment_url or "").strip() or (getattr(quote, "payment_link_url", None) or "").strip()
    if not raw_url:
        raise HTTPException(status_code=400, detail="Payment URL is required")
    try:
        payment_url = validate_payment_url(raw_url)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    if req.save_link_on_quote:
        quote.payment_link_url = payment_url
        session.add(quote)

    company_settings = session.exec(select(CompanySettings).limit(1)).first()
    template_ctx = quote_payment_link_template_context(quote, payment_url)
    custom_body = (req.body or "").strip()

    if channel == "sms":
        to_phone = resolve_sms_to_phone(
            session,
            customer,
            explicit_to=(req.to_phone or "").strip() or None,
            lead_id=quote.lead_id,
        )
        if not to_phone:
            raise HTTPException(
                status_code=400,
                detail="No phone number; set to_phone, add a phone on the customer, or ensure the quote's lead has a phone.",
            )

        if custom_body:
            sms_body = custom_body
        elif req.template_id:
            template = session.get(SmsTemplate, req.template_id)
            if not template:
                raise HTTPException(status_code=404, detail="SMS template not found")
            sms_body = render_sms_template(
                template,
                customer,
                user=current_user,
                company_settings=company_settings,
                extra_context=template_ctx,
            )
        else:
            sms_body = default_quote_payment_sms_body(quote, payment_url)

        success, sid, error = send_sms(to_phone, sms_body)
        if not success:
            if is_unsubscribed_recipient_error(error):
                customer.automated_reminder_outreach_opt_out = True
                session.add(customer)
                session.commit()
                raise HTTPException(
                    status_code=400,
                    detail=(
                        "Recipient has unsubscribed from SMS (Twilio 21610). "
                        "Customer has been opted out from automated reminder outreach."
                    ),
                )
            raise HTTPException(status_code=500, detail=error or "Failed to send SMS")

        from_phone = (os.getenv("TWILIO_PHONE_NUMBER") or "").strip()
        now = datetime.utcnow()
        session.add(
            SmsMessage(
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
        )
        session.add(
            Activity(
                customer_id=customer.id,
                activity_type=ActivityType.SMS_SENT,
                notes=f"Payment link for quote {quote.quote_number} sent by SMS to {to_phone}\n{sms_body}",
                created_by_id=current_user.id,
            )
        )
    else:
        to_email = (req.to_email or "").strip() or (customer.email or "").strip()
        if not to_email:
            raise HTTPException(status_code=400, detail="Recipient email is required")

        if not is_email_configured(current_user.id):
            raise HTTPException(status_code=400, detail="Email not configured for your user account")

        subject = (req.subject or "").strip()
        body_html: Optional[str] = None
        body_text: Optional[str] = None

        if custom_body:
            if custom_body.lstrip().startswith("<"):
                body_html = custom_body
            else:
                body_html = "<p>" + escape(custom_body).replace("\n", "<br>\n") + "</p>"

        if req.template_id and not custom_body:
            template = session.get(EmailTemplate, req.template_id)
            if not template:
                raise HTTPException(status_code=404, detail="Email template not found")
            rendered_subject, rendered_body_html = render_email_template(
                template, customer, custom_variables=template_ctx
            )
            if not subject:
                subject = rendered_subject
            if not body_html:
                body_html = rendered_body_html

        if not subject:
            subject = default_quote_payment_email_subject(quote)
        if not body_html:
            body_html = default_quote_payment_email_html(quote, payment_url)
        body_text = _html_to_plain(body_html) if body_html else None

        success, message_id, error, sent_html, sent_text = send_email(
            to_email=to_email,
            subject=subject,
            body_html=body_html,
            body_text=body_text,
            user_id=current_user.id,
            customer_number=customer.customer_number,
        )
        if not success:
            raise HTTPException(status_code=500, detail=error or "Failed to send email")

        final_html = sent_html or body_html
        final_text = sent_text if sent_text is not None else body_text
        session.add(
            Email(
                customer_id=customer.id,
                message_id=message_id,
                direction=EmailDirection.SENT,
                from_email=current_user.email,
                to_email=to_email,
                subject=subject,
                body_html=final_html,
                body_text=final_text,
                sent_at=datetime.utcnow(),
                created_by_id=current_user.id,
                thread_id=str(uuid.uuid4()),
            )
        )
        session.add(
            Activity(
                customer_id=customer.id,
                activity_type=ActivityType.EMAIL_SENT,
                notes=build_activity_email_notes(
                    f"Payment link for quote {quote.quote_number} sent to {to_email}",
                    subject,
                    final_text,
                    final_html,
                ),
                created_by_id=current_user.id,
            )
        )

    record_order_audit_event(
        session,
        event_type=CustomerHistoryEventType.QUOTE_PAYMENT_LINK_SENT.value,
        title="Payment Link Sent",
        description=f"Payment link for quote {quote.quote_number} sent by {channel}",
        customer_id=customer.id,
        quote_id=quote.id,
        metadata={
            "channel": channel,
            "quote_number": quote.quote_number,
            "payment_url": payment_url,
        },
        created_by_id=current_user.id,
    )
    session.commit()

    return QuoteSendPaymentLinkResponse(
        message="Payment link sent successfully",
        channel=channel,
    )


@router.post("/{quote_id}/send-email", response_model=QuoteEmailSendResponse)
async def send_quote_email_endpoint(
    quote_id: int,
    email_data: str = Form(..., description="JSON string matching QuoteEmailSendRequest"),
    attachments: List[UploadFile] = File(default=[]),
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """Send a quote email with a link to view the quote online. Optional file attachments (same limits as compose email: 10MB each, 25MB total)."""
    try:
        try:
            req = QuoteEmailSendRequest.model_validate(json.loads(email_data))
        except json.JSONDecodeError as e:
            raise HTTPException(status_code=400, detail=f"Invalid email_data JSON: {e}")
        except ValidationError as e:
            for err in e.errors():
                loc = err.get("loc") or ()
                if "template_id" in loc:
                    raise HTTPException(
                        status_code=400,
                        detail="Choose an email template before sending.",
                    )
            errs = e.errors()
            if errs:
                err0 = errs[0]
                loc = err0.get("loc") or ()
                field = str(loc[-1]) if loc else "request"
                msg = err0.get("msg", "Invalid value")
                raise HTTPException(status_code=400, detail=f"{field}: {msg}")
            raise HTTPException(status_code=400, detail="Invalid email data.")

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
            raise HTTPException(
                status_code=400,
                detail=(
                    "That email template no longer exists or was removed. "
                    "Select another template in Quote Templates settings."
                ),
            )

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
            try:
                content = await load_sales_document_bytes(sales_doc)
            except HTTPException as exc:
                raise HTTPException(
                    status_code=400,
                    detail=(
                        f"Quote template attachment is unavailable: {sales_doc.name} "
                        f"({sales_doc.filename}). {exc.detail}. Re-upload the document "
                        f"in Sales Documents or remove it from the template."
                    ),
                )
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
            include_specification_sheet=getattr(req, "include_specification_sheet", False) or False,
        )
        session.add(quote_email)
        
        # Update quote: status to SENT and sent_at
        quote.include_specification_sheet = bool(req.include_specification_sheet)
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
            notes=build_activity_email_notes(
                f"Quote {quote.quote_number} sent to {req.to_email}",
                final_subject,
                email_body_text,
                final_body_html,
            ),
            created_by_id=current_user.id
        )
        session.add(activity)
        session.commit()

        _transition_customer_leads_to_quoted_after_send(
            quote.customer_id, session, current_user.id
        )
        
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

    quote.archived_at = None

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
        dismiss_open_reminders_for_quote(session, quote.id)
    
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
    include_specification_sheet: bool | None = Query(
        default=None,
        description="Override quote setting for standard specification sheet. None uses quote.include_specification_sheet.",
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
        show_optional_extras = (
            include_optional_extras is True
            or (
                include_optional_extras is None
                and should_show_available_optional_extras_on_quote(quote, quote.id, session)
            )
        )
        available_extras = (
            get_available_optional_extras_for_quote(
                list(quote_items),
                session,
                quote_id=quote.id,
                include_product_linked=getattr(quote, "include_available_optional_extras", False)
                or include_optional_extras is True,
            )
            if show_optional_extras
            else None
        )
        use_specification_sheet = should_include_specification_sheet_for_staff_preview(
            quote,
            company_settings,
            include_specification_sheet,
        )
        spec_sheet_text = (
            resolve_specification_sheet_text(quote, company_settings)
            if use_specification_sheet
            else ""
        )
        spec_sheet_image_url = (
            resolve_specification_sheet_image_url(company_settings)
            if use_specification_sheet
            else ""
        )
        include_spec_sheet = use_specification_sheet and has_specification_sheet_content(
            quote, company_settings
        )
        pdf_buffer = generate_quote_pdf(
            quote, customer, quote_items, company_settings, session,
            include_spec_sheets=use_spec_sheets,
            available_optional_extras=available_extras,
            include_specification_sheet=include_spec_sheet,
            specification_sheet_text=spec_sheet_text or None,
            specification_sheet_image_url=spec_sheet_image_url or None,
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
