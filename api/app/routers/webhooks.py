import os
import sys
from datetime import datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response
from sqlmodel import Session, select
from typing import Optional

# Production `product_type` -> Product.is_extra (see import_product_webhook). Matching is case-insensitive.
# Extras: optional_extra / extra. Main catalogue: product plus line labels (e.g. Stable) from production salesProductType.
PRODUCT_IMPORT_TYPE_EXTRA = frozenset({"extra", "optional_extra"})
PRODUCT_IMPORT_TYPE_MAIN = frozenset(
    {
        "product",
        "stable",
        "stables",
        "shed",
        "sheds",
        "cabin",
        "cabins",
    }
)
from app.database import get_session
from app.models import (
    Lead,
    User,
    StatusHistory,
    LeadStatus,
    LeadType,
    LeadSource,
    Customer,
    SmsMessage,
    SmsDirection,
    Activity,
    ActivityType,
    MessengerMessage,
    MessengerDirection,
    Product,
    ProductCategory,
    ProductOptionalExtra,
    Order,
)
from pydantic import ValidationError
from app.schemas import (
    LeadCreate,
    LeadResponse,
    ProductImportPayload,
    ProductImportResponse,
    ProductImportBatchPayload,
    ProductImportBatchItemResult,
    ProductImportBatchResponse,
    WorkOrderStatusUpdatePayload,
    WorkOrderStatusUpdateResponse,
    CustomerHistoryEventType,
)
from app.auth import get_webhook_api_key, get_product_import_api_key, get_production_app_api_key
from app.routers.settings import get_company_settings
from app.workflow import check_sla_overdue
from app.lead_create_utils import lead_create_to_model_fields
from app.lead_dedupe_service import apply_inbound_duplicate_handling
from app.routers.leads import enrich_lead_response, find_linkable_customer, find_or_create_customer
from app.sms_service import (
    validate_twilio_webhook,
    normalize_phone,
    get_twilio_config,
    send_sms,
    is_unsubscribed_recipient_error,
)
from app.sms_bot_service import BOT_HANDOVER_MESSAGE, generate_bot_reply, should_bot_reply
from app.messenger_service import (
    parse_webhook_payload,
    get_user_profile,
    get_page_access_token,
    get_leads_access_token,
    fetch_leadgen_lead,
)
from app.system_user_service import get_system_user_id
from app.order_audit import record_order_audit_event
from app.review_request_service import on_installation_completed, on_installation_uncompleted

router = APIRouter(prefix="/api/webhooks", tags=["webhooks"])


def resolve_is_extra_from_product_type(product_type: Optional[str]) -> Optional[bool]:
    """
    If product_type is omitted (None), return None — caller defaults new products to is_extra=False
    and leaves is_extra unchanged on update.
    If present, return True/False or raise HTTPException 422 for unknown values.
    """
    if product_type is None:
        return None
    key = product_type.strip().lower()
    if key in PRODUCT_IMPORT_TYPE_EXTRA:
        return True
    if key in PRODUCT_IMPORT_TYPE_MAIN:
        return False
    allowed = sorted(PRODUCT_IMPORT_TYPE_EXTRA | PRODUCT_IMPORT_TYPE_MAIN)
    raise HTTPException(
        status_code=422,
        detail=f"Invalid product_type {product_type!r}. Expected one of: {allowed}",
    )


def resolve_product_category_from_product_type(product_type: Optional[str]) -> Optional[ProductCategory]:
    """If product_type is omitted, return None (keep existing category on update; create uses STABLES)."""
    if product_type is None:
        return None
    key = product_type.strip().lower()
    if key in PRODUCT_IMPORT_TYPE_EXTRA:
        return ProductCategory.STABLES
    if key in ("shed", "sheds"):
        return ProductCategory.SHEDS
    if key in ("cabin", "cabins"):
        return ProductCategory.CABINS
    if key in PRODUCT_IMPORT_TYPE_MAIN:
        return ProductCategory.STABLES
    return None


def resolve_product_category_from_payload_category(category: Optional[str]) -> Optional[ProductCategory]:
    """Resolve payload category (stables|sheds|cabins) to ProductCategory enum."""
    if category is None:
        return None
    key = category.strip().lower()
    if key == "stables":
        return ProductCategory.STABLES
    if key == "sheds":
        return ProductCategory.SHEDS
    if key == "cabins":
        return ProductCategory.CABINS
    return None


@router.post("/leads", response_model=LeadResponse)
async def create_lead_webhook(
    lead_data: LeadCreate,
    api_key: str = Depends(get_webhook_api_key),
    session: Session = Depends(get_session)
):
    """
    Create a lead via webhook (e.g., from Make.com).
    Requires X-API-Key header for authentication.
    Finds or creates a Customer when email or phone is present so automated outreach can run.
    """
    lead = Lead(**lead_create_to_model_fields(lead_data))

    if lead.email or lead.phone:
        customer = find_or_create_customer(lead, session)
        lead.customer_id = customer.id

    # Assign to default user if configured, otherwise leave unassigned
    default_user_id = os.getenv("WEBHOOK_DEFAULT_USER_ID")
    if default_user_id:
        try:
            user_id = int(default_user_id)
            # Verify user exists
            statement = select(User).where(User.id == user_id)
            user = session.exec(statement).first()
            if user:
                lead.assigned_to_id = user_id
        except (ValueError, TypeError):
            # Invalid user ID, leave unassigned
            pass
    
    session.add(lead)
    session.commit()
    session.refresh(lead)
    
    # Create initial status history
    # Use default user ID for status history if available, otherwise use None
    changed_by_id = lead.assigned_to_id if lead.assigned_to_id else None
    
    if changed_by_id:
        status_history = StatusHistory(
            lead_id=lead.id,
            new_status=lead.status,
            changed_by_id=changed_by_id
        )
        session.add(status_history)
        session.commit()

    session.refresh(lead)
    if not changed_by_id:
        try:
            changed_by_id = get_system_user_id(session)
        except Exception:
            changed_by_id = None
    apply_inbound_duplicate_handling(session, lead, changed_by_id)
    session.refresh(lead)
    from app.customer_outreach_service import try_customer_outreach_for_new_lead

    try_customer_outreach_for_new_lead(session, lead)

    # For webhook responses, we need to create a minimal user object for enrich_lead_response
    # Since we don't have a current_user, we'll pass None and handle it in enrich_lead_response
    # Actually, let's get the user if assigned, otherwise create a dummy response
    if lead.assigned_to_id:
        statement = select(User).where(User.id == lead.assigned_to_id)
        current_user = session.exec(statement).first()
    else:
        # Create a minimal user-like object for the response
        # We'll just return the lead without enrichment if no user
        current_user = None
    
    if current_user:
        return enrich_lead_response(lead, session, current_user)
    else:
        # Return basic response without enrichment if no user assigned
        # Still check SLA
        sla_badge = check_sla_overdue(lead, session)
        quote_locked = False
        quote_lock_reason = None
        
        # Check quote prerequisites if lead has customer
        if lead.status == LeadStatus.QUALIFIED and lead.customer_id:
            from app.workflow import check_quote_prerequisites
            statement = select(Customer).where(Customer.id == lead.customer_id)
            customer = session.exec(statement).first()
            if customer:
                can_quote, error = check_quote_prerequisites(customer, session)
                if not can_quote:
                    quote_locked = True
                    quote_lock_reason = error
        
        from app.schemas import customer_to_response
        customer_response = None
        if lead.customer_id:
            statement = select(Customer).where(Customer.id == lead.customer_id)
            customer = session.exec(statement).first()
            if customer:
                customer_response = customer_to_response(customer)
        
        return LeadResponse(
            id=lead.id,
            name=lead.name,
            email=lead.email,
            phone=lead.phone,
            postcode=lead.postcode,
            description=lead.description,
            status=lead.status,
            timeframe=lead.timeframe,
            scope_notes=lead.scope_notes,
            product_interest=lead.product_interest,
            lead_type=getattr(lead, 'lead_type', LeadType.UNKNOWN),
            lead_source=getattr(lead, 'lead_source', LeadSource.UNKNOWN),
            assigned_to_id=lead.assigned_to_id,
            customer_id=lead.customer_id,
            created_at=lead.created_at,
            updated_at=lead.updated_at,
            sla_badge=sla_badge,
            quote_locked=quote_locked,
            quote_lock_reason=quote_lock_reason,
            customer=customer_response
        )


def upsert_product_from_import(session: Session, payload: ProductImportPayload) -> Product:
    """
    Create or update a product from a production import payload.
    Commits on success. Raises HTTPException for invalid type/parent links.
    """
    resolved_is_extra = resolve_is_extra_from_product_type(payload.product_type)
    resolved_category = (
        resolve_product_category_from_payload_category(payload.category)
        or resolve_product_category_from_product_type(payload.product_type)
    )

    # Map payload to Product fields: cost ex VAT from production
    cost_ex_vat = payload.price_ex_vat
    settings = get_company_settings(session)
    margin_pct = getattr(settings, "product_import_gross_margin_pct", None) if settings else None
    if margin_pct is not None and Decimal("0") < margin_pct < Decimal("100"):
        # RRP = Cost / (1 - margin%/100)
        divisor = Decimal("1") - (margin_pct / 100)
        base_price = (cost_ex_vat / divisor).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    else:
        base_price = cost_ex_vat
    installation_hours = payload.install_hours
    number_of_boxes_int = int(payload.number_of_boxes) if payload.number_of_boxes is not None else 0

    # Upsert: prefer production_product_id if provided, else fall back to name
    existing = None
    matched_by_product_id = False
    if payload.product_id is not None:
        existing = session.exec(
            select(Product).where(Product.production_product_id == payload.product_id)
        ).first()
        if existing is not None:
            matched_by_product_id = True
    if existing is None:
        existing = session.exec(select(Product).where(Product.name == payload.name)).first()

    if existing:
        if not matched_by_product_id:
            existing.name = payload.name
            existing.description = payload.description or None
        existing.base_price = base_price
        existing.installation_hours = installation_hours
        existing.boxes_per_product = number_of_boxes_int
        if resolved_is_extra is not None:
            existing.is_extra = resolved_is_extra
        if resolved_category is not None:
            existing.category = resolved_category
        if payload.product_id is not None:
            existing.production_product_id = payload.product_id
        existing.production_pushed_at = datetime.utcnow()
        existing.updated_at = datetime.utcnow()
        session.add(existing)
        session.commit()
        session.refresh(existing)
        product = existing
    else:
        product = Product(
            name=payload.name,
            description=payload.description or None,
            category=resolved_category or ProductCategory.STABLES,
            subcategory=None,
            is_extra=resolved_is_extra if resolved_is_extra is not None else False,
            base_price=base_price,
            unit="Unit",
            is_active=True,
            installation_hours=installation_hours,
            boxes_per_product=number_of_boxes_int,
            production_product_id=payload.product_id,
            production_pushed_at=datetime.utcnow(),
        )
        session.add(product)
        session.commit()
        session.refresh(product)

    if product.is_extra and payload.parent_product_id is not None:
        parent = session.exec(
            select(Product).where(
                Product.production_product_id == payload.parent_product_id,
                Product.is_extra == False,
            )
        ).first()
        if not parent:
            raise HTTPException(
                status_code=422,
                detail=(
                    f"Parent product not found in sales for production id {payload.parent_product_id}; "
                    "sync the main product first or check parent_product_id."
                ),
            )
        existing_link = session.exec(
            select(ProductOptionalExtra).where(
                ProductOptionalExtra.product_id == parent.id,
                ProductOptionalExtra.optional_extra_id == product.id,
            )
        ).first()
        if not existing_link:
            session.add(
                ProductOptionalExtra(
                    product_id=parent.id,
                    optional_extra_id=product.id,
                )
            )
            session.commit()

    return product


def _batch_item_error_detail(exc: Exception) -> str:
    if isinstance(exc, HTTPException):
        detail = exc.detail
        if isinstance(detail, str):
            return detail
        return str(detail)
    if isinstance(exc, ValidationError):
        # Compact first error for summary responses
        errors = exc.errors()
        if errors:
            first = errors[0]
            loc = ".".join(str(p) for p in first.get("loc", ()) if p != "body")
            msg = first.get("msg") or "validation error"
            return f"{loc}: {msg}" if loc else msg
        return "validation error"
    return str(exc) or exc.__class__.__name__


@router.post("/products", response_model=ProductImportResponse)
async def import_product_webhook(
    payload: ProductImportPayload,
    _api_key: str = Depends(get_product_import_api_key),
    session: Session = Depends(get_session),
):
    """
    Create or update a product pushed from the production app.
    Requires Bearer token in Authorization header.
    Upsert: if product_id (Production's ID) provided, match by production_product_id; else match by name.
    When updating by product_id, only pricing/ops fields are applied (price → base_price, install_hours,
    number_of_boxes, product_type/category); the existing LeadLock display name (and description) are kept.
    Name/description from the payload are used on create (and on name-match updates).
    Products from production send cost ex VAT; RRP (base_price) is derived using company gross margin % if set.
    Optional product_type maps to is_extra (e.g. extra / product).
    Optional category maps to Product.category and takes precedence over product_type-derived category.
    If category is omitted, category falls back to product_type-derived mapping.
    If both are omitted, update preserves existing category and create defaults to STABLES.
    For optional extras, parent_product_id (production id of the main product) creates ProductOptionalExtra when set.
    """
    product = upsert_product_from_import(session, payload)
    return ProductImportResponse(success=True, product_id=str(product.id))


@router.post("/products/batch", response_model=ProductImportBatchResponse)
async def import_products_batch_webhook(
    payload: ProductImportBatchPayload,
    _api_key: str = Depends(get_product_import_api_key),
    session: Session = Depends(get_session),
):
    """
    Batch create/update products from the production app.
    Each item is validated and upserted independently; failures do not stop the batch.
    """
    results: list[ProductImportBatchItemResult] = []
    for raw in payload.products:
        production_product_id = None
        if isinstance(raw, dict) and raw.get("product_id") is not None:
            try:
                production_product_id = int(raw["product_id"])
            except (TypeError, ValueError):
                production_product_id = None
        try:
            item = ProductImportPayload.model_validate(raw)
            if item.product_id is not None:
                production_product_id = item.product_id
            product = upsert_product_from_import(session, item)
            results.append(
                ProductImportBatchItemResult(
                    success=True,
                    production_product_id=production_product_id,
                    product_id=str(product.id),
                )
            )
        except Exception as exc:
            try:
                session.rollback()
            except Exception:
                pass
            results.append(
                ProductImportBatchItemResult(
                    success=False,
                    production_product_id=production_product_id,
                    error=_batch_item_error_detail(exc),
                )
            )

    overall_success = all(r.success for r in results) if results else True
    return ProductImportBatchResponse(success=overall_success, results=results)


_INSTALLATION_FIELD_LABELS = {
    "installation_booked": "Installation booked",
    "installation_completed": "Installation completed",
    "installation_scheduled_at": "Installation scheduled start",
    "installation_scheduled_end_at": "Installation scheduled end",
}

_PAYMENT_FIELD_LABELS = {
    "deposit_paid": "Deposit paid",
    "balance_paid": "Balance paid",
    "paid_in_full": "Paid in full",
}


def _describe_flag_changes(changes: list[dict], *, bool_fields: set[str]) -> str:
    parts = []
    for change in changes:
        field = change.get("field")
        label = change.get("label") or field
        if field in bool_fields:
            parts.append(f"{label} {'marked' if change.get('new') else 'cleared'}")
        else:
            parts.append(f"{label} updated")
    return "; ".join(parts) if parts else "Status updated"


def _describe_installation_status_changes(changes: list[dict]) -> str:
    return _describe_flag_changes(
        changes,
        bool_fields={"installation_booked", "installation_completed"},
    )


def _reconcile_payment_flags_from_update(update_dict: dict, order: Order) -> None:
    """
    Align deposit / balance / paid-in-full when production pushes a payment flag.
    Balance paid implies paid in full (and deposit paid). Paid in full implies both.
    """
    if not any(k in update_dict for k in ("deposit_paid", "balance_paid", "paid_in_full")):
        return

    deposit_paid = bool(update_dict["deposit_paid"]) if "deposit_paid" in update_dict else bool(order.deposit_paid or False)
    balance_paid = bool(update_dict["balance_paid"]) if "balance_paid" in update_dict else bool(order.balance_paid or False)
    paid_in_full = bool(update_dict["paid_in_full"]) if "paid_in_full" in update_dict else bool(order.paid_in_full or False)

    if paid_in_full or ("balance_paid" in update_dict and balance_paid):
        deposit_paid = True
        balance_paid = True
        paid_in_full = True
    elif deposit_paid and balance_paid:
        paid_in_full = True

    update_dict["deposit_paid"] = deposit_paid
    update_dict["balance_paid"] = balance_paid
    update_dict["paid_in_full"] = paid_in_full


@router.post("/work-orders/status", response_model=WorkOrderStatusUpdateResponse)
async def work_order_status_webhook(
    payload: WorkOrderStatusUpdatePayload,
    _api_key: str = Depends(get_production_app_api_key),
    session: Session = Depends(get_session),
):
    """
    Accept install booked dates, completed status, and payment flags from production.
    Requires Bearer token matching PRODUCTION_APP_API_KEY (or WEBHOOK_API_KEY).
    Matched by LeadLock order primary key (`order_id`).
    """
    from app.routers.orders import generate_invoice_number

    order = session.exec(select(Order).where(Order.id == payload.order_id)).first()
    if not order:
        raise HTTPException(status_code=404, detail=f"Order {payload.order_id} not found")

    update_dict = payload.model_dump(exclude_unset=True)
    update_dict.pop("order_id", None)

    old_booked = bool(order.installation_booked or False)
    old_completed = bool(order.installation_completed or False)
    old_scheduled_at = getattr(order, "installation_scheduled_at", None)
    old_scheduled_end_at = getattr(order, "installation_scheduled_end_at", None)
    old_deposit = bool(order.deposit_paid or False)
    old_balance = bool(order.balance_paid or False)
    old_paid_in_full = bool(order.paid_in_full or False)

    # Sending a scheduled date implies booked unless explicitly sent false.
    if (
        "installation_scheduled_at" in update_dict
        and update_dict.get("installation_scheduled_at") is not None
        and "installation_booked" not in update_dict
    ):
        update_dict["installation_booked"] = True

    _reconcile_payment_flags_from_update(update_dict, order)

    for field, value in update_dict.items():
        setattr(order, field, value)

    # Assign invoice_number when first payment is recorded (same as CRM PATCH)
    if order.invoice_number is None and (order.deposit_paid or order.paid_in_full):
        order.invoice_number = generate_invoice_number(session)

    installation_changes: list[dict] = []
    payment_changes: list[dict] = []

    new_booked = bool(order.installation_booked or False)
    if old_booked != new_booked:
        installation_changes.append(
            {
                "field": "installation_booked",
                "label": _INSTALLATION_FIELD_LABELS["installation_booked"],
                "old": old_booked,
                "new": new_booked,
            }
        )
    new_completed = bool(order.installation_completed or False)
    if old_completed != new_completed:
        installation_changes.append(
            {
                "field": "installation_completed",
                "label": _INSTALLATION_FIELD_LABELS["installation_completed"],
                "old": old_completed,
                "new": new_completed,
            }
        )
    new_scheduled_at = getattr(order, "installation_scheduled_at", None)
    if old_scheduled_at != new_scheduled_at:
        installation_changes.append(
            {
                "field": "installation_scheduled_at",
                "label": _INSTALLATION_FIELD_LABELS["installation_scheduled_at"],
                "old": old_scheduled_at.isoformat() if old_scheduled_at else None,
                "new": new_scheduled_at.isoformat() if new_scheduled_at else None,
            }
        )
    new_scheduled_end_at = getattr(order, "installation_scheduled_end_at", None)
    if old_scheduled_end_at != new_scheduled_end_at:
        installation_changes.append(
            {
                "field": "installation_scheduled_end_at",
                "label": _INSTALLATION_FIELD_LABELS["installation_scheduled_end_at"],
                "old": old_scheduled_end_at.isoformat() if old_scheduled_end_at else None,
                "new": new_scheduled_end_at.isoformat() if new_scheduled_end_at else None,
            }
        )

    new_deposit = bool(order.deposit_paid or False)
    if old_deposit != new_deposit:
        payment_changes.append(
            {
                "field": "deposit_paid",
                "label": _PAYMENT_FIELD_LABELS["deposit_paid"],
                "old": old_deposit,
                "new": new_deposit,
            }
        )
    new_balance = bool(order.balance_paid or False)
    if old_balance != new_balance:
        payment_changes.append(
            {
                "field": "balance_paid",
                "label": _PAYMENT_FIELD_LABELS["balance_paid"],
                "old": old_balance,
                "new": new_balance,
            }
        )
    new_paid_in_full = bool(order.paid_in_full or False)
    if old_paid_in_full != new_paid_in_full:
        payment_changes.append(
            {
                "field": "paid_in_full",
                "label": _PAYMENT_FIELD_LABELS["paid_in_full"],
                "old": old_paid_in_full,
                "new": new_paid_in_full,
            }
        )

    if not installation_changes and not payment_changes:
        return WorkOrderStatusUpdateResponse(
            success=True,
            updated=False,
            order_id=order.id,
            order_number=order.order_number,
        )

    system_user_id = get_system_user_id(session)
    if payment_changes:
        record_order_audit_event(
            session,
            event_type=CustomerHistoryEventType.ORDER_PAYMENT_UPDATED.value,
            title="Order Payment Updated",
            description=(
                f"{_describe_flag_changes(payment_changes, bool_fields=set(_PAYMENT_FIELD_LABELS))} "
                f"for order {order.order_number} (from production)"
            ),
            order=order,
            metadata={
                "changes": payment_changes,
                "invoice_number": order.invoice_number,
                "source": "production",
            },
            created_by_id=system_user_id,
        )
    if installation_changes:
        record_order_audit_event(
            session,
            event_type=CustomerHistoryEventType.ORDER_INSTALLATION_UPDATED.value,
            title="Order Installation Updated",
            description=f"{_describe_installation_status_changes(installation_changes)} for order {order.order_number} (from production)",
            order=order,
            metadata={"changes": installation_changes, "source": "production"},
            created_by_id=system_user_id,
        )

    if old_completed != new_completed:
        if new_completed:
            on_installation_completed(order, session)
        else:
            on_installation_uncompleted(order, session)

    session.add(order)
    session.commit()
    session.refresh(order)

    return WorkOrderStatusUpdateResponse(
        success=True,
        updated=True,
        order_id=order.id,
        order_number=order.order_number,
    )


@router.post("/twilio/sms")
async def twilio_inbound_sms(request: Request, session: Session = Depends(get_session)):
    """
    Twilio webhook for incoming SMS. No JWT; validated via X-Twilio-Signature.
    Configure in Twilio: A MESSAGE COMES IN -> POST to this URL.
    """
    form = await request.form()
    params = dict(form)
    signature = request.headers.get("X-Twilio-Signature", "")
    _, auth_token, _ = get_twilio_config()
    if not auth_token:
        return Response(content="Twilio not configured", status_code=503)

    # Use TWILIO_SMS_WEBHOOK_URL when behind a proxy (e.g. Railway) so signature validation uses the public URL
    url = (os.getenv("TWILIO_SMS_WEBHOOK_URL") or str(request.url)).rstrip("/")
    if not validate_twilio_webhook(url, params, signature, auth_token):
        print("Twilio SMS webhook signature validation failed; set TWILIO_SMS_WEBHOOK_URL if behind a proxy", file=sys.stderr, flush=True)
        return Response(content="Invalid signature", status_code=403)

    from_phone = params.get("From", "")
    to_phone = params.get("To", "")
    body = params.get("Body", "")
    message_sid = params.get("MessageSid", "")
    if not from_phone or not body:
        print("Twilio SMS webhook: missing From or Body in request (params empty or incomplete)", file=sys.stderr, flush=True)
        return Response(content="<Response></Response>", media_type="application/xml")

    from_normalized = normalize_phone(from_phone)
    lead = None

    # Find customer by phone, then lead by phone
    stmt = select(Customer).where(Customer.phone.isnot(None))
    customers = list(session.exec(stmt).all())
    customer = None
    for c in customers:
        if c.phone and normalize_phone(c.phone) == from_normalized:
            customer = c
            break

    if not customer:
        stmt = select(Lead).where(Lead.phone.isnot(None))
        leads = list(session.exec(stmt).all())
        lead = None
        for l in leads:
            if l.phone and normalize_phone(l.phone) == from_normalized:
                lead = l
                break
        if lead and lead.customer_id:
            customer = session.get(Customer, lead.customer_id)
        if not customer and lead:
            # Attach to lead's customer if qualified, else skip storing (MVP: only known customers/leads)
            pass
        if not customer:
            # Unknown number: return 200 so Twilio doesn't retry; don't store
            mask = from_normalized[-4:] if len(from_normalized) >= 4 else "****"
            print(f"Twilio SMS: no customer/lead match for From=...{mask}", file=sys.stderr, flush=True)
            return Response(content="<Response></Response>", media_type="application/xml")

    # If we found only a lead with no customer, we still need a customer_id for SmsMessage.
    if not customer:
        mask = from_normalized[-4:] if len(from_normalized) >= 4 else "****"
        print(f"Twilio SMS: no customer/lead match for From=...{mask}", file=sys.stderr, flush=True)
        return Response(content="<Response></Response>", media_type="application/xml")

    try:
        activity_user_id = get_system_user_id(session)
    except Exception:
        activity_user_id = None

    if message_sid:
        dup_stmt = (
            select(SmsMessage)
            .where(SmsMessage.customer_id == customer.id)
            .where(SmsMessage.direction == SmsDirection.RECEIVED)
            .where(SmsMessage.twilio_sid == message_sid)
        )
        if session.exec(dup_stmt).first():
            print(
                f"Twilio SMS: duplicate MessageSid={message_sid} for customer_id={customer.id}, skipping",
                file=sys.stderr,
                flush=True,
            )
            return Response(content="<Response></Response>", media_type="application/xml")

    msg = SmsMessage(
        customer_id=customer.id,
        lead_id=lead.id if lead else None,
        direction=SmsDirection.RECEIVED,
        from_phone=from_phone,
        to_phone=to_phone,
        body=body,
        twilio_sid=message_sid,
        received_at=datetime.utcnow(),
    )
    session.add(msg)
    if activity_user_id is not None:
        activity = Activity(
            customer_id=customer.id,
            activity_type=ActivityType.SMS_RECEIVED,
            notes=f"SMS received from {from_phone}\n{(body or '').strip()}",
            created_by_id=activity_user_id,
        )
        session.add(activity)
    print(f"Twilio SMS: stored inbound message for customer_id={customer.id}", file=sys.stderr, flush=True)
    session.commit()

    # Exact HOLD / CLOSE keywords update open quotes; skip SMS bot when handled.
    try:
        from app.sms_quote_keyword_service import apply_sms_quote_keyword

        quote_keyword = apply_sms_quote_keyword(session, customer.id, body)
        if quote_keyword:
            print(
                f"Twilio SMS: applied quote keyword={quote_keyword} for customer_id={customer.id}",
                file=sys.stderr,
                flush=True,
            )
            return Response(content="<Response></Response>", media_type="application/xml")
    except Exception as e:
        print(f"Twilio SMS quote keyword error: {e}", file=sys.stderr, flush=True)

    # Optional out-of-hours SMS bot reply.
    try:
        settings = get_company_settings(session)
        customer = session.get(Customer, customer.id)
        if not customer:
            return Response(content="<Response></Response>", media_type="application/xml")
        should_reply, reason = should_bot_reply(
            session, settings, customer, body, inbound_received_at=msg.received_at
        )
        if session.is_modified(customer, include_collections=False):
            session.add(customer)
            session.commit()
        if should_reply:
            bot_reply, _from_ai = await generate_bot_reply(settings, customer.name if customer else "Customer", body)
            if reason == "handover":
                bot_reply = BOT_HANDOVER_MESSAGE

            sent_ok, sent_sid, sent_err = send_sms(from_phone, bot_reply)
            if sent_ok:
                outbound = SmsMessage(
                    customer_id=customer.id,
                    lead_id=lead.id if lead else None,
                    direction=SmsDirection.SENT,
                    from_phone=to_phone,
                    to_phone=from_phone,
                    body=bot_reply,
                    twilio_sid=sent_sid,
                    sent_at=datetime.utcnow(),
                )
                session.add(outbound)
                if activity_user_id is not None:
                    bot_activity = Activity(
                        customer_id=customer.id,
                        activity_type=ActivityType.SMS_SENT,
                        notes=f"SMS bot reply sent to {from_phone}\n{bot_reply}",
                        created_by_id=activity_user_id,
                    )
                    session.add(bot_activity)
                if bot_reply.startswith("[BOT_HANDOVER]"):
                    pause_m = max(0, int(settings.sms_bot_pause_minutes_after_handover or 0))
                    if pause_m > 0:
                        cust = session.get(Customer, customer.id)
                        if cust:
                            cust.sms_bot_suppress_auto_reply_before_utc = datetime.utcnow() + timedelta(
                                minutes=pause_m
                            )
                            session.add(cust)
                session.commit()
            else:
                if is_unsubscribed_recipient_error(sent_err):
                    customer.automated_reminder_outreach_opt_out = True
                    customer.sms_bot_stopped = True
                    session.add(customer)
                    session.commit()
                print(f"Twilio SMS bot send failed: {sent_err}", file=sys.stderr, flush=True)
        elif reason:
            print(f"Twilio SMS bot skipped: {reason}", file=sys.stderr, flush=True)
    except Exception as e:
        print(f"Twilio SMS bot error: {e}", file=sys.stderr, flush=True)

    return Response(content="<Response></Response>", media_type="application/xml")


# --- Facebook Messenger webhook ---

def _get_activity_user_id(session: Session) -> Optional[int]:
    """System user id for webhook-created Activity / StatusHistory rows."""
    try:
        return get_system_user_id(session)
    except Exception:
        return None


@router.get("/facebook/messenger")
async def facebook_messenger_verify(request: Request):
    """Facebook webhook verification: return hub.challenge if verify_token matches."""
    hub_mode = request.query_params.get("hub.mode")
    hub_verify_token = request.query_params.get("hub.verify_token")
    hub_challenge = request.query_params.get("hub.challenge")
    verify_token = os.getenv("FACEBOOK_VERIFY_TOKEN")
    if not verify_token or hub_mode != "subscribe" or hub_verify_token != verify_token or not hub_challenge:
        raise HTTPException(status_code=403, detail="Verification failed")
    return Response(content=hub_challenge, media_type="text/plain")


@router.post("/facebook/messenger")
async def facebook_messenger_webhook(request: Request, session: Session = Depends(get_session)):
    """
    Process incoming Facebook Messenger webhook events.
    Match by messenger_psid (Customer first, then Lead with customer_id); unknown users get Lead + Customer created.
    """
    try:
        body = await request.json()
    except Exception:
        return Response(status_code=200)
    events = parse_webhook_payload(body)
    if not events:
        return Response(status_code=200)
    activity_user_id = _get_activity_user_id(session)
    now = datetime.utcnow()
    new_leads_for_outreach: list[Lead] = []
    for ev in events:
        sender_psid = ev["sender_id"]
        text = ev.get("text", "")
        mid = ev.get("mid")
        if not text:
            continue
        customer = None
        lead = None
        # Match: Customer first by messenger_psid
        stmt = select(Customer).where(Customer.messenger_psid == sender_psid)
        customer = session.exec(stmt).first()
        if not customer:
            stmt = select(Lead).where(Lead.messenger_psid == sender_psid)
            lead = session.exec(stmt).first()
            if lead and lead.customer_id:
                customer = session.get(Customer, lead.customer_id)
        if not customer:
            # Phone fallback: get profile (with optional phone), match by normalized phone
            ok, first_name, last_name, profile_phone, err = get_user_profile(sender_psid, get_page_access_token())
            if profile_phone:
                from_normalized = normalize_phone(profile_phone)
                if from_normalized:
                    stmt = select(Customer).where(Customer.phone.isnot(None))
                    for c in session.exec(stmt).all():
                        if c.phone and normalize_phone(c.phone) == from_normalized:
                            customer = c
                            break
                    if not customer:
                        stmt = select(Lead).where(Lead.phone.isnot(None))
                        for l in session.exec(stmt).all():
                            if l.phone and normalize_phone(l.phone) == from_normalized and l.customer_id:
                                lead = l
                                customer = session.get(Customer, l.customer_id)
                                break
                    if customer:
                        customer.messenger_psid = sender_psid
                        session.add(customer)
                        if lead:
                            lead.messenger_psid = sender_psid
                            session.add(lead)
            if not customer:
                # Unknown user: create Lead + Customer
                name = " ".join(filter(None, [first_name, last_name])) if (first_name or last_name) else f"Facebook {sender_psid[:8]}"
                from datetime import date
                year = date.today().year
                num_stmt = select(Customer).where(Customer.customer_number.like(f"CUST-{year}-%"))
                existing = list(session.exec(num_stmt).all())
                numbers = []
                for c in existing:
                    try:
                        num = int(c.customer_number.split("-")[-1])
                        numbers.append(num)
                    except (ValueError, IndexError):
                        continue
                next_num = max(numbers) + 1 if numbers else 1
                customer_number = f"CUST-{year}-{next_num:03d}"
                customer = Customer(
                    customer_number=customer_number,
                    name=name,
                    messenger_psid=sender_psid,
                    customer_since=now,
                )
                session.add(customer)
                session.flush()
                lead = Lead(
                    name=name,
                    lead_source=LeadSource.FACEBOOK,
                    messenger_psid=sender_psid,
                    customer_id=customer.id,
                )
                session.add(lead)
                session.flush()
                new_leads_for_outreach.append(lead)
        msg = MessengerMessage(
            customer_id=customer.id,
            lead_id=lead.id if lead else None,
            direction=MessengerDirection.RECEIVED,
            from_psid=sender_psid,
            to_psid=None,
            body=text,
            facebook_mid=mid,
            received_at=now,
        )
        session.add(msg)
        if activity_user_id:
            activity = Activity(
                customer_id=customer.id,
                activity_type=ActivityType.MESSENGER_RECEIVED,
                notes=f"Messenger received: {text[:50]}...",
                created_by_id=activity_user_id,
            )
            session.add(activity)
    try:
        session.commit()
    except Exception as e:
        print(f"Facebook Messenger webhook commit error: {e}", file=sys.stderr, flush=True)
        session.rollback()
        return Response(status_code=200)

    from app.customer_outreach_service import try_customer_outreach_for_new_lead

    for lo in new_leads_for_outreach:
        fresh = session.get(Lead, lo.id)
        if fresh:
            try_customer_outreach_for_new_lead(session, fresh)
    return Response(status_code=200)


# --- Facebook Lead Ads webhook ---

def _parse_leadgen_events(body: dict) -> list[dict]:
    """Extract leadgen events from Meta webhook payload. Returns list of {leadgen_id, page_id, form_id, created_time}."""
    if body.get("object") != "page":
        return []
    events = []
    for entry in body.get("entry", []):
        for change in entry.get("changes", []):
            if change.get("field") != "leadgen":
                continue
            value = change.get("value") or {}
            leadgen_id = value.get("leadgen_id")
            if leadgen_id:
                events.append({
                    "leadgen_id": str(leadgen_id),
                    "page_id": value.get("page_id"),
                    "form_id": value.get("form_id"),
                    "created_time": value.get("created_time"),
                })
    return events


def _normalise_leadgen_field_map(field_map: dict) -> dict[str, str]:
    """Strip whitespace and lowercase Facebook field names so mapping is case-insensitive."""
    normalised: dict[str, str] = {}
    for raw_key, value in (field_map or {}).items():
        if raw_key is None:
            continue
        key = str(raw_key).strip().lower()
        if not key or key in normalised:
            continue
        normalised[key] = value
    return normalised


def _leadgen_advert_description_lines(ad_name: Optional[str] = None, ad_id: Optional[str] = None) -> list[str]:
    """Build optional Facebook Advert / Ad ID lines. Missing metadata is omitted, not an error."""
    lines: list[str] = []
    name = (str(ad_name).strip() if ad_name is not None else "")
    ident = (str(ad_id).strip() if ad_id is not None else "")
    if name:
        lines.append(f"Facebook Advert: {name}")
    if ident:
        lines.append(f"Facebook Ad ID: {ident}")
    return lines


def _leadgen_field_map_to_lead_data(
    field_map: dict,
    ad_name: Optional[str] = None,
    ad_id: Optional[str] = None,
) -> dict:
    """Map Facebook Lead Ad field_data to LeadLock name, email, phone, postcode, description."""
    fields = _normalise_leadgen_field_map(field_map)
    # Common Meta field names (normalised to lowercase)
    name = (
        fields.get("full_name") or
        " ".join(filter(None, [fields.get("first_name"), fields.get("last_name")])) or
        fields.get("name")
    )
    if not name or not str(name).strip():
        name = "Facebook Lead"
    email = (fields.get("email") or "").strip() or None
    phone = (fields.get("phone_number") or fields.get("phone") or "").strip() or None
    postcode = (
        fields.get("postcode")
        or fields.get("post_code")
        or fields.get("zip")
        or fields.get("zip_code")
        or ""
    ).strip() or None
    # Use known keys for description; then any remaining custom keys
    known = {
        "full_name",
        "first_name",
        "last_name",
        "name",
        "email",
        "phone_number",
        "phone",
        "postcode",
        "post_code",
        "zip",
        "zip_code",
        "city",
        "state",
    }
    extra = [f"{k}: {v}" for k, v in fields.items() if k not in known and v]
    header = _leadgen_advert_description_lines(ad_name=ad_name, ad_id=ad_id)
    parts: list[str] = []
    if header:
        parts.append("\n".join(header))
    if extra:
        parts.append("\n".join(extra))
    description = "\n\n".join(parts) if parts else None
    return {"name": str(name).strip(), "email": email, "phone": phone, "postcode": postcode, "description": description}


@router.get("/facebook/leadgen")
async def facebook_leadgen_verify(request: Request):
    """Facebook Lead Ads webhook verification: return hub.challenge if verify_token matches."""
    hub_mode = request.query_params.get("hub.mode")
    hub_verify_token = request.query_params.get("hub.verify_token")
    hub_challenge = request.query_params.get("hub.challenge")
    verify_token = os.getenv("FACEBOOK_VERIFY_TOKEN")
    if not verify_token or hub_mode != "subscribe" or hub_verify_token != verify_token or not hub_challenge:
        raise HTTPException(status_code=403, detail="Verification failed")
    return Response(content=hub_challenge, media_type="text/plain")


@router.post("/facebook/leadgen")
async def facebook_leadgen_webhook(request: Request, session: Session = Depends(get_session)):
    """
    Process incoming Facebook Lead Ads webhook events.
    Fetches lead data from Graph API and creates Customer + Lead with lead_source=FACEBOOK.
    """
    try:
        body = await request.json()
    except Exception:
        return Response(status_code=200)
    events = _parse_leadgen_events(body)
    if not events:
        return Response(status_code=200)
    activity_user_id = _get_activity_user_id(session)
    token = get_leads_access_token()
    if not token:
        print(
            "Facebook Lead Ads webhook: FACEBOOK_LEADS_ACCESS_TOKEN not set "
            "(and no legacy FACEBOOK_PAGE_ACCESS_TOKEN fallback)",
            file=sys.stderr,
            flush=True,
        )
        return Response(status_code=200)
    from datetime import date
    now = datetime.utcnow()
    year = date.today().year
    created_lead_ids: list[int] = []
    for ev in events:
        leadgen_id = ev["leadgen_id"]
        ok, payload, err = fetch_leadgen_lead(leadgen_id, token)
        field_map = (payload or {}).get("field_map") if payload else None
        if not ok or not field_map:
            print(
                "Facebook Lead Ads: failed to fetch lead "
                f"leadgen_id={leadgen_id} page_id={ev.get('page_id')} "
                f"form_id={ev.get('form_id')} error={err}",
                file=sys.stderr,
                flush=True,
            )
            continue
        ad_name = payload.get("ad_name")
        ad_id = payload.get("ad_id")
        print(
            "Facebook Lead Ads: fetched lead "
            f"leadgen_id={leadgen_id} page_id={ev.get('page_id')} "
            f"form_id={ev.get('form_id')} "
            f"ad_id={ad_id or '-'} ad_name={ad_name or '-'}",
            file=sys.stderr,
            flush=True,
        )
        data = _leadgen_field_map_to_lead_data(field_map, ad_name=ad_name, ad_id=ad_id)
        probe = Lead(
            name=data["name"],
            email=data.get("email"),
            phone=data.get("phone"),
            postcode=data.get("postcode"),
        )
        customer = find_linkable_customer(session, probe)
        if not customer:
            num_stmt = select(Customer).where(Customer.customer_number.like(f"CUST-{year}-%"))
            existing = list(session.exec(num_stmt).all())
            numbers = []
            for c in existing:
                try:
                    num = int(c.customer_number.split("-")[-1])
                    numbers.append(num)
                except (ValueError, IndexError):
                    continue
            next_num = max(numbers) + 1 if numbers else 1
            customer_number = f"CUST-{year}-{next_num:03d}"
            customer = Customer(
                customer_number=customer_number,
                name=data["name"],
                email=data.get("email"),
                phone=data.get("phone"),
                postcode=data.get("postcode"),
                customer_since=now,
            )
            session.add(customer)
            session.flush()
        lead = Lead(
            name=data["name"],
            email=data.get("email"),
            phone=data.get("phone"),
            postcode=data.get("postcode"),
            description=data.get("description"),
            lead_source=LeadSource.FACEBOOK,
            customer_id=customer.id,
        )
        session.add(lead)
        session.flush()
        created_lead_ids.append(lead.id)
        if activity_user_id:
            activity = Activity(
                customer_id=customer.id,
                activity_type=ActivityType.NOTE,
                notes="Lead from Facebook Lead Ad form",
                created_by_id=activity_user_id,
            )
            session.add(activity)
            status_history = StatusHistory(
                lead_id=lead.id,
                new_status=LeadStatus.NEW,
                changed_by_id=activity_user_id,
            )
            session.add(status_history)
    try:
        session.commit()
    except Exception as e:
        print(f"Facebook Lead Ads webhook commit error: {e}", file=sys.stderr, flush=True)
        session.rollback()
        return Response(status_code=200)

    from app.customer_outreach_service import try_customer_outreach_for_new_lead

    for lid in created_lead_ids:
        lo = session.get(Lead, lid)
        if lo:
            try_customer_outreach_for_new_lead(session, lo)
    return Response(status_code=200)
