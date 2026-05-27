import os
import re
import secrets
from datetime import date, datetime
from fastapi import APIRouter, Depends, HTTPException
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
)
from app.models import User
from app.invoice_pdf_service import generate_deposit_paid_invoice_pdf, generate_paid_in_full_invoice_pdf
from app.make_xero_service import push_order_invoice_to_make
from app.order_delete import delete_order_cascade
from app.order_audit import record_order_audit_event

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
    from sqlalchemy import func
    year = date.today().year
    prefix = f"INV-{year}-"
    row = session.exec(
        select(func.max(Order.invoice_number)).where(Order.invoice_number.like(f"{prefix}%"))
    ).first()
    if row and row[0] if isinstance(row, (tuple, list)) else row:
        max_val = row[0] if isinstance(row, (tuple, list)) else row
        try:
            next_num = int(max_val.split("-")[-1]) + 1
        except (ValueError, IndexError, AttributeError):
            next_num = 1
    else:
        next_num = 1
    return f"{prefix}{next_num:03d}"


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


def build_order_response(
    order: Order,
    order_items: List[OrderItem],
    session: Session,
    *,
    _customer_name: Optional[str] = None,
    _customer_source_system: Optional[str] = None,
    _lead_source=None,
    _lead_type=None,
    _access_sheet=None,
    _sent_at=None,
    _sent_by_id=None,
    _sent_by_name=None,
) -> OrderResponse:
    """Build OrderResponse with items and optional customer_name.

    Pass pre-fetched _* kwargs to avoid per-order DB queries when building responses for a list.
    """
    customer_name = _customer_name
    customer_source_system = _customer_source_system
    lead_source = _lead_source
    lead_type = _lead_type

    if customer_name is None and order.customer_id:
        customer = session.exec(select(Customer).where(Customer.id == order.customer_id)).first()
        if customer:
            customer_name = customer.name
            customer_source_system = customer.source_system

    if lead_source is None:
        quote = session.exec(select(Quote).where(Quote.id == order.quote_id)).first()
        if quote and quote.lead_id:
            lead = session.exec(select(Lead).where(Lead.id == quote.lead_id)).first()
            lead_source = lead.lead_source if lead else None
            lead_type = lead.lead_type if lead else None

    is_ninox_origin = lead_source == LeadSource.NINOX or customer_source_system == "Ninox"

    access_sheet = _access_sheet if _access_sheet is not None else _build_access_sheet_response(order.id, session)
    if _sent_at is not None or _sent_by_id is not None or _sent_by_name is not None:
        sent_at, sent_by_id, sent_by_name = _sent_at, _sent_by_id, _sent_by_name
    else:
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
        invoice_number=order.invoice_number,
        xero_invoice_id=order.xero_invoice_id,
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
    orders = list(session.exec(statement).all())
    if not orders:
        return []

    order_ids = [o.id for o in orders if o.id]
    customer_ids = list({o.customer_id for o in orders if o.customer_id})
    quote_ids = list({o.quote_id for o in orders if o.quote_id})

    # Batch load order items
    item_map: dict = {oid: [] for oid in order_ids}
    for item in session.exec(
        select(OrderItem)
        .where(OrderItem.order_id.in_(order_ids))
        .order_by(OrderItem.sort_order)
    ).all():
        if item.order_id in item_map:
            item_map[item.order_id].append(item)

    # Batch load customers
    customer_map: dict = {}
    if customer_ids:
        for c in session.exec(select(Customer).where(Customer.id.in_(customer_ids))).all():
            customer_map[c.id] = c

    # Batch load quotes and their leads
    quote_map: dict = {}
    lead_ids: list = []
    if quote_ids:
        for q in session.exec(select(Quote).where(Quote.id.in_(quote_ids))).all():
            quote_map[q.id] = q
            if q.lead_id:
                lead_ids.append(q.lead_id)

    lead_map: dict = {}
    if lead_ids:
        for lead in session.exec(select(Lead).where(Lead.id.in_(lead_ids))).all():
            lead_map[lead.id] = lead

    # Batch load access sheet requests (latest per order)
    frontend = (os.getenv("FRONTEND_URL") or os.getenv("PUBLIC_FRONTEND_URL") or "").strip()
    if not frontend or not (frontend.startswith("http://") or frontend.startswith("https://")):
        frontend = "https://leadlock-frontend-production.up.railway.app"
    base_url = frontend.rstrip("/")

    access_sheet_map: dict = {}
    for req in session.exec(
        select(AccessSheetRequest).where(AccessSheetRequest.order_id.in_(order_ids))
    ).all():
        existing = access_sheet_map.get(req.order_id)
        if existing is None or req.created_at > existing.created_at:
            access_sheet_map[req.order_id] = req

    # Batch load latest production send audit events
    prod_send_map: dict = {}  # order_id -> (created_at, created_by_id, user_name)
    for audit_event, user in session.exec(
        select(OrderAuditEvent, User)
        .outerjoin(User, OrderAuditEvent.created_by_id == User.id)
        .where(
            OrderAuditEvent.order_id.in_(order_ids),
            OrderAuditEvent.event_type == CustomerHistoryEventType.ORDER_SENT_TO_PRODUCTION.value,
        )
        .order_by(OrderAuditEvent.created_at.desc())
    ).all():
        if audit_event.order_id not in prod_send_map:
            prod_send_map[audit_event.order_id] = (
                audit_event.created_at,
                audit_event.created_by_id,
                user.full_name if user else None,
            )

    result = []
    for order in orders:
        items = item_map.get(order.id, [])
        customer = customer_map.get(order.customer_id) if order.customer_id else None
        customer_name = customer.name if customer else None
        customer_source_system = customer.source_system if customer else None
        quote = quote_map.get(order.quote_id) if order.quote_id else None
        lead = lead_map.get(quote.lead_id) if (quote and quote.lead_id) else None
        lead_source = lead.lead_source if lead else None
        lead_type = lead.lead_type if lead else None

        req = access_sheet_map.get(order.id)
        if req:
            access_sheet = AccessSheetResponse(
                access_sheet_url=f"{base_url}/access-sheet/{req.access_token}",
                completed=req.completed_at is not None,
                completed_at=req.completed_at,
                answers=req.answers,
            )
        else:
            access_sheet = None

        sent_at, sent_by_id, sent_by_name = prod_send_map.get(order.id, (None, None, None))

        result.append(build_order_response(
            order,
            items,
            session,
            _customer_name=customer_name,
            _customer_source_system=customer_source_system,
            _lead_source=lead_source,
            _lead_type=lead_type,
            _access_sheet=access_sheet,
            _sent_at=sent_at,
            _sent_by_id=sent_by_id,
            _sent_by_name=sent_by_name,
        ))
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
    session.add(order)
    session.commit()
    session.refresh(order)
    items = session.exec(
        select(OrderItem).where(OrderItem.order_id == order.id).order_by(OrderItem.sort_order)
    ).all()
    return build_order_response(order, list(items), session)


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
