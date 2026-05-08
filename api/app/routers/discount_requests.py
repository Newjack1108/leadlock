from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session, select
from typing import List, Optional
from app.database import get_session
from app.models import (
    DiscountRequest,
    DiscountRequestStatus,
    Quote,
    QuoteItem,
    QuoteDiscount,
    User,
    QuoteStatus,
    UserRole,
)
from app.auth import get_current_user, require_role
from app.constants import VAT_RATE_DECIMAL
from app.schemas import (
    DiscountRequestCreate,
    DiscountRequestResponse,
    DiscountRequestReject,
)
from app.routers.quotes import apply_custom_discount_to_quote
from datetime import datetime
from decimal import Decimal

router = APIRouter(prefix="/api", tags=["discount-requests"])


def _build_response(dr: DiscountRequest, session: Session) -> DiscountRequestResponse:
    requested_by = session.get(User, dr.requested_by_id)
    quote = session.get(Quote, dr.quote_id)
    return DiscountRequestResponse(
        id=dr.id,
        quote_id=dr.quote_id,
        requested_by_id=dr.requested_by_id,
        requested_by_name=requested_by.full_name if requested_by else None,
        discount_type=dr.discount_type,
        discount_value=dr.discount_value,
        scope=dr.scope,
        reason=dr.reason,
        status=dr.status,
        approved_by_id=dr.approved_by_id,
        responded_at=dr.responded_at,
        rejection_reason=dr.rejection_reason,
        created_at=dr.created_at,
        updated_at=dr.updated_at,
        quote_number=quote.quote_number if quote else None,
    )


@router.post("/quotes/{quote_id}/discount-requests", response_model=DiscountRequestResponse)
async def create_discount_request(
    quote_id: int,
    body: DiscountRequestCreate,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """Create a discount request for a quote. Quote must be DRAFT. Only one pending request per quote."""
    quote = session.get(Quote, quote_id)
    if not quote:
        raise HTTPException(status_code=404, detail="Quote not found")
    if quote.status != QuoteStatus.DRAFT:
        raise HTTPException(
            status_code=400,
            detail="Discount requests can only be created for draft quotes",
        )
    pending = session.exec(
        select(DiscountRequest).where(
            DiscountRequest.quote_id == quote_id,
            DiscountRequest.status == DiscountRequestStatus.PENDING,
        )
    ).first()
    if pending:
        raise HTTPException(
            status_code=400,
            detail="This quote already has a pending discount request",
        )
    dr = DiscountRequest(
        quote_id=quote_id,
        requested_by_id=current_user.id,
        discount_type=body.discount_type,
        discount_value=body.discount_value,
        scope=body.scope,
        reason=body.reason,
        status=DiscountRequestStatus.PENDING,
    )
    session.add(dr)
    session.commit()
    session.refresh(dr)
    return _build_response(dr, session)


@router.get("/quotes/{quote_id}/discount-requests", response_model=List[DiscountRequestResponse])
async def list_discount_requests_for_quote(
    quote_id: int,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """List all discount requests for a quote."""
    quote = session.get(Quote, quote_id)
    if not quote:
        raise HTTPException(status_code=404, detail="Quote not found")
    statement = select(DiscountRequest).where(DiscountRequest.quote_id == quote_id)
    requests = session.exec(statement).all()
    return [_build_response(dr, session) for dr in requests]


@router.get("/discount-requests", response_model=List[DiscountRequestResponse])
async def list_discount_requests(
    status: Optional[str] = Query(None, description="PENDING, APPROVED, REJECTED"),
    quote_id: Optional[int] = Query(None),
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """List discount requests. Approvers (DIRECTOR/SALES_MANAGER) see pending; others see their own."""
    can_approve = current_user.role in (UserRole.DIRECTOR, UserRole.SALES_MANAGER)
    statement = select(DiscountRequest)
    if quote_id is not None:
        statement = statement.where(DiscountRequest.quote_id == quote_id)
    if status:
        try:
            status_enum = DiscountRequestStatus(status)
            statement = statement.where(DiscountRequest.status == status_enum)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid status")
    if not can_approve:
        statement = statement.where(DiscountRequest.requested_by_id == current_user.id)
    statement = statement.order_by(DiscountRequest.created_at.desc())
    requests = session.exec(statement).all()
    return [_build_response(dr, session) for dr in requests]


@router.patch("/discount-requests/{request_id}/approve", response_model=DiscountRequestResponse)
async def approve_discount_request(
    request_id: int,
    session: Session = Depends(get_session),
    current_user: User = Depends(require_role([UserRole.DIRECTOR, UserRole.SALES_MANAGER])),
):
    """Approve a discount request and apply the discount to the quote."""
    dr = session.get(DiscountRequest, request_id)
    if not dr:
        raise HTTPException(status_code=404, detail="Discount request not found")
    if dr.status != DiscountRequestStatus.PENDING:
        raise HTTPException(
            status_code=400,
            detail="Only pending requests can be approved",
        )
    if dr.requested_by_id == current_user.id:
        raise HTTPException(
            status_code=400,
            detail="You cannot approve your own discount request",
        )
    quote = session.get(Quote, dr.quote_id)
    if not quote:
        raise HTTPException(status_code=404, detail="Quote not found")
    if quote.status != QuoteStatus.DRAFT:
        raise HTTPException(
            status_code=400,
            detail="Discount can only be applied to draft quotes",
        )
    quote_items = list(session.exec(select(QuoteItem).where(QuoteItem.quote_id == quote.id)).all())
    if not quote_items:
        raise HTTPException(status_code=400, detail="Quote has no items")

    description = f"Custom discount (Request #{dr.id})"
    apply_custom_discount_to_quote(
        quote,
        dr.discount_type,
        dr.discount_value,
        dr.scope,
        description,
        quote_items,
        session,
        current_user,
    )
    dr.status = DiscountRequestStatus.APPROVED
    dr.approved_by_id = current_user.id
    dr.responded_at = datetime.utcnow()
    dr.updated_at = datetime.utcnow()
    session.add(dr)
    session.commit()
    session.refresh(dr)
    return _build_response(dr, session)


@router.patch("/discount-requests/{request_id}/reject", response_model=DiscountRequestResponse)
async def reject_discount_request(
    request_id: int,
    body: Optional[DiscountRequestReject] = None,
    session: Session = Depends(get_session),
    current_user: User = Depends(require_role([UserRole.DIRECTOR, UserRole.SALES_MANAGER])),
):
    """Reject a discount request."""
    dr = session.get(DiscountRequest, request_id)
    if not dr:
        raise HTTPException(status_code=404, detail="Discount request not found")
    if dr.status != DiscountRequestStatus.PENDING:
        raise HTTPException(
            status_code=400,
            detail="Only pending requests can be rejected",
        )
    dr.status = DiscountRequestStatus.REJECTED
    dr.approved_by_id = current_user.id
    dr.responded_at = datetime.utcnow()
    dr.rejection_reason = (body.rejection_reason if body else None) or None
    dr.updated_at = datetime.utcnow()
    session.add(dr)
    session.commit()
    session.refresh(dr)
    return _build_response(dr, session)


@router.delete("/discount-requests/{request_id}", status_code=204)
async def delete_discount_request(
    request_id: int,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """Delete a pending/approved discount request.

    Requesters can delete their own requests.
    Approvers (DIRECTOR/SALES_MANAGER) can delete any request.
    For approved requests, remove the applied discount rows and recalculate
    quote + item totals.
    """
    dr = session.get(DiscountRequest, request_id)
    if not dr:
        raise HTTPException(status_code=404, detail="Discount request not found")
    if dr.status not in (DiscountRequestStatus.PENDING, DiscountRequestStatus.APPROVED):
        raise HTTPException(
            status_code=400,
            detail="Only pending or approved requests can be deleted",
        )
    can_approve = current_user.role in (UserRole.DIRECTOR, UserRole.SALES_MANAGER)
    if dr.requested_by_id != current_user.id and not can_approve:
        raise HTTPException(
            status_code=403,
            detail="You can only delete your own discount requests",
        )

    quote = session.get(Quote, dr.quote_id)
    if not quote:
        raise HTTPException(status_code=404, detail="Quote not found")
    if quote.status != QuoteStatus.DRAFT:
        raise HTTPException(
            status_code=400,
            detail="Discount requests can only be removed on draft quotes",
        )

    if dr.status == DiscountRequestStatus.APPROVED:
        description = f"Custom discount (Request #{dr.id})"
        applied_rows = list(
            session.exec(
                select(QuoteDiscount).where(
                    QuoteDiscount.quote_id == quote.id,
                    QuoteDiscount.template_id.is_(None),
                    QuoteDiscount.description == description,
                )
            ).all()
        )
        for row in applied_rows:
            session.delete(row)
        session.flush()

        quote_items = list(
            session.exec(
                select(QuoteItem).where(QuoteItem.quote_id == quote.id)
            ).all()
        )
        for item in quote_items:
            item_rows = list(
                session.exec(
                    select(QuoteDiscount).where(
                        QuoteDiscount.quote_id == quote.id,
                        QuoteDiscount.quote_item_id == item.id,
                    )
                ).all()
            )
            item.discount_amount = sum(d.discount_amount for d in item_rows)
            item.final_line_total = item.line_total - item.discount_amount
            if item.final_line_total < 0:
                item.final_line_total = Decimal(0)
            session.add(item)

        item_discount_total = sum(item.discount_amount for item in quote_items)
        quote_level_rows = list(
            session.exec(
                select(QuoteDiscount).where(
                    QuoteDiscount.quote_id == quote.id,
                    QuoteDiscount.quote_item_id.is_(None),
                )
            ).all()
        )
        quote_level_discount_total = sum(d.discount_amount for d in quote_level_rows)
        quote.discount_total = item_discount_total + quote_level_discount_total
        quote.total_amount = quote.subtotal - quote.discount_total
        if quote.total_amount < 0:
            quote.total_amount = Decimal(0)
        total_inc_vat = quote.total_amount * (Decimal("1") + VAT_RATE_DECIMAL)
        if quote.deposit_amount > total_inc_vat:
            quote.deposit_amount = total_inc_vat
        quote.balance_amount = total_inc_vat - quote.deposit_amount
        quote.updated_at = datetime.utcnow()
        session.add(quote)

    session.delete(dr)
    session.commit()
