"""Soft-archive old terminal leads and inactive quotes (see ARCHIVE_AFTER_DAYS)."""
from datetime import datetime, timedelta

from sqlmodel import Session, select

from app.constants import ARCHIVE_AFTER_DAYS
from app.models import Lead, LeadStatus, Quote, QuoteStatus


LEAD_ARCHIVE_STATUSES = (
    LeadStatus.QUOTED,
    LeadStatus.WON,
    LeadStatus.LOST,
    LeadStatus.CLOSED,
)

QUOTE_ARCHIVE_STATUSES = (
    QuoteStatus.REJECTED,
    QuoteStatus.EXPIRED,
    QuoteStatus.ACCEPTED,
)


def apply_auto_archive(session: Session) -> dict:
    """Set archived_at for eligible rows where archived_at is still null."""
    cutoff = datetime.utcnow() - timedelta(days=ARCHIVE_AFTER_DAYS)
    now = datetime.utcnow()
    leads_archived = 0
    for lead in session.exec(
        select(Lead).where(
            Lead.archived_at.is_(None),
            Lead.status.in_(LEAD_ARCHIVE_STATUSES),
            Lead.updated_at < cutoff,
        )
    ).all():
        lead.archived_at = now
        session.add(lead)
        leads_archived += 1

    quotes_archived = 0
    for quote in session.exec(
        select(Quote).where(
            Quote.archived_at.is_(None),
            Quote.status.in_(QUOTE_ARCHIVE_STATUSES),
            Quote.updated_at < cutoff,
        )
    ).all():
        quote.archived_at = now
        session.add(quote)
        quotes_archived += 1

    if leads_archived or quotes_archived:
        session.commit()
    return {"leads_archived": leads_archived, "quotes_archived": quotes_archived}
