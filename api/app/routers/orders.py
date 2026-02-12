import os
import re
import secrets
from datetime import date, datetime
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlmodel import Session, select
from typing import List
import httpx
from app.database import get_session
from app.models import Order, OrderItem, Customer, CompanySettings, AccessSheetRequest, Product
from app.auth import get_current_user
from app.schemas import OrderResponse, OrderItemResponse, OrderUpdate, AccessSheetSendResponse, AccessSheetResponse
from app.models import User
from app.invoice_pdf_service import generate_deposit_paid_invoice_pdf, generate_paid_in_full_invoice_pdf
from app.make_xero_service import push_order_invoice_to_make

router = APIRouter(prefix="/api/orders", tags=["orders"])


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


def build_order_response(order: Order, order_items: List[OrderItem], session: Session) -> OrderResponse:
    """Build OrderResponse with items and optional customer_name."""
    customer_name = None
    if order.customer_id:
        customer = session.exec(select(Customer).where(Customer.id == order.customer_id)).first()
        customer_name = customer.name if customer else None

    access_sheet = _build_access_sheet_response(order.id, session)

    return OrderResponse(
        id=order.id,
        quote_id=order.quote_id,
        customer_id=order.customer_id,
        customer_name=customer_name,
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
    update_dict = order_data.dict(exclude_unset=True)
    for field, value in update_dict.items():
        setattr(order, field, value)
    # Assign invoice_number when first payment is recorded
    if order.invoice_number is None and (order.deposit_paid or order.paid_in_full):
        order.invoice_number = generate_invoice_number(session)
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

    payload = {
        "order_number": order.order_number,
        "order_id": order.id,
        "customer_name": customer.name,
        "customer_postcode": customer.postcode or "",
        "customer_address": _build_customer_address(customer),
        "customer_email": customer.email or "",
        "customer_phone": customer.phone or "",
        "items": items_payload,
        "total_amount": float(order.total_amount),
        "currency": order.currency,
        "installation_booked": order.installation_booked,
        "created_at": order.created_at.isoformat() if order.created_at else None,
    }

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
