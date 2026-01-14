from typing import Optional
from app.models import LeadStatus, UserRole, ActivityType, Timeframe, Lead, Activity, Customer
from sqlmodel import Session, select
from datetime import datetime, timedelta


# Define allowed transitions per role
WORKFLOW_TRANSITIONS = {
    UserRole.DIRECTOR: {
        LeadStatus.NEW: [LeadStatus.CONTACT_ATTEMPTED, LeadStatus.LOST],
        LeadStatus.CONTACT_ATTEMPTED: [LeadStatus.ENGAGED, LeadStatus.LOST],
        LeadStatus.ENGAGED: [LeadStatus.QUALIFIED, LeadStatus.LOST],
        LeadStatus.QUALIFIED: [LeadStatus.QUOTED, LeadStatus.LOST],
        LeadStatus.QUOTED: [LeadStatus.WON, LeadStatus.LOST],
    },
    UserRole.SALES_MANAGER: {
        LeadStatus.NEW: [LeadStatus.CONTACT_ATTEMPTED],
        LeadStatus.CONTACT_ATTEMPTED: [LeadStatus.ENGAGED],
        LeadStatus.ENGAGED: [LeadStatus.QUALIFIED],
    },
    UserRole.CLOSER: {
        LeadStatus.QUALIFIED: [LeadStatus.QUOTED],
        LeadStatus.QUOTED: [LeadStatus.WON, LeadStatus.LOST],
    },
}

# Engagement proof activity types
ENGAGEMENT_PROOF_TYPES = {
    ActivityType.SMS_RECEIVED,
    ActivityType.EMAIL_RECEIVED,
    ActivityType.WHATSAPP_RECEIVED,
    ActivityType.LIVE_CALL,
}


def get_allowed_transitions(user_role: UserRole, current_status: LeadStatus) -> list[LeadStatus]:
    """Get allowed next statuses for a user role and current status."""
    if user_role == UserRole.DIRECTOR:
        # Director can override any transition
        all_statuses = list(LeadStatus)
        return [s for s in all_statuses if s != current_status]
    
    transitions = WORKFLOW_TRANSITIONS.get(user_role, {})
    return transitions.get(current_status, [])


def check_quote_prerequisites(customer: Customer, session: Session) -> tuple[bool, Optional[dict]]:
    """
    Check if customer profile is complete for quote creation.
    Returns (can_quote, error_dict)
    """
    missing = []
    
    # Customer profile requirements
    if not customer.address_line1:
        missing.append("address_line1")
    
    if not customer.city:
        missing.append("city")
    
    if not customer.county:
        missing.append("county")
    
    if not customer.postcode:
        missing.append("postcode")
    
    if not customer.email:
        missing.append("email")
    
    if not customer.phone:
        missing.append("phone")
    
    if missing:
        return False, {
            "error": "QUOTE_PREREQS_MISSING",
            "missing": missing
        }
    
    # Check for engagement proof (activities linked to customer)
    statement = select(Activity).where(
        Activity.customer_id == customer.id,
        Activity.activity_type.in_(list(ENGAGEMENT_PROOF_TYPES))
    )
    engagement_activities = session.exec(statement).all()
    
    if not engagement_activities:
        return False, {
            "error": "NO_ENGAGEMENT_PROOF",
            "message": "No engagement proof found (SMS_RECEIVED, EMAIL_RECEIVED, WHATSAPP_RECEIVED, or LIVE_CALL)"
        }
    
    return True, None


def can_transition(
    user_role: UserRole,
    current_status: LeadStatus,
    new_status: LeadStatus,
    lead: Lead,
    session: Session,
    is_override: bool = False
) -> tuple[bool, Optional[dict]]:
    """
    Check if a status transition is allowed.
    Returns (allowed, error_dict)
    """
    # Director can override with reason
    if user_role == UserRole.DIRECTOR and is_override:
        # Still check quote prerequisites if moving to QUOTED (requires customer)
        if new_status == LeadStatus.QUOTED:
            if not lead.customer_id:
                return False, {"error": "NO_CUSTOMER", "message": "Lead must have a customer profile to quote"}
            statement = select(Customer).where(Customer.id == lead.customer_id)
            customer = session.exec(statement).first()
            if customer:
                can_quote, error = check_quote_prerequisites(customer, session)
                if not can_quote:
                    return False, error
        return True, None
    
    # Check if transition is in allowed list
    allowed = get_allowed_transitions(user_role, current_status)
    if new_status not in allowed:
        return False, {
            "error": "TRANSITION_NOT_ALLOWED",
            "message": f"Cannot transition from {current_status} to {new_status} with role {user_role}"
        }
    
    # Special check for QUOTED status (requires customer)
    if new_status == LeadStatus.QUOTED:
        if not lead.customer_id:
            return False, {"error": "NO_CUSTOMER", "message": "Lead must have a customer profile to quote"}
        statement = select(Customer).where(Customer.id == lead.customer_id)
        customer = session.exec(statement).first()
        if customer:
            can_quote, error = check_quote_prerequisites(customer, session)
            if not can_quote:
                return False, error
    
    return True, None


def check_sla_overdue(lead: Lead, session: Session) -> Optional[str]:
    """
    Check if lead is overdue on SLA.
    Returns badge type if overdue, None otherwise.
    """
    now = datetime.utcnow()
    
    # NEW + no activity >15 mins (check customer activities if lead has customer)
    if lead.status == LeadStatus.NEW:
        activities = []
        if lead.customer_id:
            statement = select(Activity).where(Activity.customer_id == lead.customer_id)
            activities = session.exec(statement).all()
        if not activities:
            time_since_created = now - lead.created_at
            if time_since_created > timedelta(minutes=15):
                return "red"
    
    # CONTACT_ATTEMPTED + no engagement >48h (check customer activities if lead has customer)
    if lead.status == LeadStatus.CONTACT_ATTEMPTED:
        engagement = []
        if lead.customer_id:
            statement = select(Activity).where(
                Activity.customer_id == lead.customer_id,
                Activity.activity_type.in_(list(ENGAGEMENT_PROOF_TYPES))
            )
            engagement = session.exec(statement).all()
        if not engagement:
            time_since_created = now - lead.created_at
            if time_since_created > timedelta(hours=48):
                return "amber"
    
    return None
