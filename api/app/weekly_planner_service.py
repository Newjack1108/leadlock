from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import List, Optional

from sqlmodel import Session, and_, desc, func, select

from app.customer_outreach_service import _is_within_outreach_quiet_hours
from app.email_service import _html_to_plain, build_activity_email_notes, is_email_configured, send_email
from app.models import (
    Activity,
    ActivityType,
    CompanySettings,
    Customer,
    Email,
    EmailDirection,
    Lead,
    LeadStatus,
    Quote,
    QuoteStatus,
    ReminderPriority,
    SuggestedAction,
    SmsDirection,
    SmsMessage,
    User,
    WeeklyPlanItem,
    WeeklyPlanItemStatus,
    WeeklyPlanRun,
    WeeklyPlanScope,
)
from app.reminder_service import (
    calculate_days_stale,
    detect_stale_leads,
    detect_stale_opportunities,
    detect_stale_quotes,
)
from app.sms_service import normalize_phone, send_sms
from app.system_user_service import get_system_user_id


def _week_start_utc(today: Optional[date] = None) -> date:
    d = today or datetime.utcnow().date()
    return d - timedelta(days=d.weekday())


def _priority_weight(priority: ReminderPriority) -> Decimal:
    mapping = {
        ReminderPriority.LOW: Decimal("5"),
        ReminderPriority.MEDIUM: Decimal("12"),
        ReminderPriority.HIGH: Decimal("22"),
        ReminderPriority.URGENT: Decimal("35"),
    }
    return mapping.get(priority, Decimal("10"))


def _value_weight(quote: Optional[Quote]) -> Decimal:
    if not quote or quote.total_amount is None:
        return Decimal("0")
    amount = Decimal(quote.total_amount)
    if amount >= Decimal("15000"):
        return Decimal("18")
    if amount >= Decimal("8000"):
        return Decimal("12")
    if amount >= Decimal("3000"):
        return Decimal("7")
    return Decimal("3")


def _probability_weight(quote: Optional[Quote]) -> Decimal:
    if not quote or quote.close_probability is None:
        return Decimal("0")
    cp = Decimal(quote.close_probability)
    return max(Decimal("0"), min(Decimal("15"), cp / Decimal("7")))


def _default_message(action: SuggestedAction, customer_name: str, quote_number: Optional[str]) -> str:
    if action == SuggestedAction.PHONE_CALL:
        return f"Hi {customer_name}, just checking in to see if you had any questions."
    if action == SuggestedAction.RESEND_QUOTE and quote_number:
        return f"Hi {customer_name}, following up on quote {quote_number}. Happy to resend and tweak details."
    if action == SuggestedAction.REVIEW_QUOTE and quote_number:
        return f"Hi {customer_name}, would you like us to refresh quote {quote_number} with updated options?"
    return f"Hi {customer_name}, just a quick follow-up from the team."


def generate_weekly_plan(
    session: Session,
    *,
    generated_by_id: Optional[int] = None,
    auto_execute: bool = True,
    dry_run: bool = False,
) -> WeeklyPlanRun:
    week_start = _week_start_utc()
    run = WeeklyPlanRun(
        week_start=week_start,
        generated_by_id=generated_by_id,
        scope=WeeklyPlanScope.FULL_PIPELINE,
        model_version="deterministic-v1",
    )
    session.add(run)
    session.flush()

    plan_items: List[WeeklyPlanItem] = []
    seen_keys: set[tuple[str, int]] = set()

    for lead, rule, days_stale in detect_stale_leads(session):
        if not lead.id:
            continue
        key = ("lead", lead.id)
        if key in seen_keys:
            continue
        seen_keys.add(key)
        score = Decimal("25") + Decimal(days_stale) + _priority_weight(rule.priority)
        reason_codes = [f"lead_status:{lead.status.value}", "stale_lead"]
        if days_stale >= 7:
            reason_codes.append("no_recent_activity")
        action = rule.suggested_action
        channel = "CALL" if action == SuggestedAction.PHONE_CALL else "EMAIL"
        auto_eligible = action in (SuggestedAction.FOLLOW_UP, SuggestedAction.CONTACT_CUSTOMER) and channel == "EMAIL"
        customer_name = lead.name or "there"
        plan_items.append(
            WeeklyPlanItem(
                plan_run_id=run.id,
                lead_id=lead.id,
                customer_id=lead.customer_id,
                assigned_to_id=lead.assigned_to_id,
                priority_score=min(Decimal("100"), score),
                confidence=Decimal("0.72"),
                reason_codes=reason_codes,
                recommended_action=action,
                channel=channel,
                auto_eligible=auto_eligible,
                suggested_message=_default_message(action, customer_name, None),
                due_date=datetime.utcnow().date() + timedelta(days=2),
            )
        )

    quote_by_id = {}
    for quote, rule, days_stale in detect_stale_quotes(session):
        if not quote.id:
            continue
        quote_by_id[quote.id] = quote
        key = ("quote", quote.id)
        if key in seen_keys:
            continue
        seen_keys.add(key)
        score = Decimal("22") + Decimal(days_stale) + _priority_weight(rule.priority) + _value_weight(quote) + _probability_weight(quote)
        reason_codes = [f"quote_status:{quote.status.value}", "stale_quote"]
        if quote.sent_at and calculate_days_stale(quote.sent_at) >= 7:
            reason_codes.append("quote_decay_risk")
        action = rule.suggested_action
        channel = "SMS" if action in (SuggestedAction.RESEND_QUOTE, SuggestedAction.CONTACT_CUSTOMER) else "CALL"
        auto_eligible = channel in ("SMS", "EMAIL") and action in (SuggestedAction.RESEND_QUOTE, SuggestedAction.CONTACT_CUSTOMER)
        customer_name = "there"
        if quote.customer_id:
            customer = session.get(Customer, quote.customer_id)
            if customer and customer.name:
                customer_name = customer.name
        plan_items.append(
            WeeklyPlanItem(
                plan_run_id=run.id,
                quote_id=quote.id,
                lead_id=quote.lead_id,
                customer_id=quote.customer_id,
                assigned_to_id=quote.owner_id or quote.created_by_id,
                priority_score=min(Decimal("100"), score),
                confidence=Decimal("0.8"),
                reason_codes=reason_codes,
                recommended_action=action,
                channel=channel,
                auto_eligible=auto_eligible,
                suggested_message=_default_message(action, customer_name, quote.quote_number),
                due_date=datetime.utcnow().date() + timedelta(days=2),
            )
        )

    for opp, reason, days_overdue in detect_stale_opportunities(session):
        if not opp.id:
            continue
        key = ("opp", opp.id)
        if key in seen_keys:
            continue
        seen_keys.add(key)
        score = Decimal("30") + Decimal(days_overdue * 2) + _value_weight(opp) + _probability_weight(opp)
        reason_codes = ["stale_opportunity", f"reason:{reason.lower()}"]
        action = SuggestedAction.FOLLOW_UP if days_overdue < 10 else SuggestedAction.REVIEW_QUOTE
        channel = "CALL" if days_overdue >= 7 else "EMAIL"
        customer_name = "there"
        if opp.customer_id:
            customer = session.get(Customer, opp.customer_id)
            if customer and customer.name:
                customer_name = customer.name
        plan_items.append(
            WeeklyPlanItem(
                plan_run_id=run.id,
                quote_id=opp.id,
                lead_id=opp.lead_id,
                customer_id=opp.customer_id,
                assigned_to_id=opp.owner_id or opp.created_by_id,
                priority_score=min(Decimal("100"), score),
                confidence=Decimal("0.75"),
                reason_codes=reason_codes,
                recommended_action=action,
                channel=channel,
                auto_eligible=channel == "EMAIL" and action == SuggestedAction.FOLLOW_UP,
                suggested_message=_default_message(action, customer_name, opp.quote_number),
                due_date=datetime.utcnow().date() + timedelta(days=1),
            )
        )

    plan_items.sort(key=lambda item: (item.priority_score, item.created_at), reverse=True)
    for item in plan_items:
        session.add(item)

    run.total_items = len(plan_items)
    run.auto_eligible_items = sum(1 for item in plan_items if item.auto_eligible)
    session.add(run)
    session.commit()
    session.refresh(run)

    if auto_execute and not dry_run:
        execute_auto_eligible_items(session, run.id)
        session.refresh(run)

    return run


def execute_auto_eligible_items(session: Session, run_id: int) -> int:
    run = session.get(WeeklyPlanRun, run_id)
    if not run:
        return 0

    company = session.exec(select(CompanySettings).limit(1)).first()
    if _is_within_outreach_quiet_hours(company):
        return 0

    items = session.exec(
        select(WeeklyPlanItem)
        .where(
            WeeklyPlanItem.plan_run_id == run_id,
            WeeklyPlanItem.auto_eligible.is_(True),
            WeeklyPlanItem.status == WeeklyPlanItemStatus.PENDING_REVIEW,
        )
        .order_by(desc(WeeklyPlanItem.priority_score))
        .limit(25)
    ).all()

    sent_count = 0
    for item in items:
        if not item.customer_id:
            continue
        customer = session.get(Customer, item.customer_id)
        if not customer:
            continue
        if customer.automated_reminder_outreach_opt_out:
            item.status = WeeklyPlanItemStatus.REJECTED
            item.execution_error = "Customer opted out of automated reminder outreach"
            item.updated_at = datetime.utcnow()
            session.add(item)
            continue
        assignee = session.get(User, item.assigned_to_id) if item.assigned_to_id else None
        actor_id = item.assigned_to_id or run.generated_by_id or get_system_user_id(session)
        now = datetime.utcnow()

        try:
            if item.channel == "SMS":
                phone = (customer.phone or "").strip()
                if not phone:
                    raise ValueError("Customer has no phone number")
                success, sid, err = send_sms(phone, item.suggested_message or "Quick follow-up from the team.")
                if not success:
                    raise ValueError(err or "SMS send failed")
                session.add(
                    SmsMessage(
                        customer_id=customer.id,
                        lead_id=item.lead_id,
                        direction=SmsDirection.SENT,
                        from_phone="",
                        to_phone=normalize_phone(phone),
                        body=item.suggested_message or "",
                        twilio_sid=sid,
                        sent_at=now,
                        created_by_id=actor_id,
                    )
                )
                session.add(
                    Activity(
                        customer_id=customer.id,
                        activity_type=ActivityType.SMS_SENT,
                        notes=f"Weekly planner auto-SMS\n{item.suggested_message or ''}",
                        created_by_id=actor_id,
                    )
                )
            elif item.channel == "EMAIL":
                to_email = (customer.email or "").strip()
                if not to_email:
                    raise ValueError("Customer has no email")
                if not assignee or not is_email_configured(assignee.id):
                    raise ValueError("Assignee email not configured")
                subject = "Quick follow-up from LeadLock"
                body_html = f"<p>{(item.suggested_message or 'Quick follow-up from the team.')}</p>"
                success, message_id, err, sent_html, sent_text = send_email(
                    to_email=to_email,
                    subject=subject,
                    body_html=body_html,
                    body_text=_html_to_plain(body_html),
                    user_id=assignee.id,
                    customer_number=customer.customer_number,
                )
                if not success:
                    raise ValueError(err or "Email send failed")
                session.add(
                    Email(
                        customer_id=customer.id,
                        message_id=message_id,
                        direction=EmailDirection.SENT,
                        from_email=assignee.email,
                        to_email=to_email,
                        subject=subject,
                        body_html=sent_html or body_html,
                        body_text=sent_text or _html_to_plain(body_html),
                        sent_at=now,
                        created_by_id=actor_id,
                        thread_id=f"weekly-plan-{item.id}",
                    )
                )
                session.add(
                    Activity(
                        customer_id=customer.id,
                        activity_type=ActivityType.EMAIL_SENT,
                        notes=build_activity_email_notes(
                            "Weekly planner auto-email",
                            subject,
                            sent_text or _html_to_plain(body_html),
                            sent_html or body_html,
                        ),
                        created_by_id=actor_id,
                    )
                )
            else:
                continue

            item.status = WeeklyPlanItemStatus.AUTO_SENT
            item.executed_at = now
            item.execution_error = None
            item.updated_at = now
            sent_count += 1
            session.add(item)
        except Exception as exc:
            item.status = WeeklyPlanItemStatus.AUTO_FAILED
            item.execution_error = str(exc)[:1000]
            item.updated_at = datetime.utcnow()
            session.add(item)

    run.auto_sent_items = sent_count
    session.add(run)
    session.commit()
    return sent_count


def mark_plan_item_outcome(
    session: Session,
    item_id: int,
    *,
    status: Optional[WeeklyPlanItemStatus] = None,
    outcome_result: Optional[str] = None,
    response_received: Optional[bool] = None,
) -> Optional[WeeklyPlanItem]:
    item = session.get(WeeklyPlanItem, item_id)
    if not item:
        return None
    if status is not None:
        item.status = status
    if outcome_result is not None:
        item.outcome_result = outcome_result
    if response_received is not None:
        item.response_received = response_received
    item.updated_at = datetime.utcnow()
    session.add(item)
    session.commit()
    session.refresh(item)
    return item


def get_plan_metrics(session: Session, run_id: int) -> dict:
    run = session.get(WeeklyPlanRun, run_id)
    if not run:
        return {}
    total = run.total_items
    done = session.exec(
        select(func.count(WeeklyPlanItem.id)).where(
            WeeklyPlanItem.plan_run_id == run_id,
            WeeklyPlanItem.status.in_([WeeklyPlanItemStatus.COMPLETED, WeeklyPlanItemStatus.AUTO_SENT]),
        )
    ).one()
    replied = session.exec(
        select(func.count(WeeklyPlanItem.id)).where(
            WeeklyPlanItem.plan_run_id == run_id,
            WeeklyPlanItem.response_received.is_(True),
        )
    ).one()
    return {
        "run_id": run.id,
        "week_start": run.week_start,
        "total_items": total,
        "auto_eligible_items": run.auto_eligible_items,
        "auto_sent_items": run.auto_sent_items,
        "completed_items": int(done or 0),
        "response_received_items": int(replied or 0),
        "completion_rate_pct": float((Decimal(done or 0) / Decimal(total) * Decimal("100")) if total else Decimal("0")),
    }
