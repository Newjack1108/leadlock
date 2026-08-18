"""Move a lead (and records owned by that lead) onto a different customer."""
from datetime import datetime

from sqlmodel import Session, select

from app.models import (
    Activity,
    ActivityType,
    ConfiguratorInvite,
    Customer,
    CustomerFile,
    Lead,
    Order,
    Quote,
    Reminder,
    WeeklyPlanItem,
)


def create_customer_from_lead_unmatched(session: Session, lead: Lead) -> Customer:
    """Always mint a new customer from the lead. Does not match existing records."""
    from app.routers.leads import generate_customer_number

    customer = Customer(
        customer_number=generate_customer_number(session),
        name=lead.name,
        email=lead.email,
        wrong_email_address=bool(getattr(lead, "wrong_email_address", False)),
        phone=lead.phone,
        postcode=lead.postcode,
        customer_since=datetime.utcnow(),
    )
    session.add(customer)
    session.flush()
    session.refresh(customer)
    return customer


def reassign_lead_owned_records(
    session: Session,
    lead: Lead,
    new_customer: Customer,
    *,
    actor_id: int,
) -> None:
    """Point this lead and its quotes/orders/invites/reminders at ``new_customer``."""
    if not new_customer.id:
        raise ValueError("new_customer must be persisted")

    old_customer_id = lead.customer_id
    old_customer = session.get(Customer, old_customer_id) if old_customer_id else None
    if old_customer_id == new_customer.id:
        return

    lead.customer_id = new_customer.id
    lead.updated_at = datetime.utcnow()
    session.add(lead)

    quotes = list(session.exec(select(Quote).where(Quote.lead_id == lead.id)).all())
    quote_ids = [q.id for q in quotes if q.id is not None]
    for quote in quotes:
        quote.customer_id = new_customer.id
        quote.updated_at = datetime.utcnow()
        session.add(quote)

    if quote_ids:
        for order in session.exec(select(Order).where(Order.quote_id.in_(quote_ids))).all():
            order.customer_id = new_customer.id
            session.add(order)
        for customer_file in session.exec(
            select(CustomerFile).where(CustomerFile.quote_id.in_(quote_ids))
        ).all():
            customer_file.customer_id = new_customer.id
            session.add(customer_file)

    for invite in session.exec(
        select(ConfiguratorInvite).where(ConfiguratorInvite.lead_id == lead.id)
    ).all():
        invite.customer_id = new_customer.id
        invite.updated_at = datetime.utcnow()
        session.add(invite)

    for reminder in session.exec(select(Reminder).where(Reminder.lead_id == lead.id)).all():
        reminder.customer_id = new_customer.id
        session.add(reminder)

    for item in session.exec(select(WeeklyPlanItem).where(WeeklyPlanItem.lead_id == lead.id)).all():
        item.customer_id = new_customer.id
        item.updated_at = datetime.utcnow()
        session.add(item)

    old_label = (
        old_customer.customer_number
        if old_customer is not None
        else (f"#{old_customer_id}" if old_customer_id else "no customer")
    )
    new_label = new_customer.customer_number
    note = (
        f"Lead #{lead.id} unlinked from {old_label} and linked to {new_label} "
        f"({lead.name})."
    )
    if old_customer_id:
        session.add(
            Activity(
                customer_id=old_customer_id,
                activity_type=ActivityType.NOTE,
                notes=note,
                created_by_id=actor_id,
            )
        )
    session.add(
        Activity(
            customer_id=new_customer.id,
            activity_type=ActivityType.NOTE,
            notes=note,
            created_by_id=actor_id,
        )
    )
