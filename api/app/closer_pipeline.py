"""Shared SQL helpers for closer-visible lead/customer scope."""
from sqlalchemy import exists
from sqlmodel import select

from app.models import Lead, LeadStatus

CLOSER_PIPELINE_STATUSES = (
    LeadStatus.QUALIFIED,
    LeadStatus.QUOTED,
    LeadStatus.WON,
)


def customer_in_closer_pipeline_exists(customer_id_column):
    """True when the customer has at least one lead in the closer pipeline."""
    return exists(
        select(Lead.id).where(
            Lead.customer_id == customer_id_column,
            Lead.status.in_(CLOSER_PIPELINE_STATUSES),
        )
    )
