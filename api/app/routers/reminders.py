"""
API endpoints for reminders and stale item management.
"""
import re
from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select, and_, or_, func
from typing import List, Optional, Dict
from app.database import get_session
from app.auth import get_current_user
from datetime import date as date_type, datetime
from app.models import (
    Reminder, ReminderRule, User, UserRole, Lead, Quote, Customer,
    ReminderType, ReminderPriority, SuggestedAction, LeadStatus, QuoteStatus,
    CustomerOutreachChannel,
)
from app.schemas import (
    ReminderResponse, ReminderDismissRequest, ReminderActRequest,
    ReminderRuleResponse, ReminderRuleUpdate, ReminderRuleCreate, StaleSummaryResponse,
    ManualReminderCreate, UserTaskCreate,
)
from app.reminder_service import generate_reminders, calculate_priority

router = APIRouter(prefix="/api/reminders", tags=["reminders"])

_LEAD_CHECK_TYPES = frozenset({"LAST_ACTIVITY", "STATUS_DURATION"})
_QUOTE_CHECK_TYPES = frozenset({
    "SENT_DATE", "VALID_UNTIL", "STATUS_DURATION", "SENT_NOT_OPENED", "OPENED_NO_REPLY",
})


def _normalize_outreach_fields(
    *,
    channel: Optional[str],
    sms_template_id: Optional[int],
    email_template_id: Optional[int],
    cooldown_days: Optional[int],
) -> tuple:
    cd = 14 if cooldown_days is None else cooldown_days
    if cd < 0:
        raise HTTPException(
            status_code=400,
            detail="customer_outreach_cooldown_days cannot be negative",
        )
    if channel is None or str(channel).strip() == "":
        return None, None, None, cd
    ch = str(channel).strip().upper()
    if ch not in (CustomerOutreachChannel.SMS.value, CustomerOutreachChannel.EMAIL.value):
        raise HTTPException(
            status_code=400,
            detail="customer_outreach_channel must be SMS, EMAIL, or omitted",
        )
    if ch == CustomerOutreachChannel.SMS.value:
        if not sms_template_id:
            raise HTTPException(
                status_code=400,
                detail="customer_outreach_sms_template_id is required when channel is SMS",
            )
        return ch, sms_template_id, None, cd
    if not email_template_id:
        raise HTTPException(
            status_code=400,
            detail="customer_outreach_email_template_id is required when channel is EMAIL",
        )
    return ch, None, email_template_id, cd


def _normalize_rule_name(name: str) -> str:
    s = name.strip().upper().replace(" ", "_").replace("-", "_")
    if not s or not re.match(r"^[A-Z0-9_]+$", s):
        raise HTTPException(
            status_code=400,
            detail="rule_name must be non-empty and use only A-Z, 0-9, and underscores",
        )
    return s


def _reminder_rule_to_response(rule: ReminderRule) -> ReminderRuleResponse:
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
        updated_at=rule.updated_at,
        customer_outreach_channel=rule.customer_outreach_channel,
        customer_outreach_sms_template_id=rule.customer_outreach_sms_template_id,
        customer_outreach_email_template_id=rule.customer_outreach_email_template_id,
        customer_outreach_cooldown_days=rule.customer_outreach_cooldown_days
        if rule.customer_outreach_cooldown_days is not None
        else 14,
    )


def _reminder_visibility_filter(current_user: User):
    """Reminder visibility: Directors and Closers see all; others see reminders for their role."""
    if current_user.role in (UserRole.DIRECTOR, UserRole.CLOSER):
        return None  # No extra filter - show all
    same_role_ids = select(User.id).where(User.role == current_user.role)
    return Reminder.assigned_to_id.in_(same_role_ids)


def _effective_days_stale(reminder: Reminder, today: date_type) -> int:
    if reminder.due_date is not None:
        return max(0, (today - reminder.due_date).days)
    return reminder.days_stale


def _effective_priority(reminder: Reminder, today: date_type) -> ReminderPriority:
    if reminder.due_date is None:
        return reminder.priority
    d = _effective_days_stale(reminder, today)
    base = ReminderPriority.MEDIUM if reminder.reminder_type == ReminderType.USER_TASK else reminder.priority
    return calculate_priority(d, base)


def _reminder_to_response(
    session: Session,
    reminder: Reminder,
    today: date_type,
    uid_map: Dict[int, User],
) -> ReminderResponse:
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

    au = uid_map.get(reminder.assigned_to_id)
    assigned_to_name = au.full_name if au else None
    cb_name = None
    if reminder.created_by_id:
        cu = uid_map.get(reminder.created_by_id)
        cb_name = cu.full_name if cu else None

    eff_days = _effective_days_stale(reminder, today)
    eff_pri = _effective_priority(reminder, today)

    return ReminderResponse(
        id=reminder.id,
        reminder_type=reminder.reminder_type,
        lead_id=reminder.lead_id,
        quote_id=reminder.quote_id,
        customer_id=reminder.customer_id,
        assigned_to_id=reminder.assigned_to_id,
        priority=eff_pri,
        title=reminder.title,
        message=reminder.message,
        suggested_action=reminder.suggested_action,
        days_stale=eff_days,
        created_at=reminder.created_at,
        dismissed_at=reminder.dismissed_at,
        acted_upon_at=reminder.acted_upon_at,
        lead_name=lead_name,
        quote_number=quote_number,
        customer_name=customer_name,
        due_date=reminder.due_date,
        created_by_id=reminder.created_by_id,
        created_by_name=cb_name,
        assigned_to_name=assigned_to_name,
    )


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
    uid_map = {current_user.id: current_user}
    return _reminder_to_response(session, reminder, date_type.today(), uid_map)


@router.post("/tasks", response_model=ReminderResponse)
async def create_user_task(
    body: UserTaskCreate,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """Create a user task (self or another active user); appears in reminders with overdue from due_date."""
    if not body.title or not body.title.strip():
        raise HTTPException(status_code=400, detail="title is required")
    assignee_id = body.assigned_to_id if body.assigned_to_id is not None else current_user.id
    assignee = session.exec(select(User).where(User.id == assignee_id)).first()
    if not assignee or not assignee.is_active:
        raise HTTPException(status_code=400, detail="Assignee not found or inactive")

    if body.customer_id is not None:
        customer = session.exec(select(Customer).where(Customer.id == body.customer_id)).first()
        if not customer:
            raise HTTPException(status_code=404, detail="Customer not found")

    today = date_type.today()
    delta_days = max(0, (today - body.due_date).days)
    pri = calculate_priority(delta_days, ReminderPriority.MEDIUM)

    reminder = Reminder(
        reminder_type=ReminderType.USER_TASK,
        lead_id=None,
        quote_id=None,
        customer_id=body.customer_id,
        assigned_to_id=assignee_id,
        created_by_id=current_user.id,
        priority=pri,
        title=body.title.strip(),
        message=(body.message.strip() or " "),
        suggested_action=SuggestedAction.FOLLOW_UP,
        days_stale=delta_days,
        due_date=body.due_date,
    )
    session.add(reminder)
    session.commit()
    session.refresh(reminder)

    uid_map: Dict[int, User] = {current_user.id: current_user, assignee.id: assignee}
    return _reminder_to_response(session, reminder, today, uid_map)


@router.get("", response_model=List[ReminderResponse])
async def get_reminders(
    dismissed: Optional[bool] = False,
    done: Optional[bool] = None,
    priority: Optional[ReminderPriority] = None,
    reminder_type: Optional[ReminderType] = None,
    assigned_to_me: Optional[bool] = None,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """Get active reminders for the current user (per role; Directors see all)."""
    statement = select(Reminder)
    visibility = _reminder_visibility_filter(current_user)
    if visibility is not None:
        statement = statement.where(visibility)

    if assigned_to_me is True:
        statement = statement.where(Reminder.assigned_to_id == current_user.id)

    if done is True:
        statement = statement.where(
            or_(
                Reminder.acted_upon_at.isnot(None),
                Reminder.dismissed_at.isnot(None),
            )
        )
    elif dismissed is False:
        statement = statement.where(Reminder.dismissed_at.is_(None))
        statement = statement.where(Reminder.acted_upon_at.is_(None))
    elif dismissed is True:
        statement = statement.where(Reminder.dismissed_at.isnot(None))
    
    if priority:
        statement = statement.where(Reminder.priority == priority)
    
    if reminder_type:
        statement = statement.where(Reminder.reminder_type == reminder_type)
    
    reminders = session.exec(statement).all()
    today = date_type.today()

    user_ids = set()
    for r in reminders:
        user_ids.add(r.assigned_to_id)
        if r.created_by_id:
            user_ids.add(r.created_by_id)
    uid_map: Dict[int, User] = {}
    if user_ids:
        users = session.exec(select(User).where(User.id.in_(user_ids))).all()
        uid_map = {u.id: u for u in users}

    result = [_reminder_to_response(session, r, today, uid_map) for r in reminders]

    priority_order = {
        ReminderPriority.URGENT: 0,
        ReminderPriority.HIGH: 1,
        ReminderPriority.MEDIUM: 2,
        ReminderPriority.LOW: 3,
    }

    def sort_key(resp: ReminderResponse):
        return (
            priority_order.get(resp.priority, 99),
            -resp.days_stale,
            -resp.created_at.timestamp() if resp.created_at else 0,
        )

    result.sort(key=sort_key)
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
        Reminder.dismissed_at.is_(None),
        Reminder.acted_upon_at.is_(None)
    )
    high_count = _count_where(
        Reminder.priority == ReminderPriority.HIGH,
        Reminder.dismissed_at.is_(None),
        Reminder.acted_upon_at.is_(None)
    )
    medium_count = _count_where(
        Reminder.priority == ReminderPriority.MEDIUM,
        Reminder.dismissed_at.is_(None),
        Reminder.acted_upon_at.is_(None)
    )
    low_count = _count_where(
        Reminder.priority == ReminderPriority.LOW,
        Reminder.dismissed_at.is_(None),
        Reminder.acted_upon_at.is_(None)
    )
    total_reminders = urgent_count + high_count + medium_count + low_count

    stale_leads_count = _count_where(
        Reminder.reminder_type == ReminderType.LEAD_STALE,
        Reminder.dismissed_at.is_(None),
        Reminder.acted_upon_at.is_(None)
    )
    stale_quotes_count = _count_where(
        Reminder.reminder_type.in_([ReminderType.QUOTE_STALE, ReminderType.QUOTE_EXPIRED, ReminderType.QUOTE_EXPIRING, ReminderType.QUOTE_NOT_OPENED, ReminderType.QUOTE_OPENED_NO_REPLY]),
        Reminder.dismissed_at.is_(None),
        Reminder.acted_upon_at.is_(None)
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
    _current_user: User = Depends(get_current_user),
):
    """Dismiss a reminder. Any authenticated user may dismiss any reminder."""
    reminder = session.exec(select(Reminder).where(Reminder.id == reminder_id)).first()
    
    if not reminder:
        raise HTTPException(status_code=404, detail="Reminder not found")

    reminder.dismissed_at = datetime.utcnow()
    session.add(reminder)
    session.commit()
    
    return {"message": "Reminder dismissed", "id": reminder_id}


@router.post("/{reminder_id}/act")
async def act_on_reminder(
    reminder_id: int,
    request: ReminderActRequest,
    session: Session = Depends(get_session),
    _current_user: User = Depends(get_current_user),
):
    """Mark a reminder as acted upon. Any authenticated user may complete any reminder."""
    reminder = session.exec(select(Reminder).where(Reminder.id == reminder_id)).first()
    
    if not reminder:
        raise HTTPException(status_code=404, detail="Reminder not found")

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
    return [_reminder_rule_to_response(rule) for rule in rules]


@router.post("/rules", response_model=ReminderRuleResponse)
async def create_reminder_rule(
    body: ReminderRuleCreate,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """Create a reminder rule (Director only). Uses check types supported by reminder generation."""
    if current_user.role != UserRole.DIRECTOR:
        raise HTTPException(status_code=403, detail="Only directors can create reminder rules")

    rule_name = _normalize_rule_name(body.rule_name)
    if session.exec(select(ReminderRule).where(ReminderRule.rule_name == rule_name)).first():
        raise HTTPException(status_code=400, detail="A rule with this name already exists")

    entity = body.entity_type.strip().upper()
    if entity not in ("LEAD", "QUOTE"):
        raise HTTPException(status_code=400, detail="entity_type must be LEAD or QUOTE")

    check_type = body.check_type.strip().upper()
    if entity == "LEAD":
        if check_type not in _LEAD_CHECK_TYPES:
            raise HTTPException(
                status_code=400,
                detail=f"check_type for LEAD must be one of: {sorted(_LEAD_CHECK_TYPES)}",
            )
    elif check_type not in _QUOTE_CHECK_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"check_type for QUOTE must be one of: {sorted(_QUOTE_CHECK_TYPES)}",
        )

    if body.threshold_days < 0:
        raise HTTPException(status_code=400, detail="threshold_days cannot be negative")

    if entity == "LEAD":
        if not body.status or not str(body.status).strip():
            raise HTTPException(status_code=400, detail="status is required for LEAD rules")
        try:
            status_val = LeadStatus(body.status.strip().upper()).value
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid LeadStatus for status")
    else:
        if body.status and str(body.status).strip():
            try:
                status_val = QuoteStatus(body.status.strip().upper()).value
            except ValueError:
                raise HTTPException(status_code=400, detail="Invalid QuoteStatus for status")
        else:
            status_val = None

    och, ost, oet, ocd = _normalize_outreach_fields(
        channel=body.customer_outreach_channel,
        sms_template_id=body.customer_outreach_sms_template_id,
        email_template_id=body.customer_outreach_email_template_id,
        cooldown_days=body.customer_outreach_cooldown_days,
    )

    rule = ReminderRule(
        rule_name=rule_name,
        entity_type=entity,
        status=status_val,
        threshold_days=body.threshold_days,
        check_type=check_type,
        is_active=body.is_active,
        priority=body.priority,
        suggested_action=body.suggested_action,
        customer_outreach_channel=och,
        customer_outreach_sms_template_id=ost,
        customer_outreach_email_template_id=oet,
        customer_outreach_cooldown_days=ocd,
    )
    session.add(rule)
    session.commit()
    session.refresh(rule)
    return _reminder_rule_to_response(rule)


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

    patch = rule_update.model_dump(exclude_unset=True)
    outreach_keys = (
        "customer_outreach_channel",
        "customer_outreach_sms_template_id",
        "customer_outreach_email_template_id",
        "customer_outreach_cooldown_days",
    )
    if any(k in patch for k in outreach_keys):
        if "customer_outreach_channel" in patch:
            raw_ch = patch["customer_outreach_channel"]
            if raw_ch is None or (isinstance(raw_ch, str) and raw_ch.strip() == ""):
                rule.customer_outreach_channel = None
                rule.customer_outreach_sms_template_id = None
                rule.customer_outreach_email_template_id = None
                if "customer_outreach_cooldown_days" in patch and patch["customer_outreach_cooldown_days"] is not None:
                    if patch["customer_outreach_cooldown_days"] < 0:
                        raise HTTPException(
                            status_code=400,
                            detail="customer_outreach_cooldown_days cannot be negative",
                        )
                    rule.customer_outreach_cooldown_days = patch["customer_outreach_cooldown_days"]
            else:
                ch_n, st_n, et_n, cd_n = _normalize_outreach_fields(
                    channel=raw_ch,
                    sms_template_id=patch.get(
                        "customer_outreach_sms_template_id", rule.customer_outreach_sms_template_id
                    ),
                    email_template_id=patch.get(
                        "customer_outreach_email_template_id", rule.customer_outreach_email_template_id
                    ),
                    cooldown_days=patch.get(
                        "customer_outreach_cooldown_days", rule.customer_outreach_cooldown_days
                    ),
                )
                rule.customer_outreach_channel = ch_n
                rule.customer_outreach_sms_template_id = st_n
                rule.customer_outreach_email_template_id = et_n
                rule.customer_outreach_cooldown_days = cd_n
        elif rule.customer_outreach_channel:
            ch_n, st_n, et_n, cd_n = _normalize_outreach_fields(
                channel=rule.customer_outreach_channel,
                sms_template_id=patch.get(
                    "customer_outreach_sms_template_id", rule.customer_outreach_sms_template_id
                ),
                email_template_id=patch.get(
                    "customer_outreach_email_template_id", rule.customer_outreach_email_template_id
                ),
                cooldown_days=patch.get(
                    "customer_outreach_cooldown_days", rule.customer_outreach_cooldown_days
                ),
            )
            rule.customer_outreach_channel = ch_n
            rule.customer_outreach_sms_template_id = st_n
            rule.customer_outreach_email_template_id = et_n
            rule.customer_outreach_cooldown_days = cd_n

    rule.updated_at = datetime.utcnow()

    session.add(rule)
    session.commit()
    session.refresh(rule)

    return _reminder_rule_to_response(rule)


@router.delete("/rules/{rule_id}")
async def delete_reminder_rule(
    rule_id: int,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """Delete a reminder rule (Director only)."""
    if current_user.role != UserRole.DIRECTOR:
        raise HTTPException(status_code=403, detail="Only directors can delete reminder rules")

    rule = session.exec(select(ReminderRule).where(ReminderRule.id == rule_id)).first()
    if not rule:
        raise HTTPException(status_code=404, detail="Reminder rule not found")

    session.delete(rule)
    session.commit()
    return {"message": "Reminder rule deleted", "id": rule_id}
