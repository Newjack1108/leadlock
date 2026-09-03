"""Staff API for monthly review prize draw."""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session

from app.auth import require_role
from app.database import get_session
from app.models import (
    Order,
    ReviewPrizeDrawEntry,
    ReviewPrizeDrawEntryStatus,
    ReviewPrizeDrawWinner,
    User,
    UserRole,
)
from app.review_prize_draw_service import (
    add_manual_entries,
    approve_entry,
    delete_manual_entry,
    entry_display_name,
    get_winner_for_month,
    is_manual_entry,
    list_entries,
    pick_random_winner,
    reject_entry,
    reset_winner_for_month,
    send_congratulations_to_winner,
)
from app.schemas import (
    ReviewPrizeDrawAddManualRequest,
    ReviewPrizeDrawDeleteEntryResponse,
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
    order = session.get(Order, entry.order_id) if entry.order_id else None
    reviewed_by_name = None
    if entry.reviewed_by_id:
        reviewer = session.get(User, entry.reviewed_by_id)
        reviewed_by_name = reviewer.full_name if reviewer else None
    return ReviewPrizeDrawEntryListItem(
        id=entry.id,
        order_id=entry.order_id,
        order_number=order.order_number if order else "",
        customer_id=entry.customer_id,
        customer_name=entry_display_name(entry, session),
        platforms_claimed=entry.platforms_claimed or [],
        status=entry.status.value if entry.status else "",
        submitted_at=entry.submitted_at,
        entry_month=entry.entry_month,
        rejection_note=entry.rejection_note,
        reviewed_at=entry.reviewed_at,
        reviewed_by_name=reviewed_by_name,
        is_manual=is_manual_entry(entry),
    )


def _winner_to_response(winner: ReviewPrizeDrawWinner, session: Session) -> ReviewPrizeDrawWinnerResponse:
    entry = session.get(ReviewPrizeDrawEntry, winner.entry_id)
    order = session.get(Order, entry.order_id) if entry and entry.order_id else None
    picker = session.get(User, winner.picked_by_id)
    sent_by_name = None
    if winner.congratulations_sent_by_id:
        sent_by = session.get(User, winner.congratulations_sent_by_id)
        sent_by_name = sent_by.full_name if sent_by else None
    return ReviewPrizeDrawWinnerResponse(
        month=winner.month,
        entry_id=winner.entry_id,
        order_id=entry.order_id if entry else None,
        order_number=order.order_number if order else "",
        customer_id=entry.customer_id if entry else None,
        customer_name=entry_display_name(entry, session) if entry else "",
        platforms_claimed=entry.platforms_claimed or [] if entry else [],
        is_manual=is_manual_entry(entry) if entry else False,
        picked_at=winner.picked_at,
        picked_by_id=winner.picked_by_id,
        picked_by_name=picker.full_name if picker else None,
        congratulations_sent_at=winner.congratulations_sent_at,
        congratulations_channel=winner.congratulations_channel,
        congratulations_sent_by_name=sent_by_name,
    )


@router.get("/entries", response_model=ReviewPrizeDrawEntriesResponse)
async def get_prize_draw_entries(
    month: Optional[str] = Query(None, description="YYYY-MM filter for month entered (submitted_at)"),
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
    entries = list_entries(session, submitted_month=month, status=status_enum)
    approved_count = (
        len(
            list_entries(
                session,
                entry_month=month,
                status=ReviewPrizeDrawEntryStatus.APPROVED,
            )
        )
        if month
        else len(list_entries(session, status=ReviewPrizeDrawEntryStatus.APPROVED))
    )
    return ReviewPrizeDrawEntriesResponse(
        entries=[_entry_to_list_item(e, session) for e in entries],
        approved_count=approved_count,
    )


@router.post("/entries/manual", response_model=ReviewPrizeDrawEntriesResponse)
async def add_manual_prize_draw_entries(
    body: ReviewPrizeDrawAddManualRequest,
    session: Session = Depends(get_session),
    current_user: User = Depends(require_role([UserRole.DIRECTOR])),
):
    created, err = add_manual_entries(body.names, body.month, current_user, session)
    if err or created is None:
        raise HTTPException(status_code=400, detail=err or "Could not add names")
    session.commit()
    for entry in created:
        session.refresh(entry)
    pool_month = created[0].entry_month if created else body.month
    approved_count = len(
        list_entries(
            session,
            entry_month=pool_month,
            status=ReviewPrizeDrawEntryStatus.APPROVED,
        )
    )
    return ReviewPrizeDrawEntriesResponse(
        entries=[_entry_to_list_item(e, session) for e in created],
        approved_count=approved_count,
    )


@router.delete("/entries/{entry_id}", response_model=ReviewPrizeDrawDeleteEntryResponse)
async def delete_manual_prize_draw_entry(
    entry_id: int,
    session: Session = Depends(get_session),
    current_user: User = Depends(require_role([UserRole.DIRECTOR])),
):
    success, err = delete_manual_entry(entry_id, session)
    if not success:
        raise HTTPException(status_code=400, detail=err)
    session.commit()
    return ReviewPrizeDrawDeleteEntryResponse(success=True)


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
