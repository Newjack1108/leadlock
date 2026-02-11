"""
Service for pushing invoices to XERO via Make.com webhook.
Uses env var: MAKE_XERO_WEBHOOK_URL
"""
import os
from typing import Dict, Any, List

import httpx
from sqlmodel import Session

from app.models import Order, OrderItem, Customer


def _build_payload(
    order: Order,
    customer: Customer,
    order_items: List[OrderItem],
) -> Dict[str, Any]:
    """Build JSON payload for Make.com webhook."""
    line_items = []
    for item in sorted(order_items, key=lambda i: getattr(i, "sort_order", 0) or 0):
        line_items.append({
            "description": item.description or "",
            "quantity": float(item.quantity) if item.quantity else 1.0,
            "unit_price": float(item.unit_price) if item.unit_price else 0.0,
            "final_line_total": float(item.final_line_total) if item.final_line_total else 0.0,
            "sort_order": getattr(item, "sort_order", 0) or 0,
        })

    customer_data = {
        "name": customer.name or "",
        "email": customer.email or "",
        "phone": customer.phone or "",
        "address_line1": customer.address_line1 or "",
        "address_line2": customer.address_line2 or "",
        "city": customer.city or "",
        "county": customer.county or "",
        "postcode": customer.postcode or "",
        "country": customer.country or "United Kingdom",
    }

    totals = {
        "subtotal": float(order.subtotal) if order.subtotal else 0.0,
        "discount_total": float(order.discount_total) if order.discount_total else 0.0,
        "total_amount": float(order.total_amount) if order.total_amount else 0.0,
        "deposit_amount": float(order.deposit_amount) if order.deposit_amount else 0.0,
        "balance_amount": float(order.balance_amount) if order.balance_amount else 0.0,
        "currency": order.currency or "GBP",
    }

    return {
        "order_id": order.id,
        "invoice_number": order.invoice_number or "",
        "order_number": order.order_number or "",
        "xero_invoice_id": order.xero_invoice_id,
        "customer": customer_data,
        "line_items": line_items,
        "totals": totals,
        "created_at": order.created_at.isoformat() if order.created_at else None,
    }


def push_order_invoice_to_make(
    order: Order,
    customer: Customer,
    order_items: List[OrderItem],
    session: Session,
) -> Dict[str, Any]:
    """
    POST order invoice data to Make.com webhook. Make.com creates the invoice in XERO.
    Returns dict with success, xero_invoice_id, message, and optional error.
    """
    webhook_url = (os.getenv("MAKE_XERO_WEBHOOK_URL") or "").strip()
    if not webhook_url:
        return {
            "success": False,
            "error": "Make.com XERO webhook not configured. Set MAKE_XERO_WEBHOOK_URL.",
        }

    if not order.invoice_number:
        return {
            "success": False,
            "error": "Order has no invoice number. Mark deposit or paid in full first.",
        }

    if not order_items:
        return {"success": False, "error": "Order has no line items."}

    payload = _build_payload(order, customer, order_items)

    try:
        response = httpx.post(
            webhook_url,
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=30,
        )
    except httpx.TimeoutException:
        return {"success": False, "error": "Make.com webhook request timed out."}
    except Exception as e:
        return {"success": False, "error": f"Failed to call Make.com: {str(e)}"}

    if response.status_code >= 400:
        try:
            err_body = response.json()
            err_msg = err_body.get("error") or err_body.get("message") or str(err_body)
        except Exception:
            err_msg = response.text or f"HTTP {response.status_code}"
        return {"success": False, "error": err_msg}

    try:
        data = response.json()
    except Exception:
        return {
            "success": False,
            "error": "Make.com returned invalid JSON response.",
        }

    success = data.get("success", False)
    xero_invoice_id = data.get("xero_invoice_id")
    message = data.get("message", "Invoice pushed to XERO successfully." if success else "Unknown error.")

    if success and xero_invoice_id and not order.xero_invoice_id:
        order.xero_invoice_id = str(xero_invoice_id)
        session.add(order)
        session.commit()

    return {
        "success": success,
        "xero_invoice_id": xero_invoice_id,
        "message": message,
        "error": None if success else data.get("error") or message,
    }
