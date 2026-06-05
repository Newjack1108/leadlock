"""Staff API for monthly review prize draw."""
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session, select

from app.auth import get_current_user, require_role
from app.database import get_session
from app.models import (
    Customer,
    Order,
    ReviewPrizeDrawEntry,
    ReviewPrizeDrawEntryStatus,
    ReviewPrizeDrawWinner,
    User,
    UserRole,
)
from app.review_prize_draw_service import (
    approve_entry,
    get_winner_for_month,
    list_entries,
    pick_random_winner,
    reject_entry,
    reset_winner_for_month,
    send_congratulations_to_winner,
)
from app.schemas import (
    ReviewPrizeDrawEntriesResponse,
    ReviewPrizeDrawEntryListItem,
    ReviewPrizeDrawPickWinnerRequest,
    ReviewPrizeDrawRejectRequest,
    ReviewPrizeDrawResetWinnerResponse,
    ReviewPrizeDrawSendCongratulationsRequest,
    ReviewPrizeDrawWinnerResponse,
)

router = APIRouter(prefix="/api/review-prize-draw", tags=["review-prize-draw"])


def _entry_to_list_item(entry: ReviewPrizeDrawEntry, session: Session) -> ReviewPrizeDrawEntryListItem:
    order = session.get(Order, entry.order_id)
    customer = session.get(Customer, entry.customer_id)
    reviewed_by_name = None
    if entry.reviewed_by_id:
        reviewer = session.get(User, entry.reviewed_by_id)
        reviewed_by_name = reviewer.full_name if reviewer else None
    return ReviewPrizeDrawEntryListItem(
        id=entry.id,
        order_id=entry.order_id,
        order_number=order.order_number if order else "",
        customer_id=entry.customer_id,
        customer_name=customer.name if customer else "",
        platforms_claimed=entry.platforms_claimed or [],
        status=entry.status.value if entry.status else "",
        submitted_at=entry.submitted_at,
        entry_month=entry.entry_month,
        rejection_note=entry.rejection_note,
        reviewed_at=entry.reviewed_at,
        reviewed_by_name=reviewed_by_name,
    )


def _winner_to_response(winner: ReviewPrizeDrawWinner, session: Session) -> ReviewPrizeDrawWinnerResponse:
    entry = session.get(ReviewPrizeDrawEntry, winner.entry_id)
    order = session.get(Order, entry.order_id) if entry else None
    customer = session.get(Customer, entry.customer_id) if entry else None
    picker = session.get(User, winner.picked_by_id)
    sent_by_name = None
    if winner.congratulations_sent_by_id:
        sent_by = session.get(User, winner.congratulations_sent_by_id)
        sent_by_name = sent_by.full_name if sent_by else None
    return ReviewPrizeDrawWinnerResponse(
        month=winner.month,
        entry_id=winner.entry_id,
        order_id=entry.order_id if entry else 0,
        order_number=order.order_number if order else "",
        customer_id=entry.customer_id if entry else 0,
        customer_name=customer.name if customer else "",
        platforms_claimed=entry.platforms_claimed or [] if entry else [],
        picked_at=winner.picked_at,
        picked_by_id=winner.picked_by_id,
        picked_by_name=picker.full_name if picker else None,
        congratulations_sent_at=winner.congratulations_sent_at,
        congratulations_channel=winner.congratulations_channel,
        congratulations_sent_by_name=sent_by_name,
    )


@router.get("/entries", response_model=ReviewPrizeDrawEntriesResponse)
async def get_prize_draw_entries(
    month: Optional[str] = Query(None, description="YYYY-MM filter for approved entry_month"),
    status: Optional[str] = Query(None, description="PENDING, APPROVED, or REJECTED"),
    session: Session = Depends(get_session),
    current_user: User = Depends(require_role([UserRole.DIRECTOR])),
):
    status_enum = None
    if status:
        try:
            status_enum = ReviewPrizeDrawEntryStatus(status.upper())
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid status")
    filter_month = month if status_enum == ReviewPrizeDrawEntryStatus.APPROVED else None
    entries = list_entries(session, month=filter_month, status=status_enum)
    approved_count = (
        len(list_entries(session, month=month, status=ReviewPrizeDrawEntryStatus.APPROVED))
        if month
        else len(list_entries(session, status=ReviewPrizeDrawEntryStatus.APPROVED))
    )
    return ReviewPrizeDrawEntriesResponse(
        entries=[_entry_to_list_item(e, session) for e in entries],
        approved_count=approved_count,
    )


@router.post("/entries/{entry_id}/approve", response_model=ReviewPrizeDrawEntryListItem)
async def approve_prize_draw_entry(
    entry_id: int,
    session: Session = Depends(get_session),
    current_user: User = Depends(require_role([UserRole.DIRECTOR])),
):
    entry, err = approve_entry(entry_id, current_user, session)
    if err:
        raise HTTPException(status_code=400, detail=err)
    session.commit()
    session.refresh(entry)
    return _entry_to_list_item(entry, session)


@router.post("/entries/{entry_id}/reject", response_model=ReviewPrizeDrawEntryListItem)
async def reject_prize_draw_entry(
    entry_id: int,
    body: ReviewPrizeDrawRejectRequest,
    session: Session = Depends(get_session),
    current_user: User = Depends(require_role([UserRole.DIRECTOR])),
):
    entry, err = reject_entry(entry_id, current_user, session, note=body.note)
    if err:
        raise HTTPException(status_code=400, detail=err)
    session.commit()
    session.refresh(entry)
    return _entry_to_list_item(entry, session)


@router.get("/winners", response_model=Optional[ReviewPrizeDrawWinnerResponse])
async def get_prize_draw_winner(
    month: str = Query(..., description="YYYY-MM"),
    session: Session = Depends(get_session),
    current_user: User = Depends(require_role([UserRole.DIRECTOR])),
):
    winner = get_winner_for_month(session, month)
    if not winner:
        return None
    return _winner_to_response(winner, session)


@router.post("/pick-winner", response_model=ReviewPrizeDrawWinnerResponse)
async def pick_prize_draw_winner(
    body: ReviewPrizeDrawPickWinnerRequest,
    session: Session = Depends(get_session),
    current_user: User = Depends(require_role([UserRole.DIRECTOR])),
):
    winner, err = pick_random_winner(body.month, current_user, session)
    if err:
        raise HTTPException(status_code=400, detail=err)
    session.commit()
    session.refresh(winner)
    return _winner_to_response(winner, session)


@router.post("/reset-winner", response_model=ReviewPrizeDrawResetWinnerResponse)
async def reset_prize_draw_winner(
    body: ReviewPrizeDrawPickWinnerRequest,
    session: Session = Depends(get_session),
    current_user: User = Depends(require_role([UserRole.DIRECTOR])),
):
    success, err = reset_winner_for_month(body.month, current_user, session)
    if not success:
        raise HTTPException(status_code=400, detail=err)
    session.commit()
    return ReviewPrizeDrawResetWinnerResponse(success=True, month=body.month)


@router.post("/send-congratulations", response_model=ReviewPrizeDrawWinnerResponse)
async def send_prize_draw_congratulations(
    body: ReviewPrizeDrawSendCongratulationsRequest,
    session: Session = Depends(get_session),
    current_user: User = Depends(require_role([UserRole.DIRECTOR])),
):
    channel = (body.channel or "").strip().lower()
    if channel not in ("email", "sms"):
        raise HTTPException(status_code=400, detail="channel must be 'email' or 'sms'")

    winner, err = send_congratulations_to_winner(
        body.month,
        current_user,
        session,
        channel=channel,
        force=body.force,
    )
    if err:
        raise HTTPException(status_code=400, detail=err)
    session.commit()
    session.refresh(winner)
    return _winner_to_response(winner, session)
