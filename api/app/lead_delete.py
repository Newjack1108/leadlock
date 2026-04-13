"""Remove a lead and dependent rows (does not commit). Caller must enforce eligibility."""

from sqlmodel import Session, select

from app.models import (
    CustomerOutreachSend,
    Lead,
    MessengerMessage,
    Quote,
    Reminder,
    SmsMessage,
    StatusHistory,
)
from app.quote_delete import delete_quote_cascade


def delete_lead_cascade(session: Session, lead_id: int) -> None:
    """Delete lead-owned rows. Assumes no orders on quotes for this lead and quotes are removable."""
    for rem in session.exec(select(Reminder).where(Reminder.lead_id == lead_id)).all():
        session.delete(rem)
    session.flush()

    for cos in session.exec(
        select(CustomerOutreachSend).where(CustomerOutreachSend.lead_id == lead_id)
    ).all():
        session.delete(cos)
    session.flush()

    quotes = list(session.exec(select(Quote).where(Quote.lead_id == lead_id)).all())
    for q in quotes:
        qid = q.id
        if qid is not None:
            delete_quote_cascade(session, qid)
    session.flush()

    for sm in session.exec(select(SmsMessage).where(SmsMessage.lead_id == lead_id)).all():
        sm.lead_id = None
        session.add(sm)
    session.flush()

    for mm in session.exec(select(MessengerMessage).where(MessengerMessage.lead_id == lead_id)).all():
        mm.lead_id = None
        session.add(mm)
    session.flush()

    for sh in session.exec(select(StatusHistory).where(StatusHistory.lead_id == lead_id)).all():
        session.delete(sh)
    session.flush()

    lead = session.get(Lead, lead_id)
    if lead:
        session.delete(lead)
    session.flush()
