"""
Service for detecting stale leads and quotes and generating reminders.
"""
from sqlmodel import Session, select, func, and_, or_
from datetime import datetime, timedelta
from typing import List, Optional, Tuple
from app.models import (
    Lead, Quote, QuoteEmail, Activity, Reminder, ReminderRule, ReminderType,
    ReminderPriority, SuggestedAction, LeadStatus, QuoteStatus, OpportunityStage
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
            elif rule.check_type == "SENT_NOT_OPENED":
                # Quote sent but view link never opened (nudge after 48h)
                if not quote.sent_at:
                    continue
                # Any QuoteEmail for this quote with opened_at set?
                open_stmt = select(QuoteEmail).where(
                    and_(QuoteEmail.quote_id == quote.id, QuoteEmail.opened_at.isnot(None))
                )
                if session.exec(open_stmt).first() is not None:
                    continue  # Already opened
                days_stale = calculate_days_stale(quote.sent_at)
            elif rule.check_type == "OPENED_NO_REPLY":
                # Quote was opened but no reply (phone call reminder after X days)
                if quote.status != QuoteStatus.SENT:
                    continue
                if quote.viewed_at is None:
                    continue  # Not opened
                days_stale = calculate_days_stale(quote.viewed_at)
            else:
                continue  # Unknown check_type, skip

            # Check if stale based on threshold
            if days_stale >= rule.threshold_days:
                stale_items.append((quote, rule, days_stale))
    
    return stale_items


def detect_stale_opportunities(session: Session) -> List[Tuple[Quote, str, int]]:
    """
    Detect opportunities that need attention based on opportunity-specific rules.
    Returns list of (quote, reason, days_overdue) tuples.
    """
    stale_items = []
    now = datetime.utcnow()
    
    # Get all open opportunities (not WON/LOST)
    statement = select(Quote).where(
        and_(
            Quote.opportunity_stage.isnot(None),
            Quote.opportunity_stage.notin_([OpportunityStage.WON, OpportunityStage.LOST])
        )
    )
    opportunities = session.exec(statement).all()
    
    for opp in opportunities:
        # Check 1: Overdue next action
        if opp.next_action_due_date and opp.next_action_due_date < now:
            days_overdue = calculate_days_stale(opp.next_action_due_date)
            stale_items.append((opp, "OVERDUE_NEXT_ACTION", days_overdue))
        
        # Check 2: Expected close date passed
        if opp.expected_close_date and opp.expected_close_date < now:
            days_overdue = calculate_days_stale(opp.expected_close_date)
            stale_items.append((opp, "CLOSE_DATE_PASSED", days_overdue))
        
        # Check 3: Quote sent and no reply (QUOTE_SENT stage)
        if opp.opportunity_stage == OpportunityStage.QUOTE_SENT and opp.sent_at:
            days_since_sent = calculate_days_stale(opp.sent_at)
            if days_since_sent >= 2 and days_since_sent < 5:
                stale_items.append((opp, "QUOTE_SENT_SOFT_NUDGE", days_since_sent))
            elif days_since_sent >= 5 and days_since_sent < 10:
                stale_items.append((opp, "QUOTE_SENT_FIRM_FOLLOWUP", days_since_sent))
            elif days_since_sent >= 10:
                stale_items.append((opp, "QUOTE_SENT_ESCALATION", days_since_sent))
        
        # Check 4: No activity in X days (configurable, default 7 days)
        if opp.customer_id:
            last_activity = get_last_activity_date(opp.customer_id, session)
            if last_activity:
                days_since_activity = calculate_days_stale(last_activity)
                if days_since_activity >= 7:  # Configurable threshold
                    stale_items.append((opp, "NO_ACTIVITY", days_since_activity))
            else:
                # No activity at all
                days_since_created = calculate_days_stale(opp.created_at)
                if days_since_created >= 7:
                    stale_items.append((opp, "NO_ACTIVITY", days_since_created))
    
    return stale_items


def get_suggested_action_for_opportunity(quote: Quote, reason: str, days_overdue: int) -> SuggestedAction:
    """Determine suggested action based on opportunity issue."""
    if reason == "OVERDUE_NEXT_ACTION":
        return SuggestedAction.FOLLOW_UP
    elif reason == "CLOSE_DATE_PASSED":
        return SuggestedAction.REVIEW_QUOTE
    elif reason in ["QUOTE_SENT_SOFT_NUDGE", "QUOTE_SENT_FIRM_FOLLOWUP"]:
        return SuggestedAction.RESEND_QUOTE
    elif reason == "QUOTE_SENT_ESCALATION":
        return SuggestedAction.MARK_LOST
    elif reason == "NO_ACTIVITY":
        if days_overdue >= 14:
            return SuggestedAction.MARK_LOST
        return SuggestedAction.CONTACT_CUSTOMER
    return SuggestedAction.FOLLOW_UP


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
        elif rule.check_type == "SENT_NOT_OPENED":
            reminder_type = ReminderType.QUOTE_NOT_OPENED
        elif rule.check_type == "OPENED_NO_REPLY":
            reminder_type = ReminderType.QUOTE_OPENED_NO_REPLY
        elif days_stale >= 7:
            reminder_type = ReminderType.QUOTE_STALE
        else:
            reminder_type = ReminderType.QUOTE_EXPIRING

        # Check if reminder already exists for this quote, type, and rule (by message pattern or rule)
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
                elif rule.check_type == "SENT_NOT_OPENED":
                    existing.message = f"Quote {quote.quote_number} not opened in 48h. Send a nudge."
                elif rule.check_type == "OPENED_NO_REPLY":
                    existing.message = f"Quote {quote.quote_number} opened but no reply for {days_stale} days. Schedule a call."
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

        # Use rule's suggested_action for open-tracking rules (RESEND_QUOTE / PHONE_CALL)
        if rule.check_type in ("SENT_NOT_OPENED", "OPENED_NO_REPLY"):
            suggested_action = rule.suggested_action
        else:
            suggested_action = get_suggested_action_for_quote(quote, days_stale)

        # Calculate priority
        priority = calculate_priority(days_stale, rule.priority)

        # Title and message
        if reminder_type == ReminderType.QUOTE_EXPIRED:
            title = f"Expired Quote: {quote.quote_number}"
            message = f"Quote {quote.quote_number} expired on {quote.valid_until.strftime('%Y-%m-%d') if quote.valid_until else 'N/A'}"
        elif rule.check_type == "SENT_NOT_OPENED":
            title = f"Quote not opened: {quote.quote_number}"
            message = f"Quote {quote.quote_number} not opened in 48h. Send a nudge."
        elif rule.check_type == "OPENED_NO_REPLY":
            title = f"Quote opened, no reply: {quote.quote_number}"
            message = f"Quote {quote.quote_number} was opened but no reply for {days_stale} days. Schedule a call."
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
    
    # Detect stale opportunities
    stale_opportunities = detect_stale_opportunities(session)
    
    for opp, reason, days_overdue in stale_opportunities:
        # Determine reminder type and priority
        if reason == "OVERDUE_NEXT_ACTION":
            reminder_type = ReminderType.QUOTE_STALE  # Reuse existing type
            priority = ReminderPriority.URGENT if days_overdue >= 3 else ReminderPriority.HIGH
            title = f"Overdue Next Action: {opp.quote_number}"
            message = f"Next action '{opp.next_action}' was due {days_overdue} days ago"
        elif reason == "CLOSE_DATE_PASSED":
            reminder_type = ReminderType.QUOTE_EXPIRED  # Reuse existing type
            priority = ReminderPriority.URGENT
            title = f"Close Date Passed: {opp.quote_number}"
            message = f"Expected close date passed {days_overdue} days ago. Status update required."
        elif reason == "QUOTE_SENT_SOFT_NUDGE":
            reminder_type = ReminderType.QUOTE_STALE
            priority = ReminderPriority.MEDIUM
            title = f"Quote Follow-Up: {opp.quote_number}"
            message = f"Quote sent {days_overdue} days ago. Consider following up."
        elif reason == "QUOTE_SENT_FIRM_FOLLOWUP":
            reminder_type = ReminderType.QUOTE_STALE
            priority = ReminderPriority.HIGH
            title = f"Quote Follow-Up Required: {opp.quote_number}"
            message = f"Quote sent {days_overdue} days ago. Firm follow-up needed."
        elif reason == "QUOTE_SENT_ESCALATION":
            reminder_type = ReminderType.QUOTE_STALE
            priority = ReminderPriority.URGENT
            title = f"Deal Stalling: {opp.quote_number}"
            message = f"Quote sent {days_overdue} days ago. Deal may be stalling - consider marking as lost."
        elif reason == "NO_ACTIVITY":
            reminder_type = ReminderType.QUOTE_STALE
            priority = ReminderPriority.HIGH if days_overdue >= 14 else ReminderPriority.MEDIUM
            title = f"No Activity: {opp.quote_number}"
            message = f"No activity logged for {days_overdue} days. Follow up required."
        else:
            continue
        
        # Check if reminder already exists
        existing = session.exec(
            select(Reminder).where(
                and_(
                    Reminder.quote_id == opp.id,
                    Reminder.reminder_type == reminder_type,
                    Reminder.dismissed_at.is_(None)
                )
            )
        ).first()
        
        if existing:
            # Update existing reminder
            if days_overdue > existing.days_stale:
                existing.days_stale = days_overdue
                existing.priority = priority
                existing.message = message
                session.add(existing)
            continue
        
        # Get assigned user (opportunity owner or creator)
        assigned_to_id = opp.owner_id or opp.created_by_id or user_id
        if not assigned_to_id:
            continue
        
        # Get suggested action
        suggested_action = get_suggested_action_for_opportunity(opp, reason, days_overdue)
        
        # Create reminder
        reminder = Reminder(
            reminder_type=reminder_type,
            quote_id=opp.id,
            customer_id=opp.customer_id,
            assigned_to_id=assigned_to_id,
            priority=priority,
            title=title,
            message=message,
            suggested_action=suggested_action,
            days_stale=days_overdue
        )
        session.add(reminder)
        count += 1
    
    session.commit()
    return count
