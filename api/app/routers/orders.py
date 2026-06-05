import os
import re
import secrets
import uuid
from html import escape
from datetime import date, datetime
from fastapi import APIRouter, Body, Depends, HTTPException
from fastapi.responses import Response
from sqlmodel import Session, select
from typing import List, Optional
import httpx
from app.database import get_session
from app.models import (
    Order,
    OrderItem,
    OrderAuditEvent,
    Customer,
    CompanySettings,
    AccessSheetRequest,
    Product,
    Quote,
    Lead,
    LeadSource,
    QuoteFulfillmentMethod,
    Activity,
    ActivityType,
    SmsMessage,
    SmsDirection,
    Email,
    EmailDirection,
    EmailTemplate,
    SmsTemplate,
)
from app.auth import get_current_user
from app.delivery_location import (
    assert_alternate_delivery_valid,
    build_delivery_address,
    delivery_location_response_fields,
    has_full_delivery_address,
    sync_delivery_location_from_payload,
)
from app.schemas import (
    OrderResponse,
    OrderItemResponse,
    OrderUpdate,
    AccessSheetSendResponse,
    AccessSheetResponse,
    CustomerHistoryEventType,
    OrderSendPaymentLinkRequest,
    OrderSendPaymentLinkResponse,
    OrderSendReviewRequestResponse,
)
from app.review_request_service import (
    on_installation_completed,
    on_installation_uncompleted,
    send_review_request_to_customer,
    create_review_reminder,
)
from app.models import Reminder, ReminderType
from app.models import User
from app.invoice_pdf_service import generate_deposit_paid_invoice_pdf, generate_paid_in_full_invoice_pdf
from app.make_xero_service import push_order_invoice_to_make
from app.order_delete import delete_order_cascade
from app.order_audit import record_order_audit_event
from app.payment_link_service import (
    validate_payment_url,
    payment_link_template_context,
    default_payment_sms_body,
    default_payment_email_subject,
    default_payment_email_html,
)
from app.email_service import send_email, is_email_configured, build_activity_email_notes, _html_to_plain
from app.email_template_service import render_email_template
from app.sms_template_service import render_sms_template
from app.sms_service import (
    send_sms,
    resolve_sms_to_phone,
    normalize_phone,
    is_unsubscribed_recipient_error,
)

router = APIRouter(prefix="/api/orders", tags=["orders"])

_PAYMENT_FIELDS = ("deposit_paid", "balance_paid", "paid_in_full")
_INSTALLATION_FIELDS = ("installation_booked", "installation_completed")
_ORDER_FIELD_LABELS = {
    "deposit_paid": "Deposit paid",
    "balance_paid": "Balance paid",
    "paid_in_full": "Paid in full",
    "installation_booked": "Installation booked",
    "installation_completed": "Installation completed",
}


def _collect_order_flag_changes(order: Order, old_values: dict[str, bool], fields: tuple[str, ...]) -> list[dict]:
    changes: list[dict] = []
    for field in fields:
        old_value = bool(old_values.get(field, False))
        new_value = bool(getattr(order, field) or False)
        if old_value == new_value:
            continue
        changes.append(
            {
                "field": field,
                "label": _ORDER_FIELD_LABELS[field],
                "old": old_value,
                "new": new_value,
            }
        )
    return changes


def _describe_order_flag_changes(changes: list[dict]) -> str:
    parts = []
    for change in changes:
        parts.append(f"{change['label']} {'marked' if change['new'] else 'cleared'}")
    return "; ".join(parts)


def generate_invoice_number(session: Session) -> str:
    """Generate a unique invoice number like INV-2025-001."""
    year = date.today().year
    statement = select(Order).where(Order.invoice_number.like(f"INV-{year}-%"))
    orders = session.exec(statement).all()
    if not orders:
        return f"INV-{year}-001"
    numbers = []
    for order in orders:
        if not order.invoice_number:
            continue
        try:
            num = int(order.invoice_number.split("-")[-1])
            numbers.append(num)
        except (ValueError, IndexError):
            continue
    if not numbers:
        return f"INV-{year}-001"
    next_num = max(numbers) + 1
    return f"INV-{year}-{next_num:03d}"


def _build_prize_draw_entry_response(order: Order, session: Session):
    from app.models import CompanySettings
    from app.review_prize_draw_service import (
        build_prize_draw_entry_response,
        ensure_prize_draw_entry,
        get_entry_for_order,
        is_prize_draw_enabled,
    )
    from app.schemas import PrizeDrawEntryResponse

    settings = session.exec(select(CompanySettings).limit(1)).first()
    if order.installation_completed and is_prize_draw_enabled(settings):
        ensure_prize_draw_entry(order, session)
        session.flush()
    entry = get_entry_for_order(session, order.id)
    data = build_prize_draw_entry_response(entry)
    if not data:
        return None
    return PrizeDrawEntryResponse(**data)


def _build_access_sheet_response(order_id: int, session: Session) -> AccessSheetResponse | None:
    """Build AccessSheetResponse from latest AccessSheetRequest for order."""
    req = session.exec(
        select(AccessSheetRequest)
        .where(AccessSheetRequest.order_id == order_id)
        .order_by(AccessSheetRequest.created_at.desc())
        .limit(1)
    ).first()
    if not req:
        return None

    frontend = (os.getenv("FRONTEND_URL") or os.getenv("PUBLIC_FRONTEND_URL") or "").strip()
    if not frontend or not (frontend.startswith("http://") or frontend.startswith("https://")):
        frontend = "https://leadlock-frontend-production.up.railway.app"
    base = frontend.rstrip("/")
    access_sheet_url = f"{base}/access-sheet/{req.access_token}"

    return AccessSheetResponse(
        access_sheet_url=access_sheet_url,
        completed=req.completed_at is not None,
        completed_at=req.completed_at,
        answers=req.answers,
    )


def _get_latest_production_send(order_id: int, session: Session) -> tuple[datetime | None, int | None, str | None]:
    """Latest ORDER_SENT_TO_PRODUCTION audit event for this order."""
    row = session.exec(
        select(OrderAuditEvent, User)
        .outerjoin(User, OrderAuditEvent.created_by_id == User.id)
        .where(
            OrderAuditEvent.order_id == order_id,
            OrderAuditEvent.event_type == CustomerHistoryEventType.ORDER_SENT_TO_PRODUCTION.value,
        )
        .order_by(OrderAuditEvent.created_at.desc())
        .limit(1)
    ).first()
    if not row:
        return None, None, None
    audit_event, user = row
    return audit_event.created_at, audit_event.created_by_id, (user.full_name if user else None)


def build_order_response(order: Order, order_items: List[OrderItem], session: Session) -> OrderResponse:
    """Build OrderResponse with items and optional customer_name."""
    customer_name = None
    customer_source_system = None
    lead_type = None
    if order.customer_id:
        customer = session.exec(select(Customer).where(Customer.id == order.customer_id)).first()
        if customer:
            customer_name = customer.name
            customer_source_system = customer.source_system

    quote = session.exec(select(Quote).where(Quote.id == order.quote_id)).first()
    lead_source = None
    if quote and quote.lead_id:
        lead = session.exec(select(Lead).where(Lead.id == quote.lead_id)).first()
        lead_source = lead.lead_source if lead else None
        lead_type = lead.lead_type if lead else None
    is_ninox_origin = lead_source == LeadSource.NINOX or customer_source_system == "Ninox"

    access_sheet = _build_access_sheet_response(order.id, session)
    prize_draw_entry = _build_prize_draw_entry_response(order, session)
    sent_at, sent_by_id, sent_by_name = _get_latest_production_send(order.id, session)

    return OrderResponse(
        id=order.id,
        quote_id=order.quote_id,
        customer_id=order.customer_id,
        customer_name=customer_name,
        lead_type=lead_type,
        order_number=order.order_number,
        subtotal=order.subtotal,
        discount_total=order.discount_total,
        total_amount=order.total_amount,
        deposit_amount=order.deposit_amount,
        balance_amount=order.balance_amount,
        currency=order.currency,
        terms_and_conditions=order.terms_and_conditions,
        notes=order.notes,
        created_by_id=order.created_by_id,
        created_at=order.created_at,
        deposit_paid=order.deposit_paid,
        balance_paid=order.balance_paid,
        paid_in_full=order.paid_in_full,
        installation_booked=order.installation_booked,
        installation_completed=order.installation_completed,
        installation_completed_at=order.installation_completed_at,
        review_request_customer_sent_at=order.review_request_customer_sent_at,
        review_request_customer_channel=order.review_request_customer_channel,
        invoice_number=order.invoice_number,
        xero_invoice_id=order.xero_invoice_id,
        payment_link_url=order.payment_link_url,
        travel_time_hours_one_way=order.travel_time_hours_one_way,
        fulfillment_method=getattr(order, "fulfillment_method", QuoteFulfillmentMethod.DELIVERY),
        **delivery_location_response_fields(order),
        is_ninox_origin=is_ninox_origin,
        items=[
            OrderItemResponse(
                id=item.id,
                order_id=item.order_id,
                quote_item_id=item.quote_item_id,
                product_id=item.product_id,
                description=item.description,
                quantity=item.quantity,
                unit_price=item.unit_price,
                line_total=item.line_total,
                discount_amount=item.discount_amount,
                final_line_total=item.final_line_total,
                sort_order=item.sort_order,
                is_custom=item.is_custom,
            )
            for item in order_items
        ],
        access_sheet=access_sheet,
        prize_draw_entry=prize_draw_entry,
        sent_to_production_at=sent_at,
        sent_to_production_by_id=sent_by_id,
        sent_to_production_by_name=sent_by_name,
    )


@router.get("", response_model=List[OrderResponse])
async def list_orders(
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """List all orders (newest first)."""
    statement = select(Order).order_by(Order.created_at.desc())
    orders = session.exec(statement).all()
    result = []
    for order in orders:
        items = session.exec(
            select(OrderItem).where(OrderItem.order_id == order.id).order_by(OrderItem.sort_order)
        ).all()
        result.append(build_order_response(order, list(items), session))
    return result


@router.get("/{order_id}", response_model=OrderResponse)
async def get_order(
    order_id: int,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """Get a single order by id."""
    order = session.exec(select(Order).where(Order.id == order_id)).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    items = session.exec(
        select(OrderItem).where(OrderItem.order_id == order.id).order_by(OrderItem.sort_order)
    ).all()
    return build_order_response(order, list(items), session)


@router.delete("/{order_id}", status_code=204)
async def delete_order(
    order_id: int,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """Permanently delete this order (line items and access sheet data). The quote is not deleted."""
    order = session.exec(select(Order).where(Order.id == order_id)).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    record_order_audit_event(
        session,
        event_type=CustomerHistoryEventType.ORDER_REMOVED.value,
        title="Order Removed",
        description=f"Order {order.order_number} was removed",
        order=order,
        metadata={"reason": "removed"},
        created_by_id=current_user.id,
    )
    delete_order_cascade(session, order_id)
    session.commit()
    return Response(status_code=204)


@router.patch("/{order_id}", response_model=OrderResponse)
async def update_order(
    order_id: int,
    order_data: OrderUpdate,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """Update order status fields (deposit_paid, balance_paid, etc.)."""
    order = session.exec(select(Order).where(Order.id == order_id)).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    old_flag_values = {
        field: bool(getattr(order, field) or False)
        for field in (*_PAYMENT_FIELDS, *_INSTALLATION_FIELDS)
    }
    update_dict = order_data.dict(exclude_unset=True)
    delivery_field_names = {
        "use_alternate_delivery_address",
        "delivery_address_line1",
        "delivery_address_line2",
        "delivery_city",
        "delivery_county",
        "delivery_postcode",
        "delivery_country",
        "delivery_location_notes",
    }
    has_delivery_update = bool(delivery_field_names.intersection(update_dict))
    for field, value in update_dict.items():
        if field not in delivery_field_names:
            setattr(order, field, value)
    if has_delivery_update:
        sync_delivery_location_from_payload(order, order_data, partial=True)
        assert_alternate_delivery_valid(
            order.use_alternate_delivery_address,
            getattr(order, "fulfillment_method", QuoteFulfillmentMethod.DELIVERY),
            order.delivery_address_line1,
            order.delivery_city,
            order.delivery_postcode,
        )
    # Assign invoice_number when first payment is recorded
    if order.invoice_number is None and (order.deposit_paid or order.paid_in_full):
        order.invoice_number = generate_invoice_number(session)
    payment_changes = _collect_order_flag_changes(order, old_flag_values, _PAYMENT_FIELDS)
    installation_changes = _collect_order_flag_changes(order, old_flag_values, _INSTALLATION_FIELDS)
    if payment_changes:
        record_order_audit_event(
            session,
            event_type=CustomerHistoryEventType.ORDER_PAYMENT_UPDATED.value,
            title="Order Payment Updated",
            description=f"{_describe_order_flag_changes(payment_changes)} for order {order.order_number}",
            order=order,
            metadata={
                "changes": payment_changes,
                "invoice_number": order.invoice_number,
            },
            created_by_id=current_user.id,
        )
    if installation_changes:
        record_order_audit_event(
            session,
            event_type=CustomerHistoryEventType.ORDER_INSTALLATION_UPDATED.value,
            title="Order Installation Updated",
            description=f"{_describe_order_flag_changes(installation_changes)} for order {order.order_number}",
            order=order,
            metadata={"changes": installation_changes},
            created_by_id=current_user.id,
        )
        if installation_changes.get("installation_completed") is True:
            on_installation_completed(order, session)
        elif installation_changes.get("installation_completed") is False:
            on_installation_uncompleted(order, session)
    session.add(order)
    session.commit()
    session.refresh(order)
    items = session.exec(
        select(OrderItem).where(OrderItem.order_id == order.id).order_by(OrderItem.sort_order)
    ).all()
    return build_order_response(order, list(items), session)


@router.post("/{order_id}/send-payment-link", response_model=OrderSendPaymentLinkResponse)
async def send_order_payment_link(
    order_id: int,
    data: Optional[OrderSendPaymentLinkRequest] = Body(default=None),
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """Send an external payment URL to the customer by email or SMS."""
    req = data or OrderSendPaymentLinkRequest(channel="sms")
    channel = (req.channel or "").strip().lower()
    if channel not in ("email", "sms"):
        raise HTTPException(status_code=400, detail="channel must be 'email' or 'sms'")

    order = session.exec(select(Order).where(Order.id == order_id)).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    if not order.customer_id:
        raise HTTPException(status_code=400, detail="Order must be associated with a customer")

    customer = session.exec(select(Customer).where(Customer.id == order.customer_id)).first()
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")

    raw_url = (req.payment_url or "").strip() or (order.payment_link_url or "").strip()
    if not raw_url:
        raise HTTPException(status_code=400, detail="Payment URL is required")
    try:
        payment_url = validate_payment_url(raw_url)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    if req.save_link_on_order:
        order.payment_link_url = payment_url
        session.add(order)

    quote = session.exec(select(Quote).where(Quote.id == order.quote_id)).first()
    lead_id = quote.lead_id if quote else None
    company_settings = session.exec(select(CompanySettings).limit(1)).first()
    template_ctx = payment_link_template_context(order, payment_url)
    custom_body = (req.body or "").strip()

    if channel == "sms":
        to_phone = resolve_sms_to_phone(
            session,
            customer,
            explicit_to=(req.to_phone or "").strip() or None,
            lead_id=lead_id,
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
            sms_body = default_payment_sms_body(order, payment_url)

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
                lead_id=lead_id,
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
                notes=f"Payment link for order {order.order_number} sent by SMS to {to_phone}\n{sms_body}",
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
            subject = default_payment_email_subject(order)
        if not body_html:
            body_html = default_payment_email_html(order, payment_url)
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
                    f"Payment link for order {order.order_number} sent to {to_email}",
                    subject,
                    final_text,
                    final_html,
                ),
                created_by_id=current_user.id,
            )
        )

    record_order_audit_event(
        session,
        event_type=CustomerHistoryEventType.ORDER_PAYMENT_LINK_SENT.value,
        title="Payment Link Sent",
        description=f"Payment link for order {order.order_number} sent by {channel}",
        order=order,
        metadata={
            "channel": channel,
            "order_number": order.order_number,
            "payment_url": payment_url,
        },
        created_by_id=current_user.id,
    )
    session.commit()

    return OrderSendPaymentLinkResponse(
        message="Payment link sent successfully",
        channel=channel,
    )


@router.post("/{order_id}/send-review-request", response_model=OrderSendReviewRequestResponse)
async def send_order_review_request(
    order_id: int,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """Send post-install review request to customer immediately and mark staff reminder acted."""
    order = session.exec(select(Order).where(Order.id == order_id)).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    if not order.installation_completed:
        raise HTTPException(status_code=400, detail="Installation must be marked completed first")
    if not order.customer_id:
        raise HTTPException(status_code=400, detail="Order must be associated with a customer")

    create_review_reminder(order, session)
    success, error = send_review_request_to_customer(
        order,
        session,
        actor_user=current_user,
        force=True,
    )
    if not success:
        session.rollback()
        raise HTTPException(status_code=400, detail=error or "Failed to send review request")

    now = datetime.utcnow()
    open_reminder = session.exec(
        select(Reminder).where(
            Reminder.order_id == order.id,
            Reminder.reminder_type == ReminderType.REQUEST_REVIEW,
            Reminder.dismissed_at.is_(None),
            Reminder.acted_upon_at.is_(None),
        )
    ).first()
    if open_reminder:
        open_reminder.acted_upon_at = now
        session.add(open_reminder)

    session.commit()
    session.refresh(order)

    return OrderSendReviewRequestResponse(
        success=True,
        channel=order.review_request_customer_channel,
        staff_reminder_acted=open_reminder is not None,
        message="Review request sent successfully",
    )


@router.get("/{order_id}/invoice/deposit-pdf")
async def get_deposit_paid_invoice_pdf(
    order_id: int,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """Download Deposit Paid invoice PDF. Requires deposit_paid or paid_in_full."""
    order = session.exec(select(Order).where(Order.id == order_id)).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    if not order.invoice_number:
        raise HTTPException(status_code=404, detail="No invoice yet. Mark deposit or paid in full first.")
    if not order.deposit_paid and not order.paid_in_full:
        raise HTTPException(status_code=400, detail="Deposit or paid in full required to download this invoice.")
    if not order.customer_id:
        raise HTTPException(status_code=400, detail="Order has no customer.")
    customer = session.get(Customer, order.customer_id)
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")
    items = list(session.exec(select(OrderItem).where(OrderItem.order_id == order.id).order_by(OrderItem.sort_order)).all())
    company_settings = session.exec(select(CompanySettings).limit(1)).first()
    try:
        pdf_buffer = generate_deposit_paid_invoice_pdf(order, customer, items, company_settings, session)
        pdf_content = pdf_buffer.read()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error generating PDF: {str(e)}")
    safe_name = re.sub(r'[<>:"/\\|?*]', '_', customer.name or "Customer").strip()
    safe_name = re.sub(r'\s+', '_', safe_name)
    inv_display = f"{order.invoice_number}-1" if order.invoice_number else order.invoice_number or ""
    filename = f"Invoice_Deposit_{inv_display}_{safe_name}.pdf"
    record_order_audit_event(
        session,
        event_type=CustomerHistoryEventType.ORDER_INVOICE_ACTION.value,
        title="Deposit Invoice Accessed",
        description=f"Deposit invoice for order {order.order_number} was generated",
        order=order,
        metadata={
            "action": "deposit_invoice_accessed",
            "invoice_type": "deposit",
            "invoice_number": order.invoice_number,
        },
        created_by_id=current_user.id,
    )
    session.commit()
    return Response(
        content=pdf_content,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/{order_id}/invoice/paid-in-full-pdf")
async def get_paid_in_full_invoice_pdf(
    order_id: int,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """Download Paid in Full invoice PDF. Requires paid_in_full."""
    order = session.exec(select(Order).where(Order.id == order_id)).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    if not order.invoice_number:
        raise HTTPException(status_code=404, detail="No invoice yet. Mark paid in full first.")
    if not order.paid_in_full:
        raise HTTPException(status_code=400, detail="Paid in full required to download this invoice.")
    if not order.customer_id:
        raise HTTPException(status_code=400, detail="Order has no customer.")
    customer = session.get(Customer, order.customer_id)
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")
    items = list(session.exec(select(OrderItem).where(OrderItem.order_id == order.id).order_by(OrderItem.sort_order)).all())
    company_settings = session.exec(select(CompanySettings).limit(1)).first()
    try:
        pdf_buffer = generate_paid_in_full_invoice_pdf(order, customer, items, company_settings, session)
        pdf_content = pdf_buffer.read()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error generating PDF: {str(e)}")
    safe_name = re.sub(r'[<>:"/\\|?*]', '_', customer.name or "Customer").strip()
    safe_name = re.sub(r'\s+', '_', safe_name)
    inv_display = f"{order.invoice_number}-2" if order.invoice_number else order.invoice_number or ""
    filename = f"Invoice_PaidInFull_{inv_display}_{safe_name}.pdf"
    record_order_audit_event(
        session,
        event_type=CustomerHistoryEventType.ORDER_INVOICE_ACTION.value,
        title="Paid in Full Invoice Accessed",
        description=f"Paid in full invoice for order {order.order_number} was generated",
        order=order,
        metadata={
            "action": "paid_in_full_invoice_accessed",
            "invoice_type": "paid_in_full",
            "invoice_number": order.invoice_number,
        },
        created_by_id=current_user.id,
    )
    session.commit()
    return Response(
        content=pdf_content,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/{order_id}/push-to-xero")
async def push_to_xero(
    order_id: int,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """Push invoice to XERO via Make.com webhook."""
    order = session.exec(select(Order).where(Order.id == order_id)).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    if not order.invoice_number:
        raise HTTPException(status_code=400, detail="No invoice yet. Mark deposit or paid in full first.")
    if not order.customer_id:
        raise HTTPException(status_code=400, detail="Order has no customer.")
    customer = session.get(Customer, order.customer_id)
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")
    order_items = list(
        session.exec(
            select(OrderItem).where(OrderItem.order_id == order.id).order_by(OrderItem.sort_order)
        ).all()
    )
    result = push_order_invoice_to_make(order, customer, order_items, session)
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error", "Failed to push to XERO"))
    record_order_audit_event(
        session,
        event_type=CustomerHistoryEventType.ORDER_XERO_PUSHED.value,
        title="Order Pushed to XERO",
        description=f"Order {order.order_number} was pushed to XERO",
        order=order,
        metadata={
            "invoice_number": order.invoice_number,
            "xero_invoice_id": result.get("xero_invoice_id") or order.xero_invoice_id,
        },
        created_by_id=current_user.id,
    )
    session.commit()
    return result


@router.post("/{order_id}/access-sheet/send", response_model=AccessSheetSendResponse)
async def send_access_sheet(
    order_id: int,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """Create or get access sheet link for order. Returns URL for staff to copy or email."""
    order = session.exec(select(Order).where(Order.id == order_id)).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    # Get or create AccessSheetRequest
    req = session.exec(
        select(AccessSheetRequest)
        .where(AccessSheetRequest.order_id == order_id)
        .order_by(AccessSheetRequest.created_at.desc())
        .limit(1)
    ).first()

    if not req:
        token = secrets.token_urlsafe(32)
        req = AccessSheetRequest(
            order_id=order_id,
            access_token=token,
            sent_at=datetime.utcnow(),
        )
        session.add(req)
        session.commit()
        session.refresh(req)
    else:
        # Update sent_at if not set
        if not req.sent_at:
            req.sent_at = datetime.utcnow()
            session.add(req)
            session.commit()

    frontend = (os.getenv("FRONTEND_URL") or os.getenv("PUBLIC_FRONTEND_URL") or "").strip()
    if not frontend or not (frontend.startswith("http://") or frontend.startswith("https://")):
        frontend = "https://leadlock-frontend-production.up.railway.app"
    base = frontend.rstrip("/")
    access_sheet_url = f"{base}/access-sheet/{req.access_token}"
    record_order_audit_event(
        session,
        event_type=CustomerHistoryEventType.ORDER_ACCESS_SHEET_SENT.value,
        title="Access Sheet Sent",
        description=f"Access sheet link was prepared for order {order.order_number}",
        order=order,
        metadata={"access_sheet_url": access_sheet_url},
        created_by_id=current_user.id,
    )
    session.commit()

    return AccessSheetSendResponse(
        access_sheet_url=access_sheet_url,
        access_token=req.access_token,
    )


def _build_customer_address(customer: Customer) -> str:
    """Build full address string from customer fields."""
    parts = []
    if customer.address_line1:
        parts.append(customer.address_line1)
    if customer.address_line2:
        parts.append(customer.address_line2)
    if customer.city:
        parts.append(customer.city)
    if customer.county:
        parts.append(customer.county)
    if customer.postcode:
        parts.append(customer.postcode)
    if customer.country:
        parts.append(customer.country)
    return ", ".join(parts) if parts else ""


def _customer_has_full_address(customer: Customer) -> bool:
    """True when line 1, city, and postcode are all non-empty after strip."""
    line1 = (customer.address_line1 or "").strip()
    city = (customer.city or "").strip()
    postcode = (customer.postcode or "").strip()
    return bool(line1 and city and postcode)


def _order_has_address_for_production(order: Order, customer: Customer) -> bool:
    """True when order has a valid address for production (CRM or alternate delivery)."""
    is_collection = (
        getattr(order, "fulfillment_method", QuoteFulfillmentMethod.DELIVERY)
        == QuoteFulfillmentMethod.COLLECTION
    )
    if is_collection:
        return True
    if getattr(order, "use_alternate_delivery_address", False):
        return has_full_delivery_address(order)
    return _customer_has_full_address(customer)


@router.post("/{order_id}/send-to-production")
async def send_to_production(
    order_id: int,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """Send order to production app as a work order. Requires PRODUCTION_APP_API_URL and PRODUCTION_APP_API_KEY."""
    base_url = (os.getenv("PRODUCTION_APP_API_URL") or "").strip().rstrip("/")
    api_key = (os.getenv("PRODUCTION_APP_API_KEY") or "").strip()
    if not base_url or not api_key:
        raise HTTPException(
            status_code=500,
            detail="Production app not configured. Set PRODUCTION_APP_API_URL and PRODUCTION_APP_API_KEY.",
        )

    order = session.exec(select(Order).where(Order.id == order_id)).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    if not order.customer_id:
        raise HTTPException(status_code=400, detail="Order has no customer.")
    customer = session.get(Customer, order.customer_id)
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")

    if not order.deposit_paid and not order.paid_in_full:
        raise HTTPException(
            status_code=400,
            detail="Mark deposit paid or paid in full on the order before sending to production.",
        )
    is_collection = (
        getattr(order, "fulfillment_method", QuoteFulfillmentMethod.DELIVERY)
        == QuoteFulfillmentMethod.COLLECTION
    )
    if not is_collection and not _order_has_address_for_production(order, customer):
        raise HTTPException(
            status_code=400,
            detail=(
                "Customer must have address line 1, city, and postcode, or set a complete "
                "delivery location on the order before sending to production."
            ),
        )

    order_items = list(
        session.exec(
            select(OrderItem).where(OrderItem.order_id == order.id).order_by(OrderItem.sort_order)
        ).all()
    )

    items_payload = []
    for item in order_items:
        product = None
        if item.product_id:
            product = session.get(Product, item.product_id)
        install_hours = float(product.installation_hours) if product and product.installation_hours else 0
        number_of_boxes = product.boxes_per_product if product and product.boxes_per_product is not None else 0
        items_payload.append({
            "product_name": product.name if product else item.description,
            "description": item.description,
            "quantity": float(item.quantity),
            "unit_price": float(item.unit_price),
            "install_hours": install_hours,
            "number_of_boxes": int(number_of_boxes),
        })

    use_alternate = getattr(order, "use_alternate_delivery_address", False) and not is_collection
    if use_alternate:
        routing_address = build_delivery_address(order)
        routing_postcode = order.delivery_postcode or ""
    else:
        routing_address = _build_customer_address(customer)
        routing_postcode = customer.postcode or ""

    production_notes = order.notes or ""
    delivery_notes = (getattr(order, "delivery_location_notes", None) or "").strip()
    if delivery_notes:
        notes_prefix = f"Delivery location notes: {delivery_notes}"
        production_notes = (
            f"{production_notes}\n\n{notes_prefix}".strip()
            if production_notes.strip()
            else notes_prefix
        )

    payload = {
        "order_number": order.order_number,
        "order_id": order.id,
        "fulfillment_method": getattr(
            order, "fulfillment_method", QuoteFulfillmentMethod.DELIVERY
        ).value.lower(),
        "customer_name": customer.name,
        "customer_postcode": routing_postcode,
        "customer_address": routing_address,
        "customer_email": customer.email or "",
        "customer_phone": customer.phone or "",
        "items": items_payload,
        "total_amount": float(order.total_amount),
        "currency": order.currency,
        "installation_booked": order.installation_booked,
        "created_at": order.created_at.isoformat() if order.created_at else None,
        "notes": production_notes,
        "deposit_paid": bool(order.deposit_paid),
        "balance_paid": bool(order.balance_paid),
        "paid_in_full": bool(order.paid_in_full),
        "deposit_amount": float(order.deposit_amount),
        "balance_amount": float(order.balance_amount),
        "invoice_number": order.invoice_number,
    }
    if use_alternate:
        payload["address_is_delivery_location"] = True
        payload["delivery_location_notes"] = delivery_notes
        payload["crm_customer_address"] = _build_customer_address(customer)
    if (
        not is_collection
        and order.travel_time_hours_one_way is not None
    ):
        payload["travel_time_hours_round_trip"] = float(order.travel_time_hours_one_way) * 2.0

    url = f"{base_url}/api/webhooks/work-orders"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(url, json=payload, headers=headers)
            response.raise_for_status()
            data = response.json() if response.content else {}
            record_order_audit_event(
                session,
                event_type=CustomerHistoryEventType.ORDER_SENT_TO_PRODUCTION.value,
                title="Order Sent to Production",
                description=f"Order {order.order_number} was sent to production",
                order=order,
                metadata={"production_response": data or None},
                created_by_id=current_user.id,
            )
            session.commit()
            return {"success": True, "message": "Order sent to production", **data}
    except httpx.HTTPStatusError as e:
        detail = "Production app rejected the request"
        try:
            err_body = e.response.json()
            if "detail" in err_body:
                detail = str(err_body["detail"])
        except Exception:
            pass
        raise HTTPException(status_code=502, detail=detail)
    except httpx.RequestError as e:
        raise HTTPException(status_code=502, detail=f"Failed to reach production app: {str(e)}")
