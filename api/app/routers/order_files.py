"""Order file (plan) upload, list and delete endpoints, backed by Cloudinary."""

from typing import List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Response, UploadFile
from sqlmodel import Session, select

from app.auth import get_current_user
from app.database import get_session
from app.models import Order, OrderFile, OrderFileKind, User
from app.order_file_service import (
    delete_order_file_from_cloudinary,
    upload_order_file_to_cloudinary,
)
from app.schemas import OrderFileResponse

router = APIRouter(prefix="/api/orders", tags=["order-files"])


def _build_response(of: OrderFile, session: Session) -> OrderFileResponse:
    user = session.get(User, of.uploaded_by_id)
    return OrderFileResponse(
        id=of.id,
        order_id=of.order_id,
        kind=of.kind,
        original_filename=of.original_filename,
        content_type=of.content_type,
        size_bytes=of.size_bytes,
        secure_url=of.secure_url,
        uploaded_by_id=of.uploaded_by_id,
        uploaded_by_name=user.full_name if user else None,
        created_at=of.created_at,
    )


@router.get("/{order_id}/files", response_model=List[OrderFileResponse])
async def list_order_files(
    order_id: int,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """List files attached to an order, newest first."""
    order = session.get(Order, order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    files = session.exec(
        select(OrderFile)
        .where(OrderFile.order_id == order_id)
        .order_by(OrderFile.created_at.desc())
    ).all()
    return [_build_response(f, session) for f in files]


@router.post("/{order_id}/files", response_model=OrderFileResponse)
async def upload_order_file(
    order_id: int,
    file: UploadFile = File(...),
    kind: Optional[str] = Form(None),
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """Upload a PDF/JPG/PNG plan file for an order."""
    order = session.get(Order, order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    file_kind = OrderFileKind.PLAN
    if kind:
        try:
            file_kind = OrderFileKind(kind)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid kind")

    upload = await upload_order_file_to_cloudinary(file, order_id)

    of = OrderFile(
        order_id=order_id,
        kind=file_kind,
        original_filename=file.filename or "file",
        content_type=(file.content_type or "").lower() or "application/octet-stream",
        size_bytes=int(upload.get("bytes") or 0),
        cloudinary_public_id=upload["public_id"],
        cloudinary_resource_type=upload.get("resource_type") or "image",
        secure_url=upload["secure_url"],
        uploaded_by_id=current_user.id,
    )
    session.add(of)
    session.commit()
    session.refresh(of)
    return _build_response(of, session)


@router.delete("/{order_id}/files/{file_id}", status_code=204)
async def delete_order_file(
    order_id: int,
    file_id: int,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """Delete a file from the order (and best-effort from Cloudinary)."""
    of = session.get(OrderFile, file_id)
    if not of or of.order_id != order_id:
        raise HTTPException(status_code=404, detail="File not found")
    delete_order_file_from_cloudinary(of.cloudinary_public_id, of.cloudinary_resource_type)
    session.delete(of)
    session.commit()
    return Response(status_code=204)
