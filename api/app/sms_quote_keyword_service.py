"""
Apply exact SMS keywords HOLD / CLOSE to a customer's open quotes.
"""
import string
from datetime import datetime
from typing import Optional

from sqlmodel import Session, select

from app.models import (
    LeadStatus,
    LossCategory,
    OpportunityStage,
    Quote,
    QuoteStatus,
)


QUOTE_KEYWORD_OPEN_STATUSES = (QuoteStatus.SENT, QuoteStatus.VIEWED)
CLOSE_LOSS_REASON = "Customer replied CLOSE via SMS"


def normalize_quote_keyword_body(body: str) -> str:
    """Trim, casefold, and strip leading/trailing punctuation for exact keyword match."""
    text = (body or "").strip().casefold()
    return text.strip(string.punctuation + string.whitespace)


def detect_quote_keyword(body: str) -> Optional[str]:
    """Return 'hold', 'close', or None for an exact whole-message keyword."""
    text = normalize_quote_keyword_body(body)
    if text == "hold":
        return "hold"
    if text == "close":
        return "close"
    return None


def _open_quotes_for_customer(session: Session, customer_id: int) -> list[Quote]:
    stmt = (
        select(Quote)
        .where(Quote.customer_id == customer_id)
        .where(Quote.status.in_(QUOTE_KEYWORD_OPEN_STATUSES))
    )
    return list(session.exec(stmt).all())


def apply_sms_quote_keyword(session: Session, customer_id: int, body: str) -> Optional[str]:
    """
    If body is exact HOLD or CLOSE, update open SENT/VIEWED quotes for the customer.

    HOLD: set on_hold_at (leave existing timestamp if already set).
    CLOSE: mark REJECTED/LOST and transition linked QUOTED leads to LOST.

    Returns 'hold', 'close', or None if the body is not a keyword (or no work needed for
    keyword detection — still returns the keyword when matched even if no open quotes).
    """
    keyword = detect_quote_keyword(body)
    if not keyword:
        return None

    quotes = _open_quotes_for_customer(session, customer_id)
    now = datetime.utcnow()

    if keyword == "hold":
        for quote in quotes:
            if quote.on_hold_at is None:
                quote.on_hold_at = now
                quote.updated_at = now
                session.add(quote)
        session.commit()
        return "hold"

    # CLOSE — same semantics as staff mark_opportunity_lost
    any_newly_rejected = False
    for quote in quotes:
        old_status = quote.status
        quote.status = QuoteStatus.REJECTED
        quote.opportunity_stage = OpportunityStage.LOST
        quote.loss_reason = CLOSE_LOSS_REASON
        quote.loss_category = LossCategory.OTHER
        quote.updated_at = now
        session.add(quote)
        if old_status != QuoteStatus.REJECTED:
            any_newly_rejected = True

    session.commit()

    if any_newly_rejected:
        from app.system_user_service import get_system_user_id
        from app.workflow import auto_transition_lead_status, find_leads_by_customer_id

        try:
            actor_id = get_system_user_id(session)
        except Exception:
            actor_id = None

        if actor_id is not None:
            leads = find_leads_by_customer_id(customer_id, session)
            for lead in leads:
                if lead.status == LeadStatus.QUOTED:
                    auto_transition_lead_status(
                        lead.id,
                        LeadStatus.LOST,
                        session,
                        actor_id,
                        "Automatic transition: Customer replied CLOSE via SMS",
                    )

    return "close"
