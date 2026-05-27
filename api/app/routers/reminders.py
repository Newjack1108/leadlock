"""
API endpoints for reminders and stale item management.
"""
import re
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session, select, and_, or_, func, col
from sqlalchemy import case
from typing import List, Optional, Dict, Tuple
from jinja2 import Template as JinjaTemplate, TemplateError
from app.database import get_session
from app.auth import get_current_user
from datetime import date as date_type, datetime, timedelta
from app.models import (
    Reminder, ReminderRule, User, UserRole, Lead, Quote, Customer,
    ReminderType, ReminderPriority, SuggestedAction, LeadStatus, QuoteStatus,
    CustomerOutreachChannel,
    CustomerOutreachSend,
    AutomatedReminderCleanupSuppression,
    DeletedReminderRuleName,
    ReminderCleanupTargetKind,
    WeeklyPlanItem,
    WeeklyPlanItemStatus,
    WeeklyPlanRun,
    WeeklyPlanTemplate,
)
from app.schemas import (
    ReminderResponse, ReminderDismissRequest, ReminderActRequest,
    AutomatedReminderCleanupRequest, AutomatedReminderCleanupResponse,
    ReminderRuleResponse, ReminderRuleUpdate, ReminderRuleCreate, StaleSummaryResponse,
    ManualReminderCreate, UserTaskCreate,
    OutreachSendListResponse,
    OutreachSendListItemResponse,
    OutreachSendTargetType,
    WeeklyPlanItemOutcomeUpdate,
    WeeklyPlanItemResponse,
    WeeklyPlanListResponse,
    WeeklyPlanRunResponse,
    WeeklyPlanTemplateCreate,
    WeeklyPlanTemplatePreviewRequest,
    WeeklyPlanTemplatePreviewResponse,
    WeeklyPlanTemplateResponse,
    WeeklyPlanTemplateUpdate,
    WeeklyPlanBulkSendRequest,
)
from app.reminder_service import generate_reminders, calculate_priority, get_reminder_cleanup_target
from app.weekly_planner_service import (
    execute_auto_eligible_items,
    generate_weekly_plan,
    get_plan_metrics,
    mark_plan_item_outcome,
    render_weekly_plan_item_message,
    send_weekly_plan_item,
    send_weekly_plan_items_bulk,
)

router = APIRouter(prefix="/api/reminders", tags=["reminders"])

_LEAD_CHECK_TYPES = frozenset({"LAST_ACTIVITY", "STATUS_DURATION"})
_QUOTE_CHECK_TYPES = frozenset({
    "SENT_DATE", "VALID_UNTIL", "STATUS_DURATION", "SENT_NOT_OPENED", "OPENED_NO_REPLY",
})
_USER_TASK_NEAR_DUE_DAYS = 1


def _weekly_plan_run_to_response(run: WeeklyPlanRun) -> WeeklyPlanRunResponse:
    return WeeklyPlanRunResponse(
        id=run.id,
        week_start=run.week_start,
        generated_at=run.generated_at,
        scope=run.scope,
        model_version=run.model_version,
        generated_by_id=run.generated_by_id,
        total_items=run.total_items,
        auto_eligible_items=run.auto_eligible_items,
        auto_sent_items=run.auto_sent_items,
    )


def _weekly_plan_item_to_response(
    session: Session,
    item: WeeklyPlanItem,
    uid_map: Dict[int, User],
    lead_by_id: Dict[int, Lead],
    quote_by_id: Dict[int, Quote],
    customer_by_id: Dict[int, Customer],
) -> WeeklyPlanItemResponse:
    assignee_name = uid_map[item.assigned_to_id].full_name if item.assigned_to_id in uid_map else None
    lead = lead_by_id.get(item.lead_id) if item.lead_id else None
    quote = quote_by_id.get(item.quote_id) if item.quote_id else None
    customer = customer_by_id.get(item.customer_id) if item.customer_id else None
    return WeeklyPlanItemResponse(
        id=item.id,
        plan_run_id=item.plan_run_id,
        lead_id=item.lead_id,
        quote_id=item.quote_id,
        customer_id=item.customer_id,
        assigned_to_id=item.assigned_to_id,
        assigned_to_name=assignee_name,
        customer_name=customer.name if customer else None,
        quote_number=quote.quote_number if quote else None,
        lead_name=lead.name if lead else None,
        priority_score=item.priority_score,
        confidence=item.confidence,
        order_likelihood_score=item.order_likelihood_score,
        order_likelihood_confidence=item.order_likelihood_confidence,
        order_likelihood_reasons=item.order_likelihood_reasons or [],
        likelihood_explanation=item.likelihood_explanation,
        recommended_next_steps=item.recommended_next_steps or [],
        reason_codes=item.reason_codes or [],
        recommended_action=item.recommended_action,
        channel=item.channel,
        status=item.status,
        auto_eligible=item.auto_eligible,
        suggested_message=item.suggested_message,
        due_date=item.due_date,
        executed_at=item.executed_at,
        execution_error=item.execution_error,
        outcome_result=item.outcome_result,
        response_received=item.response_received,
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


def _weekly_template_to_response(template: WeeklyPlanTemplate, created_by_name: Optional[str]) -> WeeklyPlanTemplateResponse:
    return WeeklyPlanTemplateResponse(
        id=template.id,
        name=template.name,
        description=template.description,
        suggested_action=template.suggested_action,
        channel=template.channel,
        subject_template=template.subject_template,
        body_template=template.body_template,
        is_active=template.is_active,
        created_by_id=template.created_by_id,
        created_at=template.created_at,
        updated_at=template.updated_at,
        created_by_name=created_by_name,
    )


def _weekly_template_preview_context(customer_name: Optional[str], quote_number: Optional[str]) -> dict:
    return {
        "customer": {
            "name": (customer_name or "Sample Customer").strip() or "Sample Customer",
        },
        "quote": {
            "number": (quote_number or "Q-12345").strip() or "Q-12345",
        },
        "company": {
            "name": "LeadLock",
        },
    }


def _load_latest_outreach_by_target(
    session: Session, reminders: List[Reminder]
) -> Dict[Tuple[str, int], Tuple[CustomerOutreachSend, str]]:
    """
    Latest CustomerOutreachSend per reminder target: quote reminders match by quote_id;
    lead-only reminders match sends with that lead_id and quote_id IS NULL.
    """
    quote_ids = {r.quote_id for r in reminders if r.quote_id}
    lead_only_ids = {r.lead_id for r in reminders if r.lead_id and not r.quote_id}
    if not quote_ids and not lead_only_ids:
        return {}

    if quote_ids and lead_only_ids:
        where_clause = or_(
            CustomerOutreachSend.quote_id.in_(quote_ids),
            and_(
                CustomerOutreachSend.lead_id.in_(lead_only_ids),
                CustomerOutreachSend.quote_id.is_(None),
            ),
        )
    elif quote_ids:
        where_clause = CustomerOutreachSend.quote_id.in_(quote_ids)
    else:
        where_clause = and_(
            CustomerOutreachSend.lead_id.in_(lead_only_ids),
            CustomerOutreachSend.quote_id.is_(None),
        )

    rows = session.exec(
        select(CustomerOutreachSend, ReminderRule.rule_name)
        .join(ReminderRule, ReminderRule.id == CustomerOutreachSend.reminder_rule_id)
        .where(where_clause)
        .order_by(col(CustomerOutreachSend.sent_at).desc(), col(CustomerOutreachSend.id).desc())
    ).all()

    result: Dict[Tuple[str, int], Tuple[CustomerOutreachSend, str]] = {}
    for send, rule_name in rows:
        if send.quote_id is not None and send.quote_id in quote_ids:
            k: Tuple[str, int] = ("q", send.quote_id)
        elif send.lead_id is not None and send.quote_id is None and send.lead_id in lead_only_ids:
            k = ("l", send.lead_id)
        else:
            continue
        if k not in result:
            result[k] = (send, rule_name)
    return result


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
        threshold_minutes=rule.threshold_minutes,
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
        customer_outreach_on_lead_create=bool(
            getattr(rule, "customer_outreach_on_lead_create", False)
        ),
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


def _build_reminders_statement(
    *,
    current_user: User,
    dismissed: Optional[bool] = False,
    done: Optional[bool] = None,
    priority: Optional[ReminderPriority] = None,
    reminder_type: Optional[ReminderType] = None,
    assigned_to_me: Optional[bool] = None,
):
    today = date_type.today()
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

    # Keep user tasks out of active reminder lists until they are near due.
    if done is not True and dismissed is False:
        near_due_cutoff = today + timedelta(days=_USER_TASK_NEAR_DUE_DAYS)
        statement = statement.where(
            or_(
                Reminder.reminder_type != ReminderType.USER_TASK,
                Reminder.due_date <= near_due_cutoff,
            )
        )
    return statement


def _reminder_target_key(reminder: Reminder) -> Optional[Tuple[str, int]]:
    if reminder.quote_id:
        return ("q", reminder.quote_id)
    if reminder.lead_id:
        return ("l", reminder.lead_id)
    return None


def _get_reminder_auto_outreach_fields(
    reminder: Reminder,
    outreach_by_target: Optional[Dict[Tuple[str, int], Tuple[CustomerOutreachSend, str]]],
) -> Tuple[Optional[str], Optional[str], Optional[datetime], Optional[str], Optional[str]]:
    auto_status: Optional[str] = None
    auto_channel: Optional[str] = None
    auto_sent_at: Optional[datetime] = None
    auto_fail: Optional[str] = None
    auto_rule: Optional[str] = None

    if not outreach_by_target:
        return auto_status, auto_channel, auto_sent_at, auto_fail, auto_rule

    target_key = _reminder_target_key(reminder)
    if target_key is None:
        return auto_status, auto_channel, auto_sent_at, auto_fail, auto_rule

    tup = outreach_by_target.get(target_key)
    if tup:
        send, rule_name = tup
        auto_status = getattr(send, "status", None) or "SENT"
        auto_channel = send.channel
        auto_sent_at = send.sent_at
        auto_fail = getattr(send, "failure_reason", None)
        auto_rule = rule_name
    return auto_status, auto_channel, auto_sent_at, auto_fail, auto_rule


def _record_automated_cleanup_suppression(
    session: Session,
    *,
    reminder: Reminder,
    cleaned_up_by_id: int,
    auto_status: Optional[str],
    auto_channel: Optional[str],
    auto_sent_at: Optional[datetime],
) -> bool:
    target = get_reminder_cleanup_target(
        reminder_type=reminder.reminder_type,
        lead_id=reminder.lead_id,
        quote_id=reminder.quote_id,
    )
    if target is None:
        return False

    target_kind, target_id = target
    suppression = session.exec(
        select(AutomatedReminderCleanupSuppression).where(
            AutomatedReminderCleanupSuppression.target_kind == target_kind,
            AutomatedReminderCleanupSuppression.target_id == target_id,
            AutomatedReminderCleanupSuppression.reminder_type == reminder.reminder_type,
        )
    ).first()
    if suppression is None:
        suppression = AutomatedReminderCleanupSuppression(
            target_kind=target_kind,
            target_id=target_id,
            reminder_type=reminder.reminder_type,
            lead_id=reminder.lead_id,
            quote_id=reminder.quote_id,
            customer_id=reminder.customer_id,
        )

    suppression.lead_id = reminder.lead_id
    suppression.quote_id = reminder.quote_id
    suppression.customer_id = reminder.customer_id
    suppression.last_auto_outreach_status = auto_status
    suppression.last_auto_outreach_channel = auto_channel
    suppression.last_auto_outreach_sent_at = auto_sent_at
    suppression.cleaned_up_by_id = cleaned_up_by_id
    suppression.cleaned_up_at = datetime.utcnow()
    session.add(suppression)
    return True


def _reminder_to_response(
    session: Session,
    reminder: Reminder,
    today: date_type,
    uid_map: Dict[int, User],
    *,
    lead_by_id: Optional[Dict[int, Lead]] = None,
    quote_by_id: Optional[Dict[int, Quote]] = None,
    customer_by_id: Optional[Dict[int, Customer]] = None,
    outreach_by_target: Optional[Dict[Tuple[str, int], Tuple[CustomerOutreachSend, str]]] = None,
) -> ReminderResponse:
    lead_name = None
    quote_number = None
    customer_name = None
    if reminder.lead_id:
        if lead_by_id is not None:
            lead = lead_by_id.get(reminder.lead_id)
        else:
            lead = session.exec(select(Lead).where(Lead.id == reminder.lead_id)).first()
        if lead:
            lead_name = lead.name
    if reminder.quote_id:
        if quote_by_id is not None:
            quote = quote_by_id.get(reminder.quote_id)
        else:
            quote = session.exec(select(Quote).where(Quote.id == reminder.quote_id)).first()
        if quote:
            quote_number = quote.quote_number
    if reminder.customer_id:
        if customer_by_id is not None:
            customer = customer_by_id.get(reminder.customer_id)
        else:
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

    auto_status, auto_channel, auto_sent_at, auto_fail, auto_rule = _get_reminder_auto_outreach_fields(
        reminder, outreach_by_target
    )

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
        auto_outreach_status=auto_status,
        auto_outreach_channel=auto_channel,
        auto_outreach_sent_at=auto_sent_at,
        auto_outreach_failure_reason=auto_fail,
        auto_outreach_rule_name=auto_rule,
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
    today = date_type.today()
    statement = _build_reminders_statement(
        current_user=current_user,
        dismissed=dismissed,
        done=done,
        priority=priority,
        reminder_type=reminder_type,
        assigned_to_me=assigned_to_me,
    )
    reminders = session.exec(statement).all()

    user_ids = set()
    for r in reminders:
        user_ids.add(r.assigned_to_id)
        if r.created_by_id:
            user_ids.add(r.created_by_id)
    uid_map: Dict[int, User] = {}
    if user_ids:
        users = session.exec(select(User).where(User.id.in_(user_ids))).all()
        uid_map = {u.id: u for u in users}

    lead_ids = {r.lead_id for r in reminders if r.lead_id}
    quote_ids = {r.quote_id for r in reminders if r.quote_id}
    customer_ids = {r.customer_id for r in reminders if r.customer_id}
    lead_by_id: Dict[int, Lead] = {}
    if lead_ids:
        leads = session.exec(select(Lead).where(Lead.id.in_(lead_ids))).all()
        lead_by_id = {lead.id: lead for lead in leads if lead.id is not None}
    quote_by_id: Dict[int, Quote] = {}
    if quote_ids:
        quotes = session.exec(select(Quote).where(Quote.id.in_(quote_ids))).all()
        quote_by_id = {q.id: q for q in quotes if q.id is not None}
    customer_by_id: Dict[int, Customer] = {}
    if customer_ids:
        customers = session.exec(select(Customer).where(Customer.id.in_(customer_ids))).all()
        customer_by_id = {c.id: c for c in customers if c.id is not None}

    outreach_by_target = _load_latest_outreach_by_target(session, list(reminders))

    result = [
        _reminder_to_response(
            session,
            r,
            today,
            uid_map,
            lead_by_id=lead_by_id,
            quote_by_id=quote_by_id,
            customer_by_id=customer_by_id,
            outreach_by_target=outreach_by_target,
        )
        for r in reminders
    ]

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


@router.post("/cleanup-automated", response_model=AutomatedReminderCleanupResponse)
async def cleanup_automated_reminders(
    payload: AutomatedReminderCleanupRequest,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """Hard-delete visible active reminders that already have automated outreach and suppress regeneration."""
    reminders = session.exec(
        _build_reminders_statement(
            current_user=current_user,
            dismissed=False,
            done=None,
            priority=payload.priority,
            reminder_type=payload.reminder_type,
            assigned_to_me=payload.assigned_to_me,
        )
    ).all()

    if not reminders:
        return AutomatedReminderCleanupResponse(deleted_count=0, deleted_ids=[])

    outreach_by_target = _load_latest_outreach_by_target(session, list(reminders))
    deleted_ids: List[int] = []
    for reminder in reminders:
        auto_status, auto_channel, auto_sent_at, _auto_fail, _auto_rule = _get_reminder_auto_outreach_fields(
            reminder, outreach_by_target
        )
        if auto_status not in {"SENT", "FAILED"}:
            continue
        if not _record_automated_cleanup_suppression(
            session,
            reminder=reminder,
            cleaned_up_by_id=current_user.id,
            auto_status=auto_status,
            auto_channel=auto_channel,
            auto_sent_at=auto_sent_at,
        ):
            continue
        if reminder.id is not None:
            deleted_ids.append(reminder.id)
        session.delete(reminder)

    if deleted_ids:
        session.commit()
    return AutomatedReminderCleanupResponse(deleted_count=len(deleted_ids), deleted_ids=deleted_ids)


@router.get("/stale-summary", response_model=StaleSummaryResponse)
async def get_stale_summary(
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """Get summary of stale items and reminders (per role; Directors see all)."""
    visibility = _reminder_visibility_filter(current_user)
    base_conds = [
        Reminder.dismissed_at.is_(None),
        Reminder.acted_upon_at.is_(None),
    ]
    if visibility is not None:
        base_conds.append(visibility)

    quote_stale_types = (
        ReminderType.QUOTE_STALE,
        ReminderType.QUOTE_EXPIRED,
        ReminderType.QUOTE_EXPIRING,
        ReminderType.QUOTE_NOT_OPENED,
        ReminderType.QUOTE_OPENED_NO_REPLY,
    )
    agg_stmt = select(
        func.coalesce(
            func.sum(case((Reminder.priority == ReminderPriority.URGENT, 1), else_=0)), 0
        ),
        func.coalesce(
            func.sum(case((Reminder.priority == ReminderPriority.HIGH, 1), else_=0)), 0
        ),
        func.coalesce(
            func.sum(case((Reminder.priority == ReminderPriority.MEDIUM, 1), else_=0)), 0
        ),
        func.coalesce(
            func.sum(case((Reminder.priority == ReminderPriority.LOW, 1), else_=0)), 0
        ),
        func.coalesce(
            func.sum(case((Reminder.reminder_type == ReminderType.LEAD_STALE, 1), else_=0)), 0
        ),
        func.coalesce(
            func.sum(case((Reminder.reminder_type.in_(quote_stale_types), 1), else_=0)), 0
        ),
    ).where(and_(*base_conds))
    row = session.exec(agg_stmt).one()
    urgent_count = int(row[0] or 0)
    high_count = int(row[1] or 0)
    medium_count = int(row[2] or 0)
    low_count = int(row[3] or 0)
    total_reminders = urgent_count + high_count + medium_count + low_count
    stale_leads_count = int(row[4] or 0)
    stale_quotes_count = int(row[5] or 0)

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


@router.get("/weekly-plan/templates", response_model=List[WeeklyPlanTemplateResponse])
def list_weekly_plan_templates(
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    if current_user.role != UserRole.DIRECTOR:
        raise HTTPException(status_code=403, detail="Only directors can view weekly plan templates")
    rows = session.exec(
        select(WeeklyPlanTemplate, User)
        .outerjoin(User, WeeklyPlanTemplate.created_by_id == User.id)
        .order_by(col(WeeklyPlanTemplate.suggested_action), col(WeeklyPlanTemplate.channel))
    ).all()
    return [_weekly_template_to_response(t, u.full_name if u else None) for t, u in rows]


@router.post("/weekly-plan/templates", response_model=WeeklyPlanTemplateResponse)
def create_weekly_plan_template(
    payload: WeeklyPlanTemplateCreate,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    if current_user.role != UserRole.DIRECTOR:
        raise HTTPException(status_code=403, detail="Only directors can create weekly plan templates")
    channel = (payload.channel or "").strip().upper()
    if channel not in {"EMAIL", "SMS", "CALL"}:
        raise HTTPException(status_code=400, detail="channel must be EMAIL, SMS, or CALL")
    template = WeeklyPlanTemplate(
        name=payload.name.strip(),
        description=payload.description,
        suggested_action=payload.suggested_action,
        channel=channel,
        subject_template=(payload.subject_template or "").strip() or None,
        body_template=payload.body_template,
        is_active=bool(payload.is_active if payload.is_active is not None else True),
        created_by_id=current_user.id,
    )
    session.add(template)
    try:
        session.commit()
    except Exception:
        session.rollback()
        raise HTTPException(
            status_code=409,
            detail=f"Template for {payload.suggested_action.value}/{channel} already exists",
        )
    session.refresh(template)
    return _weekly_template_to_response(template, current_user.full_name)


@router.put("/weekly-plan/templates/{template_id}", response_model=WeeklyPlanTemplateResponse)
def update_weekly_plan_template(
    template_id: int,
    payload: WeeklyPlanTemplateUpdate,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    if current_user.role != UserRole.DIRECTOR:
        raise HTTPException(status_code=403, detail="Only directors can update weekly plan templates")
    template = session.get(WeeklyPlanTemplate, template_id)
    if not template:
        raise HTTPException(status_code=404, detail="Weekly plan template not found")
    if payload.name is not None:
        template.name = payload.name.strip()
    if payload.description is not None:
        template.description = payload.description
    if payload.suggested_action is not None:
        template.suggested_action = payload.suggested_action
    if payload.channel is not None:
        channel = payload.channel.strip().upper()
        if channel not in {"EMAIL", "SMS", "CALL"}:
            raise HTTPException(status_code=400, detail="channel must be EMAIL, SMS, or CALL")
        template.channel = channel
    if payload.subject_template is not None:
        template.subject_template = payload.subject_template.strip() or None
    if payload.body_template is not None:
        template.body_template = payload.body_template
    if payload.is_active is not None:
        template.is_active = payload.is_active
    template.updated_at = datetime.utcnow()
    session.add(template)
    try:
        session.commit()
    except Exception:
        session.rollback()
        raise HTTPException(
            status_code=409,
            detail=f"Template for {template.suggested_action.value}/{template.channel} already exists",
        )
    session.refresh(template)

    matching_items = session.exec(
        select(WeeklyPlanItem).where(
            WeeklyPlanItem.recommended_action == template.suggested_action,
            WeeklyPlanItem.channel == template.channel,
            WeeklyPlanItem.status == WeeklyPlanItemStatus.PENDING_REVIEW,
        )
    ).all()
    if matching_items:
        customer_ids = {item.customer_id for item in matching_items if item.customer_id}
        quote_ids = {item.quote_id for item in matching_items if item.quote_id}
        customer_by_id: Dict[int, Customer] = {}
        if customer_ids:
            customers = session.exec(select(Customer).where(Customer.id.in_(customer_ids))).all()
            customer_by_id = {customer.id: customer for customer in customers if customer.id is not None}
        quote_by_id: Dict[int, Quote] = {}
        if quote_ids:
            quotes = session.exec(select(Quote).where(Quote.id.in_(quote_ids))).all()
            quote_by_id = {quote.id: quote for quote in quotes if quote.id is not None}

        now = datetime.utcnow()
        for item in matching_items:
            item.suggested_message = render_weekly_plan_item_message(
                session,
                action=item.recommended_action,
                channel=item.channel or template.channel,
                customer_id=item.customer_id,
                quote_id=item.quote_id,
                customer_by_id=customer_by_id,
                quote_by_id=quote_by_id,
            )
            item.updated_at = now
            session.add(item)
        session.commit()

    owner = session.get(User, template.created_by_id)
    return _weekly_template_to_response(template, owner.full_name if owner else None)


@router.delete("/weekly-plan/templates/{template_id}")
def delete_weekly_plan_template(
    template_id: int,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    if current_user.role != UserRole.DIRECTOR:
        raise HTTPException(status_code=403, detail="Only directors can delete weekly plan templates")
    template = session.get(WeeklyPlanTemplate, template_id)
    if not template:
        raise HTTPException(status_code=404, detail="Weekly plan template not found")
    session.delete(template)
    session.commit()
    return {"message": "Weekly plan template deleted"}


@router.post("/weekly-plan/templates/{template_id}/preview", response_model=WeeklyPlanTemplatePreviewResponse)
def preview_weekly_plan_template(
    template_id: int,
    payload: WeeklyPlanTemplatePreviewRequest,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    if current_user.role != UserRole.DIRECTOR:
        raise HTTPException(status_code=403, detail="Only directors can preview weekly plan templates")
    template = session.get(WeeklyPlanTemplate, template_id)
    if not template:
        raise HTTPException(status_code=404, detail="Weekly plan template not found")
    ctx = _weekly_template_preview_context(payload.customer_name, payload.quote_number)
    try:
        body = JinjaTemplate(template.body_template or "").render(**ctx)
        subject = JinjaTemplate(template.subject_template).render(**ctx) if template.subject_template else None
    except TemplateError as exc:
        raise HTTPException(status_code=400, detail=f"Template render error: {exc}") from exc
    return WeeklyPlanTemplatePreviewResponse(subject=subject, body=body)


@router.post("/weekly-plan/generate", response_model=WeeklyPlanRunResponse)
def generate_weekly_plan_endpoint(
    auto_execute: bool = Query(False),
    dry_run: bool = Query(False),
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    run = generate_weekly_plan(
        session,
        generated_by_id=current_user.id,
        auto_execute=auto_execute,
        dry_run=dry_run,
    )
    return _weekly_plan_run_to_response(run)


@router.post("/weekly-plan/{run_id}/execute-auto")
def execute_weekly_plan_auto(
    run_id: int,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    if current_user.role != UserRole.DIRECTOR:
        raise HTTPException(status_code=403, detail="Only directors can trigger automation")
    sent = execute_auto_eligible_items(session, run_id)
    return {"message": f"Auto-executed {sent} weekly plan item(s)", "sent_count": sent}


@router.get("/weekly-plan/latest", response_model=WeeklyPlanListResponse)
async def get_latest_weekly_plan(
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    run = session.exec(select(WeeklyPlanRun).order_by(col(WeeklyPlanRun.generated_at).desc()).limit(1)).first()
    if not run:
        raise HTTPException(status_code=404, detail="No weekly plan run found")
    items = session.exec(
        select(WeeklyPlanItem)
        .where(WeeklyPlanItem.plan_run_id == run.id)
        .order_by(col(WeeklyPlanItem.priority_score).desc(), col(WeeklyPlanItem.created_at).asc())
    ).all()

    user_ids = {item.assigned_to_id for item in items if item.assigned_to_id}
    lead_ids = {item.lead_id for item in items if item.lead_id}
    quote_ids = {item.quote_id for item in items if item.quote_id}
    customer_ids = {item.customer_id for item in items if item.customer_id}
    uid_map = {u.id: u for u in session.exec(select(User).where(User.id.in_(user_ids))).all()} if user_ids else {}
    lead_by_id = {l.id: l for l in session.exec(select(Lead).where(Lead.id.in_(lead_ids))).all()} if lead_ids else {}
    quote_by_id = {q.id: q for q in session.exec(select(Quote).where(Quote.id.in_(quote_ids))).all()} if quote_ids else {}
    customer_by_id = {c.id: c for c in session.exec(select(Customer).where(Customer.id.in_(customer_ids))).all()} if customer_ids else {}

    return WeeklyPlanListResponse(
        run=_weekly_plan_run_to_response(run),
        items=[
            _weekly_plan_item_to_response(session, item, uid_map, lead_by_id, quote_by_id, customer_by_id)
            for item in items
        ],
    )


@router.patch("/weekly-plan/items/{item_id}", response_model=WeeklyPlanItemResponse)
async def update_weekly_plan_item_outcome(
    item_id: int,
    payload: WeeklyPlanItemOutcomeUpdate,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    item = mark_plan_item_outcome(
        session,
        item_id,
        status=payload.status,
        outcome_result=payload.outcome_result,
        response_received=payload.response_received,
    )
    if not item:
        raise HTTPException(status_code=404, detail="Weekly plan item not found")
    uid_map = {}
    if item.assigned_to_id:
        assignee = session.get(User, item.assigned_to_id)
        if assignee:
            uid_map[assignee.id] = assignee
    lead_by_id = {}
    if item.lead_id:
        lead = session.get(Lead, item.lead_id)
        if lead:
            lead_by_id[lead.id] = lead
    quote_by_id = {}
    if item.quote_id:
        quote = session.get(Quote, item.quote_id)
        if quote:
            quote_by_id[quote.id] = quote
    customer_by_id = {}
    if item.customer_id:
        customer = session.get(Customer, item.customer_id)
        if customer:
            customer_by_id[customer.id] = customer
    return _weekly_plan_item_to_response(session, item, uid_map, lead_by_id, quote_by_id, customer_by_id)


@router.post("/weekly-plan/items/{item_id}/send", response_model=WeeklyPlanItemResponse)
def send_weekly_plan_single_item(
    item_id: int,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    if current_user.role not in (UserRole.DIRECTOR, UserRole.CLOSER):
        raise HTTPException(status_code=403, detail="Only directors and closers can send weekly plan actions")
    item = send_weekly_plan_item(session, item_id, sender_user_id=current_user.id)
    if not item:
        raise HTTPException(status_code=404, detail="Weekly plan item not found")
    uid_map: Dict[int, User] = {}
    if item.assigned_to_id:
        assignee = session.get(User, item.assigned_to_id)
        if assignee:
            uid_map[assignee.id] = assignee
    lead_by_id: Dict[int, Lead] = {}
    if item.lead_id:
        lead = session.get(Lead, item.lead_id)
        if lead:
            lead_by_id[lead.id] = lead
    quote_by_id: Dict[int, Quote] = {}
    if item.quote_id:
        quote = session.get(Quote, item.quote_id)
        if quote:
            quote_by_id[quote.id] = quote
    customer_by_id: Dict[int, Customer] = {}
    if item.customer_id:
        customer = session.get(Customer, item.customer_id)
        if customer:
            customer_by_id[customer.id] = customer
    return _weekly_plan_item_to_response(session, item, uid_map, lead_by_id, quote_by_id, customer_by_id)


@router.post("/weekly-plan/items/send-bulk")
def send_weekly_plan_items_in_bulk(
    payload: WeeklyPlanBulkSendRequest,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    if current_user.role not in (UserRole.DIRECTOR, UserRole.CLOSER):
        raise HTTPException(status_code=403, detail="Only directors and closers can send weekly plan actions")
    result = send_weekly_plan_items_bulk(session, payload.item_ids or [], sender_user_id=current_user.id)
    return {
        "message": f"Sent {result['sent']} of {result['requested']} selected item(s)",
        **result,
    }


@router.get("/weekly-plan/{run_id}/metrics")
async def get_weekly_plan_metrics(
    run_id: int,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    metrics = get_plan_metrics(session, run_id)
    if not metrics:
        raise HTTPException(status_code=404, detail="Weekly plan run not found")
    return metrics


@router.get("/weekly-plan/trend")
async def get_weekly_plan_trend(
    weeks: int = Query(8, ge=2, le=26),
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    runs = session.exec(
        select(WeeklyPlanRun)
        .order_by(col(WeeklyPlanRun.week_start).desc(), col(WeeklyPlanRun.generated_at).desc())
        .limit(weeks * 2)
    ).all()
    if not runs:
        return {"items": []}

    # Keep the newest run per week_start.
    latest_by_week: Dict[date_type, WeeklyPlanRun] = {}
    for run in runs:
        if run.week_start not in latest_by_week:
            latest_by_week[run.week_start] = run

    selected = list(latest_by_week.values())[:weeks]
    selected.sort(key=lambda r: r.week_start)
    items = []
    for run in selected:
        avg_likelihood = session.exec(
            select(func.avg(WeeklyPlanItem.order_likelihood_score)).where(
                WeeklyPlanItem.plan_run_id == run.id,
            )
        ).one()
        items.append(
            {
                "run_id": run.id,
                "week_start": run.week_start.isoformat(),
                "average_order_likelihood": float(avg_likelihood or 0),
                "total_items": run.total_items,
            }
        )
    return {"items": items}


@router.get("/rules", response_model=List[ReminderRuleResponse])
async def get_reminder_rules(
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """Get all reminder rules (configuration)."""
    rules = session.exec(select(ReminderRule).order_by(ReminderRule.entity_type, ReminderRule.rule_name)).all()
    return [_reminder_rule_to_response(rule) for rule in rules]


@router.get("/outreach-sends", response_model=OutreachSendListResponse)
async def list_outreach_sends(
    channel: Optional[CustomerOutreachChannel] = Query(None),
    target_type: Optional[OutreachSendTargetType] = Query(None),
    customer_id: Optional[int] = Query(None, ge=1),
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=200),
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """List automated reminder-rule SMS/email sends with filtering and pagination."""
    if current_user.role != UserRole.DIRECTOR:
        raise HTTPException(status_code=403, detail="Only directors can view automated outreach sends")

    where_clauses = []
    if channel is not None:
        where_clauses.append(CustomerOutreachSend.channel == channel.value)
    if target_type == OutreachSendTargetType.LEAD:
        where_clauses.append(CustomerOutreachSend.quote_id.is_(None))
    elif target_type == OutreachSendTargetType.QUOTE:
        where_clauses.append(CustomerOutreachSend.quote_id.is_not(None))
    if customer_id is not None:
        where_clauses.append(CustomerOutreachSend.customer_id == customer_id)

    count_statement = select(func.count(CustomerOutreachSend.id))
    if where_clauses:
        count_statement = count_statement.where(and_(*where_clauses))
    total = int(session.exec(count_statement).one())

    statement = (
        select(
            CustomerOutreachSend,
            ReminderRule.rule_name,
            Customer.name,
            Lead.name,
            Quote.quote_number,
        )
        .join(ReminderRule, ReminderRule.id == CustomerOutreachSend.reminder_rule_id)
        .outerjoin(Customer, Customer.id == CustomerOutreachSend.customer_id)
        .outerjoin(Lead, Lead.id == CustomerOutreachSend.lead_id)
        .outerjoin(Quote, Quote.id == CustomerOutreachSend.quote_id)
    )
    if where_clauses:
        statement = statement.where(and_(*where_clauses))
    statement = statement.order_by(col(CustomerOutreachSend.sent_at).desc(), col(CustomerOutreachSend.id).desc())
    statement = statement.offset((page - 1) * page_size).limit(page_size)

    rows = session.exec(statement).all()
    items: List[OutreachSendListItemResponse] = []
    for send, rule_name, customer_name, lead_name, quote_number in rows:
        items.append(
            OutreachSendListItemResponse(
                id=send.id,
                reminder_rule_id=send.reminder_rule_id,
                reminder_rule_name=rule_name,
                customer_id=send.customer_id,
                customer_name=customer_name,
                channel=send.channel,
                target_type=OutreachSendTargetType.QUOTE if send.quote_id is not None else OutreachSendTargetType.LEAD,
                lead_id=send.lead_id,
                lead_name=lead_name,
                quote_id=send.quote_id,
                quote_number=quote_number,
                external_message_id=send.external_message_id,
                status=getattr(send, "status", "SENT"),
                failure_reason=getattr(send, "failure_reason", None),
                sent_at=send.sent_at,
            )
        )

    return OutreachSendListResponse(items=items, total=total, page=page, page_size=page_size)


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

    if body.threshold_minutes < 0:
        raise HTTPException(status_code=400, detail="threshold_minutes cannot be negative")

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

    on_create = bool(body.customer_outreach_on_lead_create) if entity == "LEAD" else False
    if entity != "LEAD" and body.customer_outreach_on_lead_create:
        raise HTTPException(
            status_code=400,
            detail="customer_outreach_on_lead_create applies only to LEAD rules",
        )
    if on_create and not och:
        raise HTTPException(
            status_code=400,
            detail="customer_outreach_on_lead_create requires customer outreach channel and template",
        )

    rule = ReminderRule(
        rule_name=rule_name,
        entity_type=entity,
        status=status_val,
        threshold_minutes=body.threshold_minutes,
        check_type=check_type,
        is_active=body.is_active,
        priority=body.priority,
        suggested_action=body.suggested_action,
        customer_outreach_channel=och,
        customer_outreach_sms_template_id=ost,
        customer_outreach_email_template_id=oet,
        customer_outreach_cooldown_days=ocd,
        outreach_enabled_from_utc=datetime.utcnow() if och else None,
        customer_outreach_on_lead_create=on_create,
    )
    session.add(rule)
    suppress = session.get(DeletedReminderRuleName, rule_name)
    if suppress:
        session.delete(suppress)
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

    prev_channel = (rule.customer_outreach_channel or "").strip().upper() if rule.customer_outreach_channel else None
    
    if rule_update.threshold_minutes is not None:
        if rule_update.threshold_minutes < 0:
            raise HTTPException(status_code=400, detail="threshold_minutes cannot be negative")
        rule.threshold_minutes = rule_update.threshold_minutes
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
                rule.customer_outreach_on_lead_create = False
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
    new_channel = (rule.customer_outreach_channel or "").strip().upper() if rule.customer_outreach_channel else None
    if not prev_channel and new_channel:
        rule.outreach_enabled_from_utc = datetime.utcnow()
    elif prev_channel and not new_channel:
        rule.outreach_enabled_from_utc = None

    if rule_update.customer_outreach_on_lead_create is not None:
        if rule.entity_type != "LEAD":
            if rule_update.customer_outreach_on_lead_create:
                raise HTTPException(
                    status_code=400,
                    detail="customer_outreach_on_lead_create applies only to LEAD rules",
                )
        else:
            rule.customer_outreach_on_lead_create = rule_update.customer_outreach_on_lead_create
            new_ch = (rule.customer_outreach_channel or "").strip().upper()
            if rule.customer_outreach_on_lead_create and new_ch not in (
                CustomerOutreachChannel.SMS.value,
                CustomerOutreachChannel.EMAIL.value,
            ):
                raise HTTPException(
                    status_code=400,
                    detail="customer_outreach_on_lead_create requires customer outreach channel and template",
                )

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

    # Clean up outreach audit rows first so FK constraints do not block delete.
    sends = session.exec(
        select(CustomerOutreachSend).where(CustomerOutreachSend.reminder_rule_id == rule.id)
    ).all()
    for send in sends:
        session.delete(send)

    name = rule.rule_name
    session.delete(rule)
    existing_suppress = session.get(DeletedReminderRuleName, name)
    if not existing_suppress:
        session.add(DeletedReminderRuleName(rule_name=name))
    session.commit()
    return {"message": "Reminder rule deleted", "id": rule_id}
