"""
Monthly review prize draw: customer self-declaration with staff approval.
"""
from __future__ import annotations

import os
import random
import secrets
from datetime import datetime
from typing import List, Optional, Tuple

from sqlmodel import Session, select, and_

from app.models import (
    CompanySettings,
    Customer,
    Order,
    ReviewPrizeDrawEntry,
    ReviewPrizeDrawEntryStatus,
    ReviewPrizeDrawPlatform,
    ReviewPrizeDrawWinner,
    User,
)
from app.order_audit import record_order_audit_event
from app.schemas import CustomerHistoryEventType

PLATFORM_LABELS = {
    ReviewPrizeDrawPlatform.GOOGLE.value: "Google",
    ReviewPrizeDrawPlatform.FACEBOOK.value: "Facebook",
    ReviewPrizeDrawPlatform.TRUSTPILOT.value: "Trustpilot",
}


def _get_company_settings(session: Session) -> Optional[CompanySettings]:
    return session.exec(select(CompanySettings).limit(1)).first()


def is_prize_draw_enabled(settings: Optional[CompanySettings]) -> bool:
    return bool(settings and settings.review_prize_draw_enabled)


def build_prize_draw_url(token: str) -> str:
    frontend = (os.getenv("FRONTEND_URL") or os.getenv("PUBLIC_FRONTEND_URL") or "").strip()
    if not frontend or not (frontend.startswith("http://") or frontend.startswith("https://")):
        frontend = "https://leadlock-frontend-production.up.railway.app"
    base = frontend.rstrip("/")
    return f"{base}/review-prize/{token}"


def get_entry_for_order(session: Session, order_id: int) -> Optional[ReviewPrizeDrawEntry]:
    return session.exec(
        select(ReviewPrizeDrawEntry)
        .where(ReviewPrizeDrawEntry.order_id == order_id)
        .order_by(ReviewPrizeDrawEntry.created_at.desc())
        .limit(1)
    ).first()


def get_entry_by_token(session: Session, token: str) -> Optional[ReviewPrizeDrawEntry]:
    return session.exec(
        select(ReviewPrizeDrawEntry).where(ReviewPrizeDrawEntry.access_token == token)
    ).first()


def configured_platforms(settings: Optional[CompanySettings]) -> List[Tuple[str, str]]:
    """Return (code, label) for platforms with URLs configured."""
    if not settings:
        return []
    platforms: List[Tuple[str, str]] = []
    if settings.review_google_url:
        platforms.append((ReviewPrizeDrawPlatform.GOOGLE.value, PLATFORM_LABELS[ReviewPrizeDrawPlatform.GOOGLE.value]))
    if settings.review_facebook_url:
        platforms.append((ReviewPrizeDrawPlatform.FACEBOOK.value, PLATFORM_LABELS[ReviewPrizeDrawPlatform.FACEBOOK.value]))
    if settings.review_trustpilot_url:
        platforms.append(
            (ReviewPrizeDrawPlatform.TRUSTPILOT.value, PLATFORM_LABELS[ReviewPrizeDrawPlatform.TRUSTPILOT.value])
        )
    return platforms


def ensure_prize_draw_entry(order: Order, session: Session) -> Optional[ReviewPrizeDrawEntry]:
    """Mint a prize draw token for an order when prize draw is enabled."""
    if not order.id or not order.customer_id:
        return None
    settings = _get_company_settings(session)
    if not is_prize_draw_enabled(settings):
        return None

    existing = get_entry_for_order(session, order.id)
    if existing:
        return existing

    entry = ReviewPrizeDrawEntry(
        order_id=order.id,
        customer_id=order.customer_id,
        access_token=secrets.token_urlsafe(32),
        status=ReviewPrizeDrawEntryStatus.PENDING,
    )
    session.add(entry)
    session.flush()
    return entry


def _validate_platforms(
    platforms: List[str],
    settings: CompanySettings,
) -> Tuple[bool, Optional[str]]:
    allowed = {code for code, _ in configured_platforms(settings)}
    if not allowed:
        return False, "No review platforms configured"
    normalized = []
    for p in platforms:
        code = (p or "").strip().upper()
        if code not in allowed:
            return False, f"Invalid platform: {p}"
        if code not in normalized:
            normalized.append(code)
    min_required = max(1, int(settings.review_prize_draw_min_platforms or 2))
    if len(normalized) < min_required:
        return False, f"Select at least {min_required} platforms"
    return True, None


def submit_prize_draw_entry(
    token: str,
    platforms: List[str],
    session: Session,
) -> Tuple[Optional[ReviewPrizeDrawEntry], Optional[str]]:
    entry = get_entry_by_token(session, token)
    if not entry:
        return None, "Prize draw entry not found"

    if entry.status == ReviewPrizeDrawEntryStatus.APPROVED:
        return None, "Entry already approved"
    if entry.status == ReviewPrizeDrawEntryStatus.PENDING and entry.submitted_at:
        return None, "Entry already submitted and awaiting approval"

    settings = _get_company_settings(session)
    if not settings or not is_prize_draw_enabled(settings):
        return None, "Prize draw is not enabled"

    ok, err = _validate_platforms(platforms, settings)
    if not ok:
        return None, err

    normalized = []
    for p in platforms:
        code = p.strip().upper()
        if code not in normalized:
            normalized.append(code)

    now = datetime.utcnow()
    entry.platforms_claimed = normalized
    entry.status = ReviewPrizeDrawEntryStatus.PENDING
    entry.submitted_at = now
    entry.reviewed_at = None
    entry.reviewed_by_id = None
    entry.rejection_note = None
    entry.entry_month = None
    session.add(entry)

    order = session.get(Order, entry.order_id)
    if order:
        record_order_audit_event(
            session,
            event_type=CustomerHistoryEventType.REVIEW_PRIZE_DRAW_SUBMITTED.value,
            title="Review Prize Draw Submitted",
            description=f"Customer submitted prize draw entry for order {order.order_number}",
            order=order,
            metadata={"platforms": normalized},
        )
    return entry, None


def approve_entry(entry_id: int, user: User, session: Session) -> Tuple[Optional[ReviewPrizeDrawEntry], Optional[str]]:
    entry = session.get(ReviewPrizeDrawEntry, entry_id)
    if not entry:
        return None, "Entry not found"
    if entry.status != ReviewPrizeDrawEntryStatus.PENDING or not entry.submitted_at:
        return None, "Only pending submitted entries can be approved"

    now = datetime.utcnow()
    entry.status = ReviewPrizeDrawEntryStatus.APPROVED
    entry.reviewed_at = now
    entry.reviewed_by_id = user.id
    entry.rejection_note = None
    entry.entry_month = now.strftime("%Y-%m")
    session.add(entry)

    order = session.get(Order, entry.order_id)
    if order:
        record_order_audit_event(
            session,
            event_type=CustomerHistoryEventType.REVIEW_PRIZE_DRAW_APPROVED.value,
            title="Review Prize Draw Approved",
            description=f"Prize draw entry approved for order {order.order_number}",
            order=order,
            metadata={"platforms": entry.platforms_claimed, "entry_month": entry.entry_month},
            created_by_id=user.id,
        )
    return entry, None


def reject_entry(
    entry_id: int,
    user: User,
    session: Session,
    *,
    note: Optional[str] = None,
) -> Tuple[Optional[ReviewPrizeDrawEntry], Optional[str]]:
    entry = session.get(ReviewPrizeDrawEntry, entry_id)
    if not entry:
        return None, "Entry not found"
    if entry.status != ReviewPrizeDrawEntryStatus.PENDING or not entry.submitted_at:
        return None, "Only pending submitted entries can be rejected"

    now = datetime.utcnow()
    entry.status = ReviewPrizeDrawEntryStatus.REJECTED
    entry.reviewed_at = now
    entry.reviewed_by_id = user.id
    entry.rejection_note = (note or "").strip() or None
    entry.entry_month = None
    session.add(entry)

    order = session.get(Order, entry.order_id)
    if order:
        record_order_audit_event(
            session,
            event_type=CustomerHistoryEventType.REVIEW_PRIZE_DRAW_REJECTED.value,
            title="Review Prize Draw Rejected",
            description=f"Prize draw entry rejected for order {order.order_number}",
            order=order,
            metadata={"platforms": entry.platforms_claimed, "note": entry.rejection_note},
            created_by_id=user.id,
        )
    return entry, None


def list_entries(
    session: Session,
    *,
    month: Optional[str] = None,
    status: Optional[ReviewPrizeDrawEntryStatus] = None,
) -> List[ReviewPrizeDrawEntry]:
    statement = select(ReviewPrizeDrawEntry).order_by(ReviewPrizeDrawEntry.submitted_at.desc())
    if month:
        statement = statement.where(ReviewPrizeDrawEntry.entry_month == month)
    if status:
        statement = statement.where(ReviewPrizeDrawEntry.status == status)
    return list(session.exec(statement).all())


def get_winner_for_month(session: Session, month: str) -> Optional[ReviewPrizeDrawWinner]:
    return session.exec(
        select(ReviewPrizeDrawWinner).where(ReviewPrizeDrawWinner.month == month)
    ).first()


def pick_random_winner(
    month: str,
    user: User,
    session: Session,
) -> Tuple[Optional[ReviewPrizeDrawWinner], Optional[str]]:
    existing = get_winner_for_month(session, month)
    if existing:
        return existing, None

    approved = list(
        session.exec(
            select(ReviewPrizeDrawEntry).where(
                and_(
                    ReviewPrizeDrawEntry.status == ReviewPrizeDrawEntryStatus.APPROVED,
                    ReviewPrizeDrawEntry.entry_month == month,
                )
            )
        ).all()
    )
    if not approved:
        return None, "No approved entries for this month"

    winner_entry = random.choice(approved)
    now = datetime.utcnow()
    winner = ReviewPrizeDrawWinner(
        month=month,
        entry_id=winner_entry.id,
        picked_at=now,
        picked_by_id=user.id,
    )
    session.add(winner)
    session.flush()

    order = session.get(Order, winner_entry.order_id)
    customer = session.get(Customer, winner_entry.customer_id)
    if order:
        record_order_audit_event(
            session,
            event_type=CustomerHistoryEventType.REVIEW_PRIZE_DRAW_WINNER.value,
            title="Review Prize Draw Winner",
            description=(
                f"{customer.name if customer else 'Customer'} won the {month} review prize draw "
                f"for order {order.order_number}"
            ),
            order=order,
            metadata={"month": month, "entry_id": winner_entry.id},
            created_by_id=user.id,
        )
    return winner, None


def build_prize_draw_entry_response(
    entry: Optional[ReviewPrizeDrawEntry],
) -> Optional[dict]:
    if not entry:
        return None
    return {
        "id": entry.id,
        "status": entry.status.value if entry.status else None,
        "prize_draw_url": build_prize_draw_url(entry.access_token),
        "platforms_claimed": entry.platforms_claimed or [],
        "submitted_at": entry.submitted_at,
        "entry_month": entry.entry_month,
        "rejection_note": entry.rejection_note,
    }
