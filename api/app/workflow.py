from typing import Dict, List, Optional, Set
from app.models import LeadStatus, UserRole, ActivityType, Timeframe, Lead, Activity, Customer, CompanySettings
from sqlmodel import Session, select
from datetime import datetime, timedelta
from decimal import Decimal


# Define allowed transitions per role
WORKFLOW_TRANSITIONS = {
    UserRole.DIRECTOR: {
        LeadStatus.NEW: [LeadStatus.ENGAGED, LeadStatus.CONTACT_ATTEMPTED, LeadStatus.LOST],
        LeadStatus.CONTACT_ATTEMPTED: [LeadStatus.ENGAGED, LeadStatus.LOST],
        LeadStatus.ENGAGED: [LeadStatus.QUALIFIED, LeadStatus.LOST],
        LeadStatus.QUALIFIED: [LeadStatus.QUOTED, LeadStatus.LOST, LeadStatus.CLOSED],
        LeadStatus.QUOTED: [LeadStatus.WON, LeadStatus.LOST],
    },
    UserRole.SALES_MANAGER: {
        LeadStatus.NEW: [LeadStatus.ENGAGED, LeadStatus.CONTACT_ATTEMPTED],
        LeadStatus.CONTACT_ATTEMPTED: [LeadStatus.ENGAGED],
        LeadStatus.ENGAGED: [LeadStatus.QUALIFIED],
    },
    UserRole.CLOSER: {
        LeadStatus.QUALIFIED: [LeadStatus.QUOTED, LeadStatus.CLOSED],
        LeadStatus.QUOTED: [LeadStatus.WON, LeadStatus.LOST],
    },
}

# Engagement proof activity types
ENGAGEMENT_PROOF_TYPES = {
    ActivityType.SMS_RECEIVED,
    ActivityType.EMAIL_RECEIVED,
    ActivityType.EMAIL_SENT,  # Sending email counts as engagement/contact
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


def batch_customers_with_any_activity(session: Session, customer_ids: Set[int]) -> Set[int]:
    if not customer_ids:
        return set()
    rows = session.exec(
        select(Activity.customer_id)
        .where(Activity.customer_id.in_(customer_ids))
        .distinct()
    ).all()
    return {int(cid) for cid in rows if cid is not None}


def batch_customers_with_engagement_proof(session: Session, customer_ids: Set[int]) -> Set[int]:
    if not customer_ids:
        return set()
    rows = session.exec(
        select(Activity.customer_id)
        .where(
            Activity.customer_id.in_(customer_ids),
            Activity.activity_type.in_(list(ENGAGEMENT_PROOF_TYPES)),
        )
        .distinct()
    ).all()
    return {int(cid) for cid in rows if cid is not None}


def batch_sla_badges_for_leads(session: Session, leads: List[Lead]) -> Dict[int, Optional[str]]:
    """Compute SLA badges for a page of leads without per-lead activity queries."""
    now = datetime.utcnow()
    customer_ids = {int(l.customer_id) for l in leads if l.customer_id is not None}
    customers_with_activity = batch_customers_with_any_activity(session, customer_ids)
    customers_with_engagement = batch_customers_with_engagement_proof(session, customer_ids)
    out: Dict[int, Optional[str]] = {}
    for lead in leads:
        if lead.id is None:
            continue
        badge: Optional[str] = None
        if lead.status == LeadStatus.NEW:
            has_activity = bool(lead.customer_id and int(lead.customer_id) in customers_with_activity)
            if not has_activity:
                if now - lead.created_at > timedelta(minutes=15):
                    badge = "red"
        elif lead.status == LeadStatus.CONTACT_ATTEMPTED:
            has_engagement = bool(
                lead.customer_id and int(lead.customer_id) in customers_with_engagement
            )
            if not has_engagement:
                if now - lead.created_at > timedelta(hours=48):
                    badge = "amber"
        out[int(lead.id)] = badge
    return out


def check_quote_prerequisites(
    customer: Customer,
    session: Session,
    *,
    company_settings: Optional[CompanySettings] = None,
    has_engagement_proof: Optional[bool] = None,
) -> tuple[bool, Optional[dict]]:
    """
    Check if customer profile meets quote contact rules.
    At least two of postcode, email, and phone must be present (any pair).
    Returns (can_quote, error_dict)
    """
    missing = []

    # Customer profile: need any two of postcode, email, phone
    if not customer.postcode:
        missing.append("postcode")

    if not customer.email:
        missing.append("email")

    if not customer.phone:
        missing.append("phone")

    contact_filled = 3 - len(missing)
    if contact_filled < 2:
        return False, {
            "error": "QUOTE_PREREQS_MISSING",
            "missing": missing,
            "message": "At least two of postcode, email, and phone are required.",
        }
    
    # Engagement proof: only required when company setting is enabled
    if company_settings is None:
        company_settings = session.exec(select(CompanySettings)).first()
    if company_settings and getattr(company_settings, "require_engagement_proof", False):
        if has_engagement_proof is None:
            has_engagement_proof = customer.id in batch_customers_with_engagement_proof(
                session, {int(customer.id)} if customer.id is not None else set()
            )
        if not has_engagement_proof:
            return False, {
                "error": "NO_ENGAGEMENT_PROOF",
                "message": "No engagement proof found (SMS_RECEIVED, EMAIL_RECEIVED, EMAIL_SENT, WHATSAPP_RECEIVED, or LIVE_CALL)"
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


def sync_customer_contact_from_lead_on_qualify(session: Session, lead: Lead) -> None:
    """
    Copy lead contact fields onto the linked customer when the lead is (or becomes) qualified.

    Facebook and similar imports attach customer_id immediately with raw form data; staff often
    correct name, email, phone, or postcode on the lead before qualifying. The customer profile
    should match the lead for CRM and outreach.

    Phone and postcode are only updated when the lead has a non-empty value after strip, so
    clearing them on the lead does not wipe known-good customer contact data used for SMS and quoting.
    """
    if not lead.customer_id:
        return
    customer = session.get(Customer, lead.customer_id)
    if not customer:
        return

    def _norm_optional(s: Optional[str]) -> Optional[str]:
        t = (s or "").strip()
        return t if t else None

    new_name = (lead.name or "").strip() or customer.name
    new_email = _norm_optional(lead.email)
    postcode_stripped = (lead.postcode or "").strip()
    new_postcode = postcode_stripped if postcode_stripped else None
    phone_stripped = (lead.phone or "").strip()
    new_phone = phone_stripped if phone_stripped else None

    dirty = False
    if customer.name != new_name:
        customer.name = new_name
        dirty = True
    if customer.email != new_email:
        customer.email = new_email
        dirty = True
    if new_postcode is not None and customer.postcode != new_postcode:
        customer.postcode = new_postcode
        dirty = True
    if new_phone is not None and customer.phone != new_phone:
        customer.phone = new_phone
        dirty = True
    # Keep customer-level wrong-email marker aligned when staff mark it on a qualified lead.
    if customer.wrong_email_address != bool(getattr(lead, "wrong_email_address", False)):
        customer.wrong_email_address = bool(getattr(lead, "wrong_email_address", False))
        dirty = True

    if dirty:
        customer.updated_at = datetime.utcnow()
        session.add(customer)


def auto_transition_lead_status(
    lead_id: int,
    new_status: LeadStatus,
    session: Session,
    changed_by_id: int,
    reason: Optional[str] = None
) -> bool:
    """
    Automatically transition a lead to a new status.
    Uses director override logic to allow automatic transitions.
    Returns True if transition occurred, False otherwise.
    """
    statement = select(Lead).where(Lead.id == lead_id)
    lead = session.exec(statement).first()
    
    if not lead:
        return False
    
    # Skip if already in target status
    if lead.status == new_status:
        return False
    
    # Use director override logic for automatic transitions
    allowed, error = can_transition(
        UserRole.DIRECTOR,  # Use director role for automatic transitions
        lead.status,
        new_status,
        lead,
        session,
        is_override=True  # Allow override for automatic transitions
    )
    
    if not allowed:
        return False

    if new_status == LeadStatus.QUALIFIED:
        from app.lead_qualify_rules import lead_fields_allow_qualify

        if not lead_fields_allow_qualify(lead.lead_source, lead.lead_type):
            return False
    
    old_status = lead.status
    lead.status = new_status
    lead.updated_at = datetime.utcnow()
    session.add(lead)

    if new_status == LeadStatus.QUALIFIED:
        sync_customer_contact_from_lead_on_qualify(session, lead)

    # Create status history record
    from app.models import StatusHistory
    status_history = StatusHistory(
        lead_id=lead.id,
        old_status=old_status,
        new_status=new_status,
        changed_by_id=changed_by_id,
        override_reason=reason or "Automatic transition"
    )
    session.add(status_history)
    session.commit()
    session.refresh(lead)
    
    return True


def find_leads_by_customer_id(customer_id: int, session: Session) -> list[Lead]:
    """Find all leads associated with a customer."""
    statement = select(Lead).where(Lead.customer_id == customer_id)
    return list(session.exec(statement).all())


def auto_create_opportunity(
    customer_id: int,
    lead_id: int,
    session: Session,
    created_by_id: int
) -> Optional["Quote"]:
    """
    Automatically create an opportunity (quote) when lead becomes QUALIFIED.
    Returns the created Quote/opportunity, or None if one already exists.
    """
    from app.models import Quote, OpportunityStage, QuoteStatus
    from app.routers.quotes import generate_quote_number
    
    # Check if opportunity already exists for this customer
    statement = select(Quote).where(Quote.customer_id == customer_id)
    existing_quotes = session.exec(statement).all()
    
    if existing_quotes:
        # Opportunity already exists, return None
        return None
    
    # Get the lead to inherit owner
    statement = select(Lead).where(Lead.id == lead_id)
    lead = session.exec(statement).first()
    
    if not lead:
        return None
    
    # Create minimal opportunity (quote) with default values
    quote_number = generate_quote_number(session)
    next_action_due = datetime.utcnow() + timedelta(days=2)
    
    opportunity = Quote(
        customer_id=customer_id,
        lead_id=lead_id,
        quote_number=quote_number,
        version=1,
        subtotal=Decimal(0),
        discount_total=Decimal(0),
        total_amount=Decimal(0),
        deposit_amount=Decimal(0),
        balance_amount=Decimal(0),
        currency="GBP",
        status=QuoteStatus.DRAFT,
        created_by_id=created_by_id,
        owner_id=lead.assigned_to_id if lead.assigned_to_id else created_by_id,
        opportunity_stage=OpportunityStage.DISCOVERY,
        close_probability=Decimal("25.00"),  # 25% default for DISCOVERY
        next_action="Initial contact and site visit",
        next_action_due_date=next_action_due
    )
    
    session.add(opportunity)
    session.commit()
    session.refresh(opportunity)
    
    return opportunity
