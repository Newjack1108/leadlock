"""
Resolve and enrich stale reference dates/labels for reminders and weekly plan items.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional, Tuple

from sqlmodel import Session

from app.models import (
    Lead,
    Order,
    Quote,
    Reminder,
    ReminderRule,
    ReminderType,
    WeeklyPlanItem,
)
def _get_last_activity_date(customer_id: Optional[int], session: Session) -> Optional[datetime]:
    from app.reminder_service import get_last_activity_date

    return get_last_activity_date(customer_id, session)


def _label_for_check_type(check_type: str) -> str:
    return {
        "LAST_ACTIVITY": "Last activity",
        "STATUS_DURATION": "In status since",
        "SENT_DATE": "Quote sent",
        "VALID_UNTIL": "Quote expired",
        "SENT_NOT_OPENED": "Quote sent",
        "OPENED_NO_REPLY": "Quote opened",
    }.get(check_type, "Stale since")


def _label_for_opportunity_reason(reason: str) -> str:
    return {
        "OVERDUE_NEXT_ACTION": "Next action due",
        "CLOSE_DATE_PASSED": "Expected close",
        "QUOTE_SENT_SOFT_NUDGE": "Quote sent",
        "QUOTE_SENT_FIRM_FOLLOWUP": "Quote sent",
        "QUOTE_SENT_ESCALATION": "Quote sent",
        "NO_ACTIVITY": "Last activity",
    }.get(reason, "Stale since")


def resolve_stale_reference_for_lead(
    lead: Lead,
    rule: ReminderRule,
    session: Session,
) -> Tuple[Optional[datetime], str]:
    label = _label_for_check_type(rule.check_type)
    if rule.check_type == "LAST_ACTIVITY":
        ref = _get_last_activity_date(lead.customer_id, session)
        if not ref:
            ref = lead.updated_at or lead.created_at
        return ref, label
    if rule.check_type == "STATUS_DURATION":
        return lead.updated_at or lead.created_at, label
    return lead.updated_at or lead.created_at, label


def resolve_stale_reference_for_quote(
    quote: Quote,
    rule: ReminderRule,
) -> Tuple[Optional[datetime], str]:
    label = _label_for_check_type(rule.check_type)
    if rule.check_type == "SENT_DATE":
        return quote.sent_at, label
    if rule.check_type == "VALID_UNTIL":
        return quote.valid_until, label
    if rule.check_type == "STATUS_DURATION":
        return quote.updated_at or quote.created_at, label
    if rule.check_type == "SENT_NOT_OPENED":
        return quote.sent_at, label
    if rule.check_type == "OPENED_NO_REPLY":
        return quote.viewed_at, label
    return quote.updated_at or quote.created_at, label


def resolve_stale_reference_for_opportunity(
    quote: Quote,
    reason: str,
    session: Session,
) -> Tuple[Optional[datetime], str]:
    label = _label_for_opportunity_reason(reason)
    if reason == "OVERDUE_NEXT_ACTION":
        return quote.next_action_due_date, label
    if reason == "CLOSE_DATE_PASSED":
        return quote.expected_close_date, label
    if reason.startswith("QUOTE_SENT_"):
        return quote.sent_at, label
    if reason == "NO_ACTIVITY":
        if quote.customer_id:
            ref = _get_last_activity_date(quote.customer_id, session)
            if ref:
                return ref, label
        return quote.created_at, label
    return quote.updated_at or quote.created_at, label


def resolve_stale_reference_for_order(order: Order) -> Tuple[Optional[datetime], str]:
    return order.installation_completed_at, "Installation completed"


def _infer_quote_reference_from_reminder_type(
    quote: Quote,
    reminder_type: ReminderType,
) -> Tuple[Optional[datetime], str]:
    if reminder_type == ReminderType.QUOTE_NOT_OPENED:
        return quote.sent_at, "Quote sent"
    if reminder_type == ReminderType.QUOTE_OPENED_NO_REPLY:
        return quote.viewed_at, "Quote opened"
    if reminder_type == ReminderType.QUOTE_EXPIRED:
        return quote.valid_until, "Quote expired"
    if quote.sent_at:
        return quote.sent_at, "Quote sent"
    return quote.updated_at or quote.created_at, "In status since"


def enrich_reminder_stale_fields(
    reminder: Reminder,
    session: Session,
) -> Tuple[Optional[datetime], str]:
    if reminder.stale_reference_at and reminder.stale_source_label:
        return reminder.stale_reference_at, reminder.stale_source_label

    if reminder.reminder_type == ReminderType.REQUEST_REVIEW and reminder.order_id:
        order = session.get(Order, reminder.order_id)
        if order:
            return resolve_stale_reference_for_order(order)

    if reminder.lead_id:
        lead = session.get(Lead, reminder.lead_id)
        if lead:
            ref = _get_last_activity_date(lead.customer_id, session)
            if not ref:
                ref = lead.updated_at or lead.created_at
            return ref, "Last activity"

    if reminder.quote_id:
        quote = session.get(Quote, reminder.quote_id)
        if quote:
            return _infer_quote_reference_from_reminder_type(quote, reminder.reminder_type)

    return None, ""


def _reason_from_weekly_plan_codes(reason_codes: list) -> Optional[str]:
    for code in reason_codes or []:
        if isinstance(code, str) and code.startswith("reason:"):
            return code.split(":", 1)[1].upper()
    return None


def enrich_weekly_plan_item_stale_fields(
    item: WeeklyPlanItem,
    session: Session,
) -> Tuple[Optional[datetime], str, Optional[int]]:
    if item.stale_reference_at and item.stale_source_label:
        return item.stale_reference_at, item.stale_source_label, item.days_stale

    days_stale = item.days_stale
    reason_codes = item.reason_codes or []
    opp_reason = _reason_from_weekly_plan_codes(reason_codes)

    if item.quote_id:
        quote = session.get(Quote, item.quote_id)
        if quote:
            if opp_reason:
                ref, label = resolve_stale_reference_for_opportunity(quote, opp_reason, session)
            else:
                ref, label = _infer_quote_reference_from_reminder_type(quote, ReminderType.QUOTE_STALE)
            if ref and days_stale is None:
                days_stale = max(0, (datetime.utcnow() - ref).days)
            return ref, label, days_stale

    if item.lead_id:
        lead = session.get(Lead, item.lead_id)
        if lead:
            ref = _get_last_activity_date(lead.customer_id, session)
            if not ref:
                ref = lead.updated_at or lead.created_at
            if ref and days_stale is None:
                days_stale = max(0, (datetime.utcnow() - ref).days)
            return ref, "Last activity", days_stale

    return None, "", days_stale
