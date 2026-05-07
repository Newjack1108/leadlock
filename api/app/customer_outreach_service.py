"""
Background evaluation: send customer SMS/email when reminder rules match stale leads/quotes.

Lead outreach prerequisites (stale worker and immediate-on-create):
- Linked Customer (``lead.customer_id``); webhook intake creates/links via ``find_or_create_customer``.
- SMS recipient: ``customer.phone``, falling back to ``lead.phone`` when the template sends for that lead.
- Actor user (SMTP, template variables): ``CUSTOMER_OUTREACH_ACTOR_USER_ID``, ``WEBHOOK_DEFAULT_USER_ID``, assignee/quote owner, then System user (``get_system_user_id``). Email outreach may still require ``CUSTOMER_OUTREACH_ACTOR_USER_ID`` if the System account has no mail configured.
- Activity and stored message ``created_by_id`` use the System user (``app.system_user_service``).
- Long-running API process running the customer outreach thread (see ``CUSTOMER_OUTREACH_INTERVAL``); immediate sends run inline on lead create.
"""
from __future__ import annotations

import os
import sys
import uuid
from datetime import datetime, timedelta, timezone
from typing import List, Optional, Tuple
from zoneinfo import ZoneInfo

from sqlalchemy import and_, desc, not_, or_
from sqlmodel import Session, select, col

from app.email_service import send_email, is_email_configured, _html_to_plain, build_activity_email_notes
from app.system_user_service import get_system_user_id
from app.email_template_service import render_email_template
from app.models import (
    Activity,
    ActivityType,
    Customer,
    CustomerOutreachChannel,
    CustomerOutreachSend,
    Email,
    EmailDirection,
    EmailTemplate,
    Lead,
    LeadStatus,
    Order,
    Quote,
    ReminderRule,
    SmsMessage,
    SmsDirection,
    SmsTemplate,
    User,
    CompanySettings,
)
from app.reminder_service import detect_stale_leads, detect_stale_quotes, get_last_activity_date
from app.sms_service import (
    send_sms,
    normalize_phone,
    get_twilio_config,
    is_unsubscribed_recipient_error,
)
from app.sms_template_service import render_sms_template

_CUSTOMER_OUTREACH_OPTOUT_REASON = "Customer opted out of automated reminder messages"
_OUTREACH_NO_ACTOR_REASON = (
    "No outreach actor user (set CUSTOMER_OUTREACH_ACTOR_USER_ID or WEBHOOK_DEFAULT_USER_ID, assign the "
    "lead/quote, or ensure System user exists)"
)
_OUTREACH_QUIET_HOURS_REASON = (
    "Skipped during outreach quiet hours (23:00-06:00 local company timezone)"
)
_OUTREACH_WRONG_EMAIL_REASON = "Marked as wrong email address"
QUIET_HOURS_AUDIT_PREFIX = "QUIET_HOURS_AUDIT:"
_OUTREACH_QUIET_HOURS_START = 23  # 23:00 local
_OUTREACH_QUIET_HOURS_END = 6  # 06:00 local


def _meaningful_customer_outreach_attempt_clause():
    """
    Rows logged only for visibility during quiet hours must not block cooldown or de-dupe.
    Prefix quiet-hours stubs with QUIET_HOURS_AUDIT: and exclude them here.
    """
    prefix_pattern = f"{QUIET_HOURS_AUDIT_PREFIX}%"
    return or_(
        CustomerOutreachSend.status == "SENT",
        and_(
            CustomerOutreachSend.status == "FAILED",
            or_(
                CustomerOutreachSend.failure_reason.is_(None),
                not_(CustomerOutreachSend.failure_reason.like(prefix_pattern)),
            ),
        ),
    )


def _generate_thread_id(message_id: Optional[str], in_reply_to: Optional[str]) -> str:
    if in_reply_to:
        return in_reply_to.split("@")[0] if in_reply_to else str(uuid.uuid4())
    return str(uuid.uuid4())


def _rule_outreach_ready(rule: ReminderRule) -> bool:
    ch = (rule.customer_outreach_channel or "").strip().upper()
    if ch == CustomerOutreachChannel.SMS.value:
        return bool(rule.customer_outreach_sms_template_id)
    if ch == CustomerOutreachChannel.EMAIL.value:
        return bool(rule.customer_outreach_email_template_id)
    return False


def _log_outreach_suppression(
    *,
    reason: str,
    rule_id: Optional[int],
    customer_id: Optional[int],
    lead_id: Optional[int],
    quote_id: Optional[int],
) -> None:
    print(
        "Customer outreach suppressed: "
        f"reason={reason} rule_id={rule_id} customer_id={customer_id} "
        f"lead_id={lead_id} quote_id={quote_id} ts_utc={datetime.utcnow().isoformat()}",
        file=sys.stderr,
        flush=True,
    )


def _is_within_outreach_quiet_hours(company: Optional[CompanySettings]) -> bool:
    """
    Block automated reminder outreach between 23:00 and 06:00 local company time.
    Falls back to Europe/London when timezone is missing/invalid.
    """
    timezone_name = "Europe/London"
    if company and company.sms_bot_timezone and company.sms_bot_timezone.strip():
        timezone_name = company.sms_bot_timezone.strip()

    now_utc = datetime.now(timezone.utc)
    try:
        local_hour = now_utc.astimezone(ZoneInfo(timezone_name)).hour
    except Exception:
        # Safe fallback: if timezone parsing fails, apply quiet hours in UTC.
        local_hour = now_utc.hour

    return local_hour >= _OUTREACH_QUIET_HOURS_START or local_hour < _OUTREACH_QUIET_HOURS_END


def _cooldown_blocks(
    session: Session,
    rule: ReminderRule,
    *,
    lead_id: Optional[int],
    quote_id: Optional[int],
) -> bool:
    cd = rule.customer_outreach_cooldown_days if rule.customer_outreach_cooldown_days is not None else 14
    if cd <= 0:
        return False
    statement = select(CustomerOutreachSend).where(
        CustomerOutreachSend.reminder_rule_id == rule.id,
    )
    if lead_id is not None:
        statement = statement.where(CustomerOutreachSend.lead_id == lead_id)
    else:
        statement = statement.where(CustomerOutreachSend.quote_id == quote_id)
    statement = statement.where(_meaningful_customer_outreach_attempt_clause())
    statement = statement.order_by(desc(CustomerOutreachSend.sent_at)).limit(1)
    last = session.exec(statement).first()
    if not last:
        return False
    return (datetime.utcnow() - last.sent_at) < timedelta(days=cd)


def _attempt_already_recorded(
    session: Session,
    rule: ReminderRule,
    *,
    lead_id: Optional[int],
    quote_id: Optional[int],
    channel: str,
) -> bool:
    statement = select(CustomerOutreachSend).where(
        CustomerOutreachSend.reminder_rule_id == rule.id,
        CustomerOutreachSend.channel == channel,
    )
    if lead_id is not None:
        statement = statement.where(
            CustomerOutreachSend.lead_id == lead_id,
            CustomerOutreachSend.quote_id.is_(None),
        )
    else:
        statement = statement.where(CustomerOutreachSend.quote_id == quote_id)
    statement = statement.where(_meaningful_customer_outreach_attempt_clause())
    return session.exec(statement.limit(1)).first() is not None


def _lead_stale_reference_timestamp(session: Session, lead: Lead, rule: ReminderRule) -> Optional[datetime]:
    if rule.check_type == "LAST_ACTIVITY":
        last_activity = get_last_activity_date(lead.customer_id, session)
        return last_activity or lead.updated_at or lead.created_at
    if rule.check_type == "STATUS_DURATION":
        return lead.updated_at or lead.created_at
    return lead.updated_at or lead.created_at


def _quote_stale_reference_timestamp(quote: Quote, rule: ReminderRule) -> Optional[datetime]:
    if rule.check_type == "SENT_DATE":
        return quote.sent_at
    if rule.check_type == "VALID_UNTIL":
        return quote.valid_until
    if rule.check_type == "STATUS_DURATION":
        return quote.updated_at or quote.created_at
    if rule.check_type == "SENT_NOT_OPENED":
        return quote.sent_at
    if rule.check_type == "OPENED_NO_REPLY":
        return quote.viewed_at
    return quote.updated_at or quote.created_at


def _resolve_actor_user_id(session: Session, lead: Optional[Lead], quote: Optional[Quote]) -> Optional[int]:
    env_id = (os.getenv("CUSTOMER_OUTREACH_ACTOR_USER_ID") or "").strip()
    if env_id:
        try:
            uid = int(env_id)
            u = session.get(User, uid)
            if u:
                return uid
        except ValueError:
            pass
    fallback = (os.getenv("WEBHOOK_DEFAULT_USER_ID") or "").strip()
    if fallback:
        try:
            uid = int(fallback)
            u = session.get(User, uid)
            if u:
                return uid
        except ValueError:
            pass
    if lead and lead.assigned_to_id:
        return lead.assigned_to_id
    if quote:
        if quote.owner_id:
            return quote.owner_id
        return quote.created_by_id
    try:
        return get_system_user_id(session)
    except Exception:
        return None


def _quote_email_variables(quote: Quote) -> dict:
    return {
        "quote": {
            "id": quote.id,
            "quote_number": quote.quote_number or "",
            "total_amount": str(quote.total_amount) if quote.total_amount is not None else "",
            "status": quote.status.value if quote.status else "",
        }
    }


def _customer_opted_out_of_rule_outreach(session: Session, customer_id: int) -> bool:
    """Fresh existence check so we do not rely on a possibly stale Customer in the session identity map."""
    stmt = (
        select(Customer.id)
        .where(
            Customer.id == customer_id,
            Customer.automated_reminder_outreach_opt_out.is_(True),
        )
        .limit(1)
    )
    return session.exec(stmt).first() is not None


def _wrong_email_marked_for_outreach(
    session: Session,
    *,
    customer_id: int,
    lead_id: Optional[int],
) -> bool:
    customer_stmt = (
        select(Customer.id)
        .where(
            Customer.id == customer_id,
            Customer.wrong_email_address.is_(True),
        )
        .limit(1)
    )
    if session.exec(customer_stmt).first() is not None:
        return True
    if lead_id is None:
        return False
    lead_stmt = (
        select(Lead.id)
        .where(
            Lead.id == lead_id,
            Lead.wrong_email_address.is_(True),
        )
        .limit(1)
    )
    return session.exec(lead_stmt).first() is not None


def _quote_outreach_superseded_by_later_order(session: Session, quote: Quote, customer_id: int) -> bool:
    """
    True if the customer already has an order placed on or after this quote's outreach reference time
    (sent_at, else created_at), so stale SENT quotes should not keep triggering rule outreach.
    """
    ref = quote.sent_at or quote.created_at
    if ref is None:
        return False
    stmt = (
        select(Order.id)
        .join(Quote, Quote.id == Order.quote_id)
        .where(Quote.customer_id == customer_id, Order.created_at >= ref)
        .limit(1)
    )
    return session.exec(stmt).first() is not None


def _send_outreach_sms(
    session: Session,
    *,
    rule: ReminderRule,
    customer: Customer,
    lead: Optional[Lead],
    quote: Optional[Quote],
    actor: User,
    company: Optional[CompanySettings],
) -> Tuple[bool, Optional[str], Optional[str]]:
    if customer.id is not None and _customer_opted_out_of_rule_outreach(session, customer.id):
        return False, None, _CUSTOMER_OUTREACH_OPTOUT_REASON
    tid = rule.customer_outreach_sms_template_id
    if not tid:
        return False, None, "No SMS template"
    template = session.get(SmsTemplate, tid)
    if not template:
        return False, None, "SMS template not found"
    sid, token, from_phone = get_twilio_config()
    if not sid or not token or not from_phone:
        return False, None, "Twilio not configured"

    to_phone = (customer.phone or "").strip() or ((lead.phone or "").strip() if lead else "")
    if not to_phone:
        return (
            False,
            None,
            "No phone number on customer or lead; SMS outreach is disabled until a number is added",
        )

    body = render_sms_template(template, customer, user=actor, company_settings=company)
    if customer.id is not None and _customer_opted_out_of_rule_outreach(session, customer.id):
        return False, None, _CUSTOMER_OUTREACH_OPTOUT_REASON
    success, twilio_sid, err = send_sms(to_phone, body)
    if not success:
        return False, None, err or "send_sms failed"

    system_uid = get_system_user_id(session)
    msg = SmsMessage(
        customer_id=customer.id,
        lead_id=lead.id if lead else None,
        direction=SmsDirection.SENT,
        from_phone=from_phone or "",
        to_phone=normalize_phone(to_phone),
        body=body,
        twilio_sid=twilio_sid,
        sent_at=datetime.utcnow(),
        created_by_id=system_uid,
    )
    session.add(msg)
    session.add(
        Activity(
            customer_id=customer.id,
            activity_type=ActivityType.SMS_SENT,
            notes=f"Automated SMS (rule {rule.rule_name}) to {to_phone}\n{body}",
            created_by_id=system_uid,
        )
    )
    return True, twilio_sid, None


def _send_outreach_email(
    session: Session,
    *,
    rule: ReminderRule,
    customer: Customer,
    lead: Optional[Lead],
    quote: Optional[Quote],
    actor: User,
) -> Tuple[bool, Optional[str], Optional[str]]:
    if customer.id is not None and _customer_opted_out_of_rule_outreach(session, customer.id):
        return False, None, _CUSTOMER_OUTREACH_OPTOUT_REASON
    if customer.id is not None and _wrong_email_marked_for_outreach(
        session,
        customer_id=customer.id,
        lead_id=lead.id if lead else None,
    ):
        return False, None, _OUTREACH_WRONG_EMAIL_REASON
    tid = rule.customer_outreach_email_template_id
    if not tid:
        return False, None, "No email template"
    template = session.get(EmailTemplate, tid)
    if not template:
        return False, None, "Email template not found"
    to_email = (customer.email or "").strip() or (lead.email if lead and lead.email else None)
    if not to_email:
        return False, None, "No email address"

    if not is_email_configured(actor.id):
        return False, None, "Email not configured for actor user"

    extra = {}
    if quote:
        extra.update(_quote_email_variables(quote))
    subject, body_html = render_email_template(template, customer, custom_variables=extra or None)
    body_text = _html_to_plain(body_html) if body_html else None

    if customer.id is not None and _customer_opted_out_of_rule_outreach(session, customer.id):
        return False, None, _CUSTOMER_OUTREACH_OPTOUT_REASON
    if customer.id is not None and _wrong_email_marked_for_outreach(
        session,
        customer_id=customer.id,
        lead_id=lead.id if lead else None,
    ):
        return False, None, _OUTREACH_WRONG_EMAIL_REASON
    success, message_id, err, sent_html, sent_text = send_email(
        to_email=to_email,
        subject=subject,
        body_html=body_html,
        body_text=body_text,
        user_id=actor.id,
        customer_number=customer.customer_number,
    )
    if not success:
        return False, None, err or "send_email failed"

    system_uid = get_system_user_id(session)
    email_record = Email(
        customer_id=customer.id,
        message_id=message_id,
        direction=EmailDirection.SENT,
        from_email=actor.email,
        to_email=to_email,
        subject=subject,
        body_html=sent_html or body_html,
        body_text=sent_text if sent_text is not None else body_text,
        sent_at=datetime.utcnow(),
        created_by_id=system_uid,
        thread_id=_generate_thread_id(message_id, None),
    )
    session.add(email_record)
    session.add(
        Activity(
            customer_id=customer.id,
            activity_type=ActivityType.EMAIL_SENT,
            notes=build_activity_email_notes(
                f"Automated email (rule {rule.rule_name}) to {to_email}",
                subject,
                sent_text if sent_text is not None else body_text,
                sent_html or body_html,
            ),
            created_by_id=system_uid,
        )
    )
    return True, message_id, None


def _deliver_lead_customer_outreach_once(
    session: Session,
    *,
    company: Optional[CompanySettings],
    lead: Lead,
    rule: ReminderRule,
) -> bool:
    """Send SMS/email for one lead/rule pair; commit on success or logged failure. Returns True if sent."""
    ch = (rule.customer_outreach_channel or "").strip().upper()
    if not lead.customer_id:
        return False
    customer = session.get(Customer, lead.customer_id)
    if not customer:
        return False
    if _customer_opted_out_of_rule_outreach(session, lead.customer_id):
        print(
            f"Customer outreach: skip lead {lead.id} rule {rule.id}: "
            f"customer {customer.id} opted out of automated reminder messages",
            file=sys.stderr,
            flush=True,
        )
        return False
    actor_id = _resolve_actor_user_id(session, lead, None)
    if not actor_id:
        print(
            f"Customer outreach: skip lead {lead.id} rule {rule.id}: no actor user",
            file=sys.stderr,
            flush=True,
        )
        session.add(
            CustomerOutreachSend(
                reminder_rule_id=rule.id,
                customer_id=customer.id,
                channel=ch,
                lead_id=lead.id,
                quote_id=None,
                external_message_id=None,
                status="FAILED",
                failure_reason=_OUTREACH_NO_ACTOR_REASON[:1000],
                sent_at=datetime.utcnow(),
            )
        )
        session.commit()
        return False
    actor = session.get(User, actor_id)
    if not actor:
        print(
            f"Customer outreach: skip lead {lead.id} rule {rule.id}: actor user missing id={actor_id}",
            file=sys.stderr,
            flush=True,
        )
        session.add(
            CustomerOutreachSend(
                reminder_rule_id=rule.id,
                customer_id=customer.id,
                channel=ch,
                lead_id=lead.id,
                quote_id=None,
                external_message_id=None,
                status="FAILED",
                failure_reason=_OUTREACH_NO_ACTOR_REASON[:1000],
                sent_at=datetime.utcnow(),
            )
        )
        session.commit()
        return False

    external_id: Optional[str] = None
    ok = False
    err_msg: Optional[str] = None
    try:
        if ch == CustomerOutreachChannel.SMS.value:
            ok, external_id, err_msg = _send_outreach_sms(
                session,
                rule=rule,
                customer=customer,
                lead=lead,
                quote=None,
                actor=actor,
                company=company,
            )
        elif ch == CustomerOutreachChannel.EMAIL.value:
            ok, external_id, err_msg = _send_outreach_email(
                session,
                rule=rule,
                customer=customer,
                lead=lead,
                quote=None,
                actor=actor,
            )
        else:
            return False
    except Exception as e:  # noqa: BLE001
        err_msg = str(e)
        print(f"Customer outreach error lead {lead.id} rule {rule.id}: {e}", file=sys.stderr, flush=True)
        session.rollback()
        return False

    if not ok:
        if err_msg == _CUSTOMER_OUTREACH_OPTOUT_REASON:
            _log_outreach_suppression(
                reason="opt_out_enabled",
                rule_id=rule.id,
                customer_id=customer.id,
                lead_id=lead.id,
                quote_id=None,
            )
            return False
        if err_msg == _OUTREACH_WRONG_EMAIL_REASON:
            _log_outreach_suppression(
                reason="wrong_email_marked",
                rule_id=rule.id,
                customer_id=customer.id,
                lead_id=lead.id,
                quote_id=None,
            )
            return False
        if err_msg:
            if ch == CustomerOutreachChannel.SMS.value and is_unsubscribed_recipient_error(err_msg):
                customer.automated_reminder_outreach_opt_out = True
                session.add(customer)
            session.add(
                CustomerOutreachSend(
                    reminder_rule_id=rule.id,
                    customer_id=customer.id,
                    channel=ch,
                    lead_id=lead.id,
                    quote_id=None,
                    external_message_id=None,
                    status="FAILED",
                    failure_reason=(err_msg or "send failed")[:1000],
                    sent_at=datetime.utcnow(),
                )
            )
            session.commit()
            print(
                f"Customer outreach skip lead {lead.id} rule {rule.rule_name}: {err_msg}",
                file=sys.stderr,
                flush=True,
            )
        return False

    log = CustomerOutreachSend(
        reminder_rule_id=rule.id,
        customer_id=customer.id,
        channel=ch,
        lead_id=lead.id,
        quote_id=None,
        external_message_id=external_id,
        status="SENT",
        failure_reason=None,
        sent_at=datetime.utcnow(),
    )
    session.add(log)
    session.commit()
    return True


def try_customer_outreach_for_new_lead(session: Session, lead: Lead) -> int:
    """
    Run outreach rules configured with customer_outreach_on_lead_create for this lead's status.
    Called after persisting a new lead (webhook, UI create, Facebook Lead Ads, etc.).
    """
    if not lead.id:
        return 0
    company = session.exec(select(CompanySettings).limit(1)).first()
    statement = (
        select(ReminderRule)
        .where(
            ReminderRule.entity_type == "LEAD",
            ReminderRule.is_active == True,  # noqa: E712
            ReminderRule.customer_outreach_on_lead_create == True,
        )
        .order_by(ReminderRule.id)
    )
    rules = session.exec(statement).all()
    eligible: List[Tuple[ReminderRule, str]] = []
    for rule in rules:
        if not rule.status:
            continue
        try:
            rule_status = LeadStatus(rule.status)
        except ValueError:
            continue
        if lead.status != rule_status:
            continue
        if not _rule_outreach_ready(rule):
            continue
        if not lead.customer_id:
            continue
        enabled_from = getattr(rule, "outreach_enabled_from_utc", None)
        if enabled_from is not None and lead.created_at < enabled_from:
            continue
        ch = (rule.customer_outreach_channel or "").strip().upper()
        if _attempt_already_recorded(session, rule, lead_id=lead.id, quote_id=None, channel=ch):
            continue
        if _cooldown_blocks(session, rule, lead_id=lead.id, quote_id=None):
            continue
        eligible.append((rule, ch))

    if _is_within_outreach_quiet_hours(company):
        if eligible:
            now_ts = datetime.utcnow()
            for rule, ch in eligible:
                session.add(
                    CustomerOutreachSend(
                        reminder_rule_id=rule.id,
                        customer_id=lead.customer_id,
                        channel=ch,
                        lead_id=lead.id,
                        quote_id=None,
                        external_message_id=None,
                        status="FAILED",
                        failure_reason=(
                            f"{QUIET_HOURS_AUDIT_PREFIX} {_OUTREACH_QUIET_HOURS_REASON}"
                        )[:1000],
                        sent_at=now_ts,
                    )
                )
            session.commit()
            _log_outreach_suppression(
                reason="quiet_hours",
                rule_id=None,
                customer_id=lead.customer_id,
                lead_id=lead.id,
                quote_id=None,
            )
        return 0

    sent_count = 0
    for rule, _ch in eligible:
        if _deliver_lead_customer_outreach_once(session, company=company, lead=lead, rule=rule):
            sent_count += 1
    return sent_count


def run_customer_outreach_cycle(session: Session) -> int:
    """
    Evaluate stale lead/quote rules that have customer outreach configured; send at most one
    message per matching entity per run (cooldown applies across runs).
    Returns number of successful sends.
    """
    company = session.exec(select(CompanySettings).limit(1)).first()
    if _is_within_outreach_quiet_hours(company):
        return 0

    sent_count = 0
    stale_leads = detect_stale_leads(session)
    for lead, rule, _days in stale_leads:
        if not rule.is_active or not _rule_outreach_ready(rule):
            continue
        ch = (rule.customer_outreach_channel or "").strip().upper()
        if not lead.customer_id:
            continue
        enabled_from = getattr(rule, "outreach_enabled_from_utc", None)
        if enabled_from is not None:
            ref_ts = _lead_stale_reference_timestamp(session, lead, rule)
            if ref_ts is None or ref_ts < enabled_from:
                continue
        if _attempt_already_recorded(
            session,
            rule,
            lead_id=lead.id,
            quote_id=None,
            channel=ch,
        ):
            continue
        if _cooldown_blocks(session, rule, lead_id=lead.id, quote_id=None):
            continue
        if _deliver_lead_customer_outreach_once(session, company=company, lead=lead, rule=rule):
            sent_count += 1

    stale_quotes = detect_stale_quotes(session)
    for quote, rule, _days in stale_quotes:
        if not rule.is_active or not _rule_outreach_ready(rule):
            continue
        ch = (rule.customer_outreach_channel or "").strip().upper()
        if not quote.customer_id:
            continue
        enabled_from = getattr(rule, "outreach_enabled_from_utc", None)
        if enabled_from is not None:
            ref_ts = _quote_stale_reference_timestamp(quote, rule)
            if ref_ts is None or ref_ts < enabled_from:
                continue
        if _attempt_already_recorded(
            session,
            rule,
            lead_id=None,
            quote_id=quote.id,
            channel=ch,
        ):
            continue
        if _cooldown_blocks(session, rule, lead_id=None, quote_id=quote.id):
            continue
        if _customer_opted_out_of_rule_outreach(session, quote.customer_id):
            _log_outreach_suppression(
                reason="opt_out_enabled",
                rule_id=rule.id,
                customer_id=quote.customer_id,
                lead_id=quote.lead_id,
                quote_id=quote.id,
            )
            continue
        if ch == CustomerOutreachChannel.EMAIL.value and _wrong_email_marked_for_outreach(
            session,
            customer_id=quote.customer_id,
            lead_id=quote.lead_id,
        ):
            _log_outreach_suppression(
                reason="wrong_email_marked",
                rule_id=rule.id,
                customer_id=quote.customer_id,
                lead_id=quote.lead_id,
                quote_id=quote.id,
            )
            continue
        if _quote_outreach_superseded_by_later_order(session, quote, quote.customer_id):
            print(
                f"Customer outreach: skip quote {quote.id} rule {rule.id}: "
                f"customer {quote.customer_id} has a later order; stale quote outreach suppressed",
                file=sys.stderr,
                flush=True,
            )
            continue
        customer = session.get(Customer, quote.customer_id)
        if not customer:
            continue
        lead = session.get(Lead, quote.lead_id) if quote.lead_id else None
        actor_id = _resolve_actor_user_id(session, lead, quote)
        if not actor_id:
            print(
                f"Customer outreach: skip quote {quote.id} rule {rule.id}: no actor user",
                file=sys.stderr,
                flush=True,
            )
            continue
        actor = session.get(User, actor_id)
        if not actor:
            continue

        external_id = None
        ok = False
        err_msg = None
        try:
            if ch == CustomerOutreachChannel.SMS.value:
                ok, external_id, err_msg = _send_outreach_sms(
                    session,
                    rule=rule,
                    customer=customer,
                    lead=lead,
                    quote=quote,
                    actor=actor,
                    company=company,
                )
            elif ch == CustomerOutreachChannel.EMAIL.value:
                ok, external_id, err_msg = _send_outreach_email(
                    session,
                    rule=rule,
                    customer=customer,
                    lead=lead,
                    quote=quote,
                    actor=actor,
                )
        except Exception as e:  # noqa: BLE001
            err_msg = str(e)
            print(f"Customer outreach error quote {quote.id} rule {rule.id}: {e}", file=sys.stderr, flush=True)
            session.rollback()
            continue

        if not ok:
            if err_msg == _CUSTOMER_OUTREACH_OPTOUT_REASON:
                _log_outreach_suppression(
                    reason="opt_out_enabled",
                    rule_id=rule.id,
                    customer_id=customer.id,
                    lead_id=quote.lead_id,
                    quote_id=quote.id,
                )
                continue
            if err_msg == _OUTREACH_WRONG_EMAIL_REASON:
                _log_outreach_suppression(
                    reason="wrong_email_marked",
                    rule_id=rule.id,
                    customer_id=customer.id,
                    lead_id=quote.lead_id,
                    quote_id=quote.id,
                )
                continue
            if err_msg:
                if ch == CustomerOutreachChannel.SMS.value and is_unsubscribed_recipient_error(err_msg):
                    customer.automated_reminder_outreach_opt_out = True
                    session.add(customer)
                session.add(
                    CustomerOutreachSend(
                        reminder_rule_id=rule.id,
                        customer_id=customer.id,
                        channel=ch,
                        lead_id=quote.lead_id,
                        quote_id=quote.id,
                        external_message_id=None,
                        status="FAILED",
                        failure_reason=(err_msg or "send failed")[:1000],
                        sent_at=datetime.utcnow(),
                    )
                )
                session.commit()
                print(
                    f"Customer outreach skip quote {quote.id} rule {rule.rule_name}: {err_msg}",
                    file=sys.stderr,
                    flush=True,
                )
            continue

        log = CustomerOutreachSend(
            reminder_rule_id=rule.id,
            customer_id=customer.id,
            channel=ch,
            lead_id=quote.lead_id,
            quote_id=quote.id,
            external_message_id=external_id,
            status="SENT",
            failure_reason=None,
            sent_at=datetime.utcnow(),
        )
        session.add(log)
        session.commit()
        sent_count += 1

    return sent_count


def any_outreach_rules_active(session: Session) -> bool:
    statement = select(ReminderRule).where(
        ReminderRule.is_active == True,  # noqa: E712
        col(ReminderRule.customer_outreach_channel).is_not(None),
    )
    for rule in session.exec(statement).all():
        if _rule_outreach_ready(rule):
            return True
    return False
