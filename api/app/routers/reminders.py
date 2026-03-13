"""
API endpoints for reminders and stale item management.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select, and_, or_, func
from typing import List, Optional
from app.database import get_session
from app.auth import get_current_user
from datetime import date as date_type
from app.models import (
    Reminder, ReminderRule, User, UserRole, Lead, Quote, Customer,
    ReminderType, ReminderPriority, SuggestedAction
)
from app.schemas import (
    ReminderResponse, ReminderDismissRequest, ReminderActRequest,
    ReminderRuleResponse, ReminderRuleUpdate, StaleSummaryResponse,
    ManualReminderCreate
)
from app.reminder_service import generate_reminders

router = APIRouter(prefix="/api/reminders", tags=["reminders"])


def _reminder_visibility_filter(current_user: User):
    """Reminder visibility: Directors see all; others see reminders for their role."""
    if current_user.role == UserRole.DIRECTOR:
        return None  # No extra filter - show all
    same_role_ids = select(User.id).where(User.role == current_user.role)
    return Reminder.assigned_to_id.in_(same_role_ids)


@router.post("", response_model=ReminderResponse)
async def create_manual_reminder(
    body: ManualReminderCreate,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """Create a manual reminder (e.g. call back) for a customer."""
    customer = session.exec(select(Customer).where(Customer.id == body.customer_id)).first()
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")
    today = date_type.today()
    delta = (body.reminder_date - today).days
    days_stale = max(0, delta)
    reminder = Reminder(
        reminder_type=ReminderType.MANUAL,
        lead_id=None,
        quote_id=None,
        customer_id=body.customer_id,
        assigned_to_id=current_user.id,
        priority=ReminderPriority.MEDIUM,
        title=body.title,
        message=body.message,
        suggested_action=SuggestedAction.CONTACT_CUSTOMER,
        days_stale=days_stale,
    )
    session.add(reminder)
    session.commit()
    session.refresh(reminder)
    return ReminderResponse(
        id=reminder.id,
        reminder_type=reminder.reminder_type,
        lead_id=reminder.lead_id,
        quote_id=reminder.quote_id,
        customer_id=reminder.customer_id,
        assigned_to_id=reminder.assigned_to_id,
        priority=reminder.priority,
        title=reminder.title,
        message=reminder.message,
        suggested_action=reminder.suggested_action,
        days_stale=reminder.days_stale,
        created_at=reminder.created_at,
        dismissed_at=reminder.dismissed_at,
        acted_upon_at=reminder.acted_upon_at,
        customer_name=customer.name,
    )


@router.get("", response_model=List[ReminderResponse])
async def get_reminders(
    dismissed: Optional[bool] = False,
    priority: Optional[ReminderPriority] = None,
    reminder_type: Optional[ReminderType] = None,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """Get active reminders for the current user (per role; Directors see all)."""
    statement = select(Reminder)
    visibility = _reminder_visibility_filter(current_user)
    if visibility is not None:
        statement = statement.where(visibility)

    if dismissed is False:
        statement = statement.where(Reminder.dismissed_at.is_(None))
    elif dismissed is True:
        statement = statement.where(Reminder.dismissed_at.isnot(None))
    
    if priority:
        statement = statement.where(Reminder.priority == priority)
    
    if reminder_type:
        statement = statement.where(Reminder.reminder_type == reminder_type)
    
    statement = statement.order_by(
        Reminder.priority.desc(),
        Reminder.days_stale.desc(),
        Reminder.created_at.desc()
    )
    
    reminders = session.exec(statement).all()
    
    result = []
    for reminder in reminders:
        lead_name = None
        quote_number = None
        customer_name = None
        
        if reminder.lead_id:
            lead = session.exec(select(Lead).where(Lead.id == reminder.lead_id)).first()
            if lead:
                lead_name = lead.name
        
        if reminder.quote_id:
            quote = session.exec(select(Quote).where(Quote.id == reminder.quote_id)).first()
            if quote:
                quote_number = quote.quote_number
        
        if reminder.customer_id:
            customer = session.exec(select(Customer).where(Customer.id == reminder.customer_id)).first()
            if customer:
                customer_name = customer.name
        
        result.append(ReminderResponse(
            id=reminder.id,
            reminder_type=reminder.reminder_type,
            lead_id=reminder.lead_id,
            quote_id=reminder.quote_id,
            customer_id=reminder.customer_id,
            assigned_to_id=reminder.assigned_to_id,
            priority=reminder.priority,
            title=reminder.title,
            message=reminder.message,
            suggested_action=reminder.suggested_action,
            days_stale=reminder.days_stale,
            created_at=reminder.created_at,
            dismissed_at=reminder.dismissed_at,
            acted_upon_at=reminder.acted_upon_at,
            lead_name=lead_name,
            quote_number=quote_number,
            customer_name=customer_name
        ))
    
    return result


@router.get("/stale-summary", response_model=StaleSummaryResponse)
async def get_stale_summary(
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """Get summary of stale items and reminders (per role; Directors see all)."""
    visibility = _reminder_visibility_filter(current_user)

    def _count_where(*conds):
        all_conds = list(conds)
        if visibility is not None:
            all_conds.append(visibility)
        return session.exec(select(func.count(Reminder.id)).where(and_(*all_conds))).one()

    urgent_count = _count_where(
        Reminder.priority == ReminderPriority.URGENT,
        Reminder.dismissed_at.is_(None)
    )
    high_count = _count_where(
        Reminder.priority == ReminderPriority.HIGH,
        Reminder.dismissed_at.is_(None)
    )
    medium_count = _count_where(
        Reminder.priority == ReminderPriority.MEDIUM,
        Reminder.dismissed_at.is_(None)
    )
    low_count = _count_where(
        Reminder.priority == ReminderPriority.LOW,
        Reminder.dismissed_at.is_(None)
    )
    total_reminders = urgent_count + high_count + medium_count + low_count

    stale_leads_count = _count_where(
        Reminder.reminder_type == ReminderType.LEAD_STALE,
        Reminder.dismissed_at.is_(None)
    )
    stale_quotes_count = _count_where(
        Reminder.reminder_type.in_([ReminderType.QUOTE_STALE, ReminderType.QUOTE_EXPIRED, ReminderType.QUOTE_EXPIRING, ReminderType.QUOTE_NOT_OPENED, ReminderType.QUOTE_OPENED_NO_REPLY]),
        Reminder.dismissed_at.is_(None)
    )
    
    return StaleSummaryResponse(
        total_reminders=total_reminders,
        urgent_count=urgent_count,
        high_count=high_count,
        medium_count=medium_count,
        low_count=low_count,
        stale_leads_count=stale_leads_count,
        stale_quotes_count=stale_quotes_count
    )


@router.post("/{reminder_id}/dismiss")
async def dismiss_reminder(
    reminder_id: int,
    request: ReminderDismissRequest,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """Dismiss a reminder."""
    reminder = session.exec(select(Reminder).where(Reminder.id == reminder_id)).first()
    
    if not reminder:
        raise HTTPException(status_code=404, detail="Reminder not found")

    if current_user.role != UserRole.DIRECTOR:
        assigned_user = session.exec(select(User).where(User.id == reminder.assigned_to_id)).first()
        if not assigned_user or assigned_user.role != current_user.role:
            raise HTTPException(status_code=403, detail="Not authorized to dismiss this reminder")

    from datetime import datetime
    reminder.dismissed_at = datetime.utcnow()
    session.add(reminder)
    session.commit()
    
    return {"message": "Reminder dismissed", "id": reminder_id}


@router.post("/{reminder_id}/act")
async def act_on_reminder(
    reminder_id: int,
    request: ReminderActRequest,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """Mark a reminder as acted upon."""
    reminder = session.exec(select(Reminder).where(Reminder.id == reminder_id)).first()
    
    if not reminder:
        raise HTTPException(status_code=404, detail="Reminder not found")

    if current_user.role != UserRole.DIRECTOR:
        assigned_user = session.exec(select(User).where(User.id == reminder.assigned_to_id)).first()
        if not assigned_user or assigned_user.role != current_user.role:
            raise HTTPException(status_code=403, detail="Not authorized to act on this reminder")

    from datetime import datetime
    reminder.acted_upon_at = datetime.utcnow()
    session.add(reminder)
    session.commit()
    
    return {"message": "Reminder marked as acted upon", "id": reminder_id}


@router.post("/generate")
async def generate_reminders_endpoint(
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """Manually trigger reminder generation."""
    count = generate_reminders(session, current_user.id)
    return {"message": f"Generated {count} reminders", "count": count}


@router.get("/rules", response_model=List[ReminderRuleResponse])
async def get_reminder_rules(
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """Get all reminder rules (configuration)."""
    rules = session.exec(select(ReminderRule).order_by(ReminderRule.entity_type, ReminderRule.rule_name)).all()
    
    return [
        ReminderRuleResponse(
            id=rule.id,
            rule_name=rule.rule_name,
            entity_type=rule.entity_type,
            status=rule.status,
            threshold_days=rule.threshold_days,
            check_type=rule.check_type,
            is_active=rule.is_active,
            priority=rule.priority,
            suggested_action=rule.suggested_action,
            created_at=rule.created_at,
            updated_at=rule.updated_at
        )
        for rule in rules
    ]


@router.put("/rules/{rule_id}", response_model=ReminderRuleResponse)
async def update_reminder_rule(
    rule_id: int,
    rule_update: ReminderRuleUpdate,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """Update a reminder rule (Director only)."""
    if current_user.role != UserRole.DIRECTOR:
        raise HTTPException(status_code=403, detail="Only directors can update reminder rules")
    
    rule = session.exec(select(ReminderRule).where(ReminderRule.id == rule_id)).first()
    
    if not rule:
        raise HTTPException(status_code=404, detail="Reminder rule not found")
    
    if rule_update.threshold_days is not None:
        rule.threshold_days = rule_update.threshold_days
    if rule_update.is_active is not None:
        rule.is_active = rule_update.is_active
    if rule_update.priority is not None:
        rule.priority = rule_update.priority
    if rule_update.suggested_action is not None:
        rule.suggested_action = rule_update.suggested_action
    
    from datetime import datetime
    rule.updated_at = datetime.utcnow()
    
    session.add(rule)
    session.commit()
    session.refresh(rule)
    
    return ReminderRuleResponse(
        id=rule.id,
        rule_name=rule.rule_name,
        entity_type=rule.entity_type,
        status=rule.status,
        threshold_days=rule.threshold_days,
        check_type=rule.check_type,
        is_active=rule.is_active,
        priority=rule.priority,
        suggested_action=rule.suggested_action,
        created_at=rule.created_at,
        updated_at=rule.updated_at
    )
