"""
Service for detecting stale leads and quotes and generating reminders.
"""
from sqlmodel import Session, select, func, and_, or_
from datetime import datetime, timedelta
from typing import List, Optional, Tuple
from app.models import (
    Lead, Quote, Activity, Reminder, ReminderRule, ReminderType, 
    ReminderPriority, SuggestedAction, LeadStatus, QuoteStatus
)


def get_last_activity_date(customer_id: Optional[int], session: Session) -> Optional[datetime]:
    """Get the most recent activity date for a customer."""
    if not customer_id:
        return None
    
    statement = select(func.max(Activity.created_at)).where(Activity.customer_id == customer_id)
    result = session.exec(statement).first()
    return result


def calculate_days_stale(last_date: Optional[datetime], reference_date: Optional[datetime] = None) -> int:
    """Calculate days since last_date. If reference_date is provided, use that instead of now."""
    if not last_date:
        return 999  # Very stale if no date
    
    if reference_date:
        delta = reference_date - last_date
    else:
        delta = datetime.utcnow() - last_date
    
    return max(0, delta.days)


def get_suggested_action_for_lead(lead: Lead, days_stale: int) -> SuggestedAction:
    """Determine suggested action based on lead status and days stale."""
    if lead.status == LeadStatus.QUOTED:
        if days_stale > 10:
            return SuggestedAction.MARK_LOST
        return SuggestedAction.FOLLOW_UP
    elif lead.status in [LeadStatus.QUALIFIED, LeadStatus.ENGAGED]:
        if days_stale > 14:
            return SuggestedAction.MARK_LOST
        return SuggestedAction.CONTACT_CUSTOMER
    elif days_stale > 14:
        return SuggestedAction.MARK_LOST
    return SuggestedAction.FOLLOW_UP


def get_suggested_action_for_quote(quote: Quote, days_stale: int) -> SuggestedAction:
    """Determine suggested action based on quote status and days stale."""
    if quote.status == QuoteStatus.EXPIRED:
        return SuggestedAction.REVIEW_QUOTE
    elif quote.status == QuoteStatus.SENT:
        if days_stale > 14:
            return SuggestedAction.REVIEW_QUOTE
        return SuggestedAction.RESEND_QUOTE
    return SuggestedAction.REVIEW_QUOTE


def calculate_priority(days_stale: int, base_priority: ReminderPriority) -> ReminderPriority:
    """Calculate priority based on days stale and base priority."""
    if days_stale >= 14:
        return ReminderPriority.URGENT
    elif days_stale >= 10:
        if base_priority == ReminderPriority.LOW:
            return ReminderPriority.MEDIUM
        elif base_priority == ReminderPriority.MEDIUM:
            return ReminderPriority.HIGH
        return ReminderPriority.URGENT
    elif days_stale >= 7:
        if base_priority == ReminderPriority.LOW:
            return ReminderPriority.MEDIUM
        return base_priority
    return base_priority


def detect_stale_leads(session: Session) -> List[Tuple[Lead, ReminderRule, int]]:
    """
    Detect stale leads based on active reminder rules.
    Returns list of (lead, rule, days_stale) tuples.
    """
    stale_items = []
    now = datetime.utcnow()
    
    # Get active rules for leads
    statement = select(ReminderRule).where(
        and_(
            ReminderRule.entity_type == "LEAD",
            ReminderRule.is_active == True
        )
    )
    rules = session.exec(statement).all()
    
    for rule in rules:
        # Get leads matching this rule's status
        lead_statement = select(Lead).where(Lead.status == rule.status)
        if rule.status:
            try:
                lead_status = LeadStatus(rule.status)
                lead_statement = select(Lead).where(Lead.status == lead_status)
            except ValueError:
                continue
        
        leads = session.exec(lead_statement).all()
        
        for lead in leads:
            days_stale = 0
            
            if rule.check_type == "LAST_ACTIVITY":
                # Check time since last activity
                last_activity = get_last_activity_date(lead.customer_id, session)
                if not last_activity:
                    # No activity at all, use created_at or updated_at
                    last_activity = lead.updated_at or lead.created_at
                days_stale = calculate_days_stale(last_activity)
            elif rule.check_type == "STATUS_DURATION":
                # Check time since status change (updated_at)
                days_stale = calculate_days_stale(lead.updated_at)
            
            # Check if stale based on threshold
            if days_stale >= rule.threshold_days:
                stale_items.append((lead, rule, days_stale))
    
    return stale_items


def detect_stale_quotes(session: Session) -> List[Tuple[Quote, ReminderRule, int]]:
    """
    Detect stale quotes based on active reminder rules.
    Returns list of (quote, rule, days_stale) tuples.
    """
    stale_items = []
    now = datetime.utcnow()
    
    # Get active rules for quotes
    statement = select(ReminderRule).where(
        and_(
            ReminderRule.entity_type == "QUOTE",
            ReminderRule.is_active == True
        )
    )
    rules = session.exec(statement).all()
    
    for rule in rules:
        # Get quotes matching this rule's status
        quote_statement = select(Quote)
        if rule.status:
            try:
                quote_status = QuoteStatus(rule.status)
                quote_statement = select(Quote).where(Quote.status == quote_status)
            except ValueError:
                continue
        else:
            # No status filter - check all quotes
            quote_statement = select(Quote)
        
        quotes = session.exec(quote_statement).all()
        
        for quote in quotes:
            days_stale = 0
            
            if rule.check_type == "SENT_DATE":
                # Check time since quote was sent
                if not quote.sent_at:
                    continue  # Skip quotes that haven't been sent
                days_stale = calculate_days_stale(quote.sent_at)
            elif rule.check_type == "VALID_UNTIL":
                # Check if quote is expired
                if not quote.valid_until:
                    continue
                if quote.valid_until < now:
                    days_stale = calculate_days_stale(quote.valid_until)
                else:
                    continue  # Not expired yet
            elif rule.check_type == "STATUS_DURATION":
                # Check time since status change (updated_at)
                days_stale = calculate_days_stale(quote.updated_at)
            
            # Check if stale based on threshold
            if days_stale >= rule.threshold_days:
                stale_items.append((quote, rule, days_stale))
    
    return stale_items


def generate_reminders(session: Session, user_id: Optional[int] = None) -> int:
    """
    Generate reminder records for stale leads and quotes.
    Returns count of reminders created.
    """
    count = 0
    now = datetime.utcnow()
    
    # Detect stale leads
    stale_leads = detect_stale_leads(session)
    
    for lead, rule, days_stale in stale_leads:
        # Check if reminder already exists for this lead and rule
        existing = session.exec(
            select(Reminder).where(
                and_(
                    Reminder.lead_id == lead.id,
                    Reminder.reminder_type == ReminderType.LEAD_STALE,
                    Reminder.dismissed_at.is_(None)
                )
            )
        ).first()
        
        if existing:
            # Update existing reminder if days_stale increased
            if days_stale > existing.days_stale:
                existing.days_stale = days_stale
                existing.priority = calculate_priority(days_stale, rule.priority)
                existing.message = f"Lead has been stale for {days_stale} days"
                session.add(existing)
            continue
        
        # Determine assigned user (lead's assigned user or fallback)
        assigned_to_id = lead.assigned_to_id or user_id
        if not assigned_to_id:
            continue  # Skip if no assigned user
        
        # Get suggested action
        suggested_action = get_suggested_action_for_lead(lead, days_stale)
        
        # Calculate priority
        priority = calculate_priority(days_stale, rule.priority)
        
        # Create reminder
        reminder = Reminder(
            reminder_type=ReminderType.LEAD_STALE,
            lead_id=lead.id,
            customer_id=lead.customer_id,
            assigned_to_id=assigned_to_id,
            priority=priority,
            title=f"Stale Lead: {lead.name}",
            message=f"Lead '{lead.name}' has been stale for {days_stale} days (Status: {lead.status.value})",
            suggested_action=suggested_action,
            days_stale=days_stale
        )
        session.add(reminder)
        count += 1
    
    # Detect stale quotes
    stale_quotes = detect_stale_quotes(session)
    
    for quote, rule, days_stale in stale_quotes:
        # Determine reminder type
        if rule.check_type == "VALID_UNTIL" and quote.valid_until and quote.valid_until < now:
            reminder_type = ReminderType.QUOTE_EXPIRED
        elif days_stale >= 7:
            reminder_type = ReminderType.QUOTE_STALE
        else:
            reminder_type = ReminderType.QUOTE_EXPIRING
        
        # Check if reminder already exists for this quote and type
        existing = session.exec(
            select(Reminder).where(
                and_(
                    Reminder.quote_id == quote.id,
                    Reminder.reminder_type == reminder_type,
                    Reminder.dismissed_at.is_(None)
                )
            )
        ).first()
        
        if existing:
            # Update existing reminder if days_stale increased
            if days_stale > existing.days_stale:
                existing.days_stale = days_stale
                existing.priority = calculate_priority(days_stale, rule.priority)
                if reminder_type == ReminderType.QUOTE_EXPIRED:
                    existing.message = f"Quote {quote.quote_number} has expired"
                else:
                    existing.message = f"Quote {quote.quote_number} has been stale for {days_stale} days"
                session.add(existing)
            continue
        
        # Get customer for assigned user
        if not quote.customer_id:
            continue
        
        # Get quote creator as assigned user
        assigned_to_id = quote.created_by_id or user_id
        if not assigned_to_id:
            continue
        
        # Get suggested action
        suggested_action = get_suggested_action_for_quote(quote, days_stale)
        
        # Calculate priority
        priority = calculate_priority(days_stale, rule.priority)
        
        # Create reminder
        if reminder_type == ReminderType.QUOTE_EXPIRED:
            title = f"Expired Quote: {quote.quote_number}"
            message = f"Quote {quote.quote_number} expired on {quote.valid_until.strftime('%Y-%m-%d') if quote.valid_until else 'N/A'}"
        else:
            title = f"Stale Quote: {quote.quote_number}"
            message = f"Quote {quote.quote_number} has been stale for {days_stale} days (Status: {quote.status.value})"
        
        reminder = Reminder(
            reminder_type=reminder_type,
            quote_id=quote.id,
            customer_id=quote.customer_id,
            assigned_to_id=assigned_to_id,
            priority=priority,
            title=title,
            message=message,
            suggested_action=suggested_action,
            days_stale=days_stale
        )
        session.add(reminder)
        count += 1
    
    session.commit()
    return count
