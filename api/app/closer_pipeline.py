"""Shared SQL helpers for closer-visible lead/customer scope."""
from sqlmodel import select

from app.models import Lead, LeadStatus

CLOSER_PIPELINE_STATUSES = (
    LeadStatus.QUALIFIED,
    LeadStatus.QUOTED,
    LeadStatus.WON,
    LeadStatus.LOST,
    LeadStatus.CLOSED,
)


def closer_pipeline_customer_ids():
    """Customer ids that have at least one closer-pipeline lead.

    Uncorrelated subquery so Postgres can compute this set once and hash-join,
    instead of a correlated EXISTS per unread message row.
    """
    return (
        select(Lead.customer_id)
        .where(
            Lead.customer_id.isnot(None),
            Lead.status.in_(CLOSER_PIPELINE_STATUSES),
        )
        .distinct()
    )


def customer_in_closer_pipeline_exists(customer_id_column):
    """True when the customer has at least one lead in the closer pipeline."""
    return customer_id_column.in_(closer_pipeline_customer_ids())
