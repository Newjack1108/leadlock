"""Discount template expiry and max_uses (redemptions on quote accept)."""
from datetime import datetime
from typing import Collection, List

from fastapi import HTTPException
from sqlmodel import Session, select, func

from app.models import (
    DiscountTemplate,
    DiscountTemplateRedemption,
    QuoteDiscount,
)


def _utcnow() -> datetime:
    return datetime.utcnow()


def assert_templates_not_expired_for_apply(session: Session, template_ids: Collection[int]) -> None:
    """Reject applying templates whose expires_at is in the past."""
    ids = [tid for tid in template_ids if tid is not None]
    if not ids:
        return
    now = _utcnow()
    for tid in set(ids):
        t = session.get(DiscountTemplate, tid)
        if not t:
            raise HTTPException(status_code=400, detail=f"Discount template {tid} not found")
        if t.expires_at is not None and t.expires_at < now:
            raise HTTPException(
                status_code=400,
                detail=f"Discount \"{t.name}\" has expired and cannot be applied",
            )


def validate_and_record_redemptions_on_accept(session: Session, quote_id: int) -> None:
    """
    When a quote becomes ACCEPTED: enforce expiry and max_uses; insert redemption rows.
    One redemption per (template_id, quote_id) even if multiple QuoteDiscount lines share the template.
    """
    statement = (
        select(QuoteDiscount.template_id)
        .where(QuoteDiscount.quote_id == quote_id, QuoteDiscount.template_id.isnot(None))
        .distinct()
    )
    template_ids: List[int] = [row[0] for row in session.exec(statement).all()]
    if not template_ids:
        return

    now = _utcnow()

    for tid in template_ids:
        template = session.get(DiscountTemplate, tid)
        if not template:
            raise HTTPException(status_code=400, detail=f"Discount template {tid} not found")

        if template.expires_at is not None and template.expires_at < now:
            raise HTTPException(
                status_code=400,
                detail=f"Cannot accept: discount \"{template.name}\" has expired",
            )

        if template.max_uses is not None:
            count_stmt = select(func.count(DiscountTemplateRedemption.id)).where(
                DiscountTemplateRedemption.template_id == tid
            )
            current = session.exec(count_stmt).one()
            existing_for_quote = session.exec(
                select(DiscountTemplateRedemption).where(
                    DiscountTemplateRedemption.template_id == tid,
                    DiscountTemplateRedemption.quote_id == quote_id,
                )
            ).first()
            if existing_for_quote is None and current >= template.max_uses:
                raise HTTPException(
                    status_code=400,
                    detail=f"Cannot accept: discount \"{template.name}\" has reached its maximum number of uses",
                )

    for tid in template_ids:
        existing = session.exec(
            select(DiscountTemplateRedemption).where(
                DiscountTemplateRedemption.template_id == tid,
                DiscountTemplateRedemption.quote_id == quote_id,
            )
        ).first()
        if existing is None:
            session.add(
                DiscountTemplateRedemption(
                    template_id=tid,
                    quote_id=quote_id,
                    created_at=now,
                )
            )


def redemption_counts_by_template(session: Session) -> dict[int, int]:
    """Map template_id -> number of acceptances recorded."""
    rows = session.exec(
        select(DiscountTemplateRedemption.template_id, func.count(DiscountTemplateRedemption.id)).group_by(
            DiscountTemplateRedemption.template_id
        )
    ).all()
    return {int(tid): int(c) for tid, c in rows}
