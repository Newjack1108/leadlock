"""Remove a lead and dependent rows (does not commit). Caller must enforce eligibility."""

from typing import Optional

from sqlalchemy import or_
from sqlmodel import Session, select

from app.customer_file_service import delete_customer_file_from_cloudinary
from app.scheduled_email_service import delete_stored_attachments
from app.models import (
    Activity,
    Customer,
    CustomerFile,
    CustomerOutreachSend,
    Email,
    Lead,
    LeadStatus,
    MessengerMessage,
    Order,
    Quote,
    QuoteStatus,
    Reminder,
    ScheduledEmail,
    ScheduledSms,
    SmsMessage,
    StatusHistory,
    WebsiteVisit,
)
from app.order_delete import delete_order_cascade
from app.quote_delete import delete_quote_cascade

PRE_QUALIFY_SPAM_STATUSES = frozenset(
    {
        LeadStatus.NEW,
        LeadStatus.CONTACT_ATTEMPTED,
        LeadStatus.ENGAGED,
    }
)


def is_pre_qualify_spam_status(status: LeadStatus) -> bool:
    return status in PRE_QUALIFY_SPAM_STATUSES


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


def maybe_delete_orphan_customer_after_spam_lead(
    session: Session, customer_id: Optional[int]
) -> None:
    """Remove outreach-linked customer stub when no other leads or real deal history remain."""
    if customer_id is None:
        return

    if session.exec(select(Lead).where(Lead.customer_id == customer_id)).first():
        return

    quotes = list(session.exec(select(Quote).where(Quote.customer_id == customer_id)).all())
    quote_ids = [q.id for q in quotes if q.id is not None]

    for q in quotes:
        if q.status != QuoteStatus.DRAFT:
            return
        if q.id is not None:
            if session.exec(select(Order).where(Order.quote_id == q.id)).first():
                return

    order_conditions = [Order.customer_id == customer_id]
    if quote_ids:
        order_conditions.append(Order.quote_id.in_(quote_ids))
    if session.exec(select(Order).where(or_(*order_conditions))).first():
        return

    reminder_conditions = [Reminder.customer_id == customer_id]
    if quote_ids:
        reminder_conditions.append(Reminder.quote_id.in_(quote_ids))
    for rem in session.exec(select(Reminder).where(or_(*reminder_conditions))).all():
        session.delete(rem)
    session.flush()

    for ss in session.exec(select(ScheduledSms).where(ScheduledSms.customer_id == customer_id)).all():
        session.delete(ss)
    session.flush()

    for se in session.exec(select(ScheduledEmail).where(ScheduledEmail.customer_id == customer_id)).all():
        delete_stored_attachments(se.attachments)
        session.delete(se)
    session.flush()

    for cos in session.exec(
        select(CustomerOutreachSend).where(CustomerOutreachSend.customer_id == customer_id)
    ).all():
        session.delete(cos)
    session.flush()

    seen_orders: set[int] = set()
    for order in session.exec(select(Order).where(or_(*order_conditions))).all():
        oid = order.id
        if oid is None or oid in seen_orders:
            continue
        seen_orders.add(oid)
        delete_order_cascade(session, oid)
    session.flush()

    for qid in quote_ids:
        delete_quote_cascade(session, qid)
    session.flush()

    for em in session.exec(select(Email).where(Email.customer_id == customer_id)).all():
        session.delete(em)
    for sm in session.exec(select(SmsMessage).where(SmsMessage.customer_id == customer_id)).all():
        session.delete(sm)
    for mm in session.exec(select(MessengerMessage).where(MessengerMessage.customer_id == customer_id)).all():
        session.delete(mm)
    for act in session.exec(select(Activity).where(Activity.customer_id == customer_id)).all():
        session.delete(act)
    for wv in session.exec(select(WebsiteVisit).where(WebsiteVisit.customer_id == customer_id)).all():
        session.delete(wv)
    session.flush()

    for cf in session.exec(select(CustomerFile).where(CustomerFile.customer_id == customer_id)).all():
        delete_customer_file_from_cloudinary(cf.cloudinary_public_id, cf.cloudinary_resource_type)
        session.delete(cf)
    session.flush()

    customer = session.get(Customer, customer_id)
    if customer:
        session.delete(customer)
    session.flush()
