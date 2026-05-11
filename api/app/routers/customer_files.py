"""Customer / quote / order file (plan) upload, list and delete endpoints.

Files are anchored to a ``Customer`` and optionally scoped to a quote and/or
order. One Cloudinary asset = one ``CustomerFile`` row; on quote acceptance the
existing row picks up the new ``order_id`` so quote and order both see it.
"""

from typing import List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Response, UploadFile
from sqlmodel import Session, select

from app.auth import get_current_user
from app.customer_file_service import (
    delete_customer_file_from_cloudinary,
    upload_customer_file_to_cloudinary,
)
from app.database import get_session
from app.models import (
    Customer,
    CustomerFile,
    CustomerFileKind,
    Order,
    Quote,
    User,
)
from app.schemas import CustomerFileResponse

router = APIRouter(tags=["customer-files"])


def _build_response(cf: CustomerFile, session: Session) -> CustomerFileResponse:
    user = session.get(User, cf.uploaded_by_id)
    return CustomerFileResponse(
        id=cf.id,
        customer_id=cf.customer_id,
        quote_id=cf.quote_id,
        order_id=cf.order_id,
        kind=cf.kind,
        original_filename=cf.original_filename,
        content_type=cf.content_type,
        size_bytes=cf.size_bytes,
        secure_url=cf.secure_url,
        uploaded_by_id=cf.uploaded_by_id,
        uploaded_by_name=user.full_name if user else None,
        created_at=cf.created_at,
    )


def _resolve_kind(raw: Optional[str]) -> CustomerFileKind:
    if not raw:
        return CustomerFileKind.PLAN
    try:
        return CustomerFileKind(raw)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid kind")


async def _persist_upload(
    file: UploadFile,
    *,
    customer_id: int,
    quote_id: Optional[int],
    order_id: Optional[int],
    kind: CustomerFileKind,
    uploaded_by_id: int,
    session: Session,
) -> CustomerFile:
    upload = await upload_customer_file_to_cloudinary(file, customer_id)
    cf = CustomerFile(
        customer_id=customer_id,
        quote_id=quote_id,
        order_id=order_id,
        kind=kind,
        original_filename=file.filename or "file",
        content_type=(upload.get("content_type") or (file.content_type or "").lower() or "application/octet-stream"),
        size_bytes=int(upload.get("bytes") or 0),
        cloudinary_public_id=upload["public_id"],
        cloudinary_resource_type=upload.get("resource_type") or "image",
        secure_url=upload["secure_url"],
        uploaded_by_id=uploaded_by_id,
    )
    session.add(cf)
    session.commit()
    session.refresh(cf)
    return cf


# ---------------------------------------------------------------------------
# Customer-level files (visible only on the customer profile)
# ---------------------------------------------------------------------------


@router.get(
    "/api/customers/{customer_id}/files",
    response_model=List[CustomerFileResponse],
)
async def list_customer_files(
    customer_id: int,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """List customer-level files (no quote or order context)."""
    customer = session.get(Customer, customer_id)
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")
    files = session.exec(
        select(CustomerFile)
        .where(
            CustomerFile.customer_id == customer_id,
            CustomerFile.quote_id.is_(None),
            CustomerFile.order_id.is_(None),
        )
        .order_by(CustomerFile.created_at.desc())
    ).all()
    return [_build_response(f, session) for f in files]


@router.post(
    "/api/customers/{customer_id}/files",
    response_model=CustomerFileResponse,
)
async def upload_customer_file(
    customer_id: int,
    file: UploadFile = File(...),
    kind: Optional[str] = Form(None),
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """Upload a customer-level file (no quote/order context)."""
    customer = session.get(Customer, customer_id)
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")
    cf = await _persist_upload(
        file,
        customer_id=customer_id,
        quote_id=None,
        order_id=None,
        kind=_resolve_kind(kind),
        uploaded_by_id=current_user.id,
        session=session,
    )
    return _build_response(cf, session)


# ---------------------------------------------------------------------------
# Quote-scoped files
# ---------------------------------------------------------------------------


@router.get(
    "/api/quotes/{quote_id}/files",
    response_model=List[CustomerFileResponse],
)
async def list_quote_files(
    quote_id: int,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """List files attached to a quote."""
    quote = session.get(Quote, quote_id)
    if not quote:
        raise HTTPException(status_code=404, detail="Quote not found")
    files = session.exec(
        select(CustomerFile)
        .where(CustomerFile.quote_id == quote_id)
        .order_by(CustomerFile.created_at.desc())
    ).all()
    return [_build_response(f, session) for f in files]


@router.post(
    "/api/quotes/{quote_id}/files",
    response_model=CustomerFileResponse,
)
async def upload_quote_file(
    quote_id: int,
    file: UploadFile = File(...),
    kind: Optional[str] = Form(None),
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """Upload a file attached to a quote (and inherited by the order on acceptance)."""
    quote = session.get(Quote, quote_id)
    if not quote:
        raise HTTPException(status_code=404, detail="Quote not found")
    if not quote.customer_id:
        raise HTTPException(status_code=400, detail="Quote has no customer")
    # If the quote already has an accepted order, propagate immediately so the
    # file shows up in both contexts without waiting for re-acceptance.
    existing_order = session.exec(
        select(Order).where(Order.quote_id == quote_id)
    ).first()
    cf = await _persist_upload(
        file,
        customer_id=quote.customer_id,
        quote_id=quote_id,
        order_id=existing_order.id if existing_order else None,
        kind=_resolve_kind(kind),
        uploaded_by_id=current_user.id,
        session=session,
    )
    return _build_response(cf, session)


# ---------------------------------------------------------------------------
# Order-scoped files (uploads after acceptance)
# ---------------------------------------------------------------------------


@router.get(
    "/api/orders/{order_id}/files",
    response_model=List[CustomerFileResponse],
)
async def list_order_files(
    order_id: int,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """List files attached to an order (includes files inherited from the quote)."""
    order = session.get(Order, order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    files = session.exec(
        select(CustomerFile)
        .where(CustomerFile.order_id == order_id)
        .order_by(CustomerFile.created_at.desc())
    ).all()
    return [_build_response(f, session) for f in files]


@router.post(
    "/api/orders/{order_id}/files",
    response_model=CustomerFileResponse,
)
async def upload_order_file(
    order_id: int,
    file: UploadFile = File(...),
    kind: Optional[str] = Form(None),
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """Upload a file directly against an order (no quote link)."""
    order = session.get(Order, order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    if not order.customer_id:
        raise HTTPException(status_code=400, detail="Order has no customer")
    cf = await _persist_upload(
        file,
        customer_id=order.customer_id,
        quote_id=None,
        order_id=order_id,
        kind=_resolve_kind(kind),
        uploaded_by_id=current_user.id,
        session=session,
    )
    return _build_response(cf, session)


# ---------------------------------------------------------------------------
# Unified delete
# ---------------------------------------------------------------------------


@router.delete("/api/customer-files/{file_id}", status_code=204)
async def delete_customer_file(
    file_id: int,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """Delete a file (best-effort Cloudinary destroy then DB delete)."""
    cf = session.get(CustomerFile, file_id)
    if not cf:
        raise HTTPException(status_code=404, detail="File not found")
    delete_customer_file_from_cloudinary(cf.cloudinary_public_id, cf.cloudinary_resource_type)
    session.delete(cf)
    session.commit()
    return Response(status_code=204)
