"""
Post-installation review request reminders and optional customer outreach.
"""
from __future__ import annotations

import os
import uuid
from datetime import datetime, timedelta
from typing import List, Optional, Tuple

from sqlmodel import Session, select, and_

from app.customer_outreach_service import _is_within_outreach_quiet_hours
from app.email_service import send_email, is_email_configured, _html_to_plain, build_activity_email_notes
from app.email_template_service import render_email_template
from app.models import (
    Activity,
    ActivityType,
    CompanySettings,
    Customer,
    CustomerOutreachChannel,
    Email,
    EmailDirection,
    EmailTemplate,
    Order,
    Quote,
    Reminder,
    ReminderPriority,
    ReminderType,
    SmsMessage,
    SmsDirection,
    SmsTemplate,
    SuggestedAction,
    User,
)
from app.order_audit import record_order_audit_event
from app.schemas import CustomerHistoryEventType
from app.sms_service import send_sms, normalize_phone, is_unsubscribed_recipient_error, resolve_sms_to_phone
from app.sms_template_service import render_sms_template
from app.system_user_service import get_system_user_id
from app.stale_reference_service import resolve_stale_reference_for_order
from app.review_hub_service import build_hub_url_for_order, ensure_review_hub_request
from app.review_prize_draw_service import (
    build_prize_draw_url,
    ensure_prize_draw_entry,
    is_prize_draw_enabled,
)


def build_review_template_context(
    company_settings: Optional[CompanySettings],
    order: Order,
    session: Optional[Session] = None,
) -> dict:
    """Jinja context for review request SMS/email templates."""
    hub_url = ""
    if session and order.id:
        hub_url = build_hub_url_for_order(order, session)

    prize_draw_url = ""
    prize_draw_title = ""
    if company_settings and is_prize_draw_enabled(company_settings) and session and order.id:
        entry = ensure_prize_draw_entry(order, session)
        if entry:
            prize_draw_url = build_prize_draw_url(entry.access_token)
            prize_draw_title = company_settings.review_prize_draw_title or "Monthly prize draw"
    company_ctx = {"company_name": "", "trading_name": ""}
    if company_settings:
        company_ctx = {
            "company_name": company_settings.company_name or "",
            "trading_name": company_settings.trading_name or "",
        }
    return {
        "order": {
            "order_number": order.order_number or "",
        },
        "company": company_ctx,
        "review": {
            "hub_url": hub_url,
            "google_url": (company_settings.review_google_url or "") if company_settings else "",
            "facebook_url": (company_settings.review_facebook_url or "") if company_settings else "",
            "trustpilot_url": (company_settings.review_trustpilot_url or "") if company_settings else "",
            "prize_draw_url": prize_draw_url,
            "prize_draw_title": prize_draw_title,
        },
    }


def _get_company_settings(session: Session) -> Optional[CompanySettings]:
    return session.exec(select(CompanySettings).limit(1)).first()


def _review_delay_days(settings: Optional[CompanySettings]) -> int:
    if not settings or settings.review_request_delay_days is None:
        return 3
    return max(0, int(settings.review_request_delay_days))


def _format_review_links_message(settings: Optional[CompanySettings]) -> str:
    lines = []
    if settings and settings.review_google_url:
        lines.append(f"Google: {settings.review_google_url}")
    if settings and settings.review_facebook_url:
        lines.append(f"Facebook: {settings.review_facebook_url}")
    if settings and settings.review_trustpilot_url:
        lines.append(f"Trustpilot: {settings.review_trustpilot_url}")
    if not lines:
        return "Configure review URLs in Company Settings."
    return "\n".join(lines)


def on_installation_completed(order: Order, session: Session) -> None:
    """Record completion timestamp when installation_completed flips true."""
    now = datetime.utcnow()
    order.installation_completed_at = now
    order.review_request_customer_sent_at = None
    order.review_request_customer_channel = None
    ensure_review_hub_request(order, session)
    session.add(order)


def on_installation_uncompleted(order: Order, session: Session) -> None:
    """Clear completion tracking and dismiss open review reminders."""
    order.installation_completed_at = None
    order.review_request_customer_sent_at = None
    order.review_request_customer_channel = None
    session.add(order)
    dismiss_open_review_reminders_for_order(order, session)


def dismiss_open_review_reminders_for_order(order: Order, session: Session) -> int:
    """Dismiss open REQUEST_REVIEW reminders for an order."""
    if not order.id:
        return 0
    now = datetime.utcnow()
    reminders = session.exec(
        select(Reminder).where(
            and_(
                Reminder.order_id == order.id,
                Reminder.reminder_type == ReminderType.REQUEST_REVIEW,
                Reminder.dismissed_at.is_(None),
                Reminder.acted_upon_at.is_(None),
            )
        )
    ).all()
    for reminder in reminders:
        reminder.dismissed_at = now
        session.add(reminder)
    return len(reminders)


def _has_review_reminder_for_order(session: Session, order_id: int) -> bool:
    existing = session.exec(
        select(Reminder).where(
            and_(
                Reminder.order_id == order_id,
                Reminder.reminder_type == ReminderType.REQUEST_REVIEW,
            )
        )
    ).first()
    return existing is not None


def _is_review_request_due(order: Order, settings: Optional[CompanySettings], now: Optional[datetime] = None) -> bool:
    if not order.installation_completed or not order.installation_completed_at:
        return False
    now = now or datetime.utcnow()
    due_at = order.installation_completed_at + timedelta(days=_review_delay_days(settings))
    return now >= due_at


def detect_due_review_requests(session: Session, now: Optional[datetime] = None) -> List[Order]:
    """Orders eligible for a post-install review reminder."""
    now = now or datetime.utcnow()
    settings = _get_company_settings(session)
    delay_days = _review_delay_days(settings)
    cutoff = now - timedelta(days=delay_days)

    orders = session.exec(
        select(Order).where(
            and_(
                Order.installation_completed == True,  # noqa: E712
                Order.installation_completed_at.isnot(None),
                Order.installation_completed_at <= cutoff,
            )
        )
    ).all()

    due: List[Order] = []
    for order in orders:
        if not order.id or not order.customer_id:
            continue
        if _has_review_reminder_for_order(session, order.id):
            continue
        if not _is_review_request_due(order, settings, now):
            continue
        due.append(order)
    return due


def create_review_reminder(order: Order, session: Session) -> Optional[Reminder]:
    """Create a staff reminder to request Google/Facebook/Trustpilot reviews."""
    if not order.id or not order.customer_id:
        return None
    if _has_review_reminder_for_order(session, order.id):
        return None

    settings = _get_company_settings(session)
    customer = session.get(Customer, order.customer_id)
    customer_name = customer.name if customer else "Customer"
    days_since = 0
    if order.installation_completed_at:
        days_since = max(0, (datetime.utcnow() - order.installation_completed_at).days)

    hub_url = build_hub_url_for_order(order, session)
    if hub_url:
        links_block = f"Customer review link: {hub_url}"
        if settings and is_prize_draw_enabled(settings):
            links_block += (
                "\n\nThe same page includes the monthly prize draw when the customer has left reviews."
            )
    else:
        links_block = _format_review_links_message(settings)

    ref_at, ref_label = resolve_stale_reference_for_order(order)
    reminder = Reminder(
        reminder_type=ReminderType.REQUEST_REVIEW,
        order_id=order.id,
        customer_id=order.customer_id,
        assigned_to_id=order.created_by_id,
        priority=ReminderPriority.MEDIUM,
        title=f"Request review: {customer_name}",
        message=(
            f"Installation completed for order {order.order_number}. "
            f"Ask {customer_name} for a Google, Facebook, or Trustpilot review.\n\n"
            f"{links_block}"
        ),
        suggested_action=SuggestedAction.REQUEST_REVIEW,
        days_stale=days_since,
        stale_reference_at=ref_at,
        stale_source_label=ref_label,
    )
    session.add(reminder)
    session.flush()
    return reminder


def _normalize_review_channel(channel: Optional[str]) -> Optional[str]:
    if not channel:
        return None
    normalized = channel.strip().lower()
    if normalized == "sms":
        return CustomerOutreachChannel.SMS.value
    if normalized == "email":
        return CustomerOutreachChannel.EMAIL.value
    return None


def _channel_has_review_template(settings: CompanySettings, channel: str) -> bool:
    if channel == CustomerOutreachChannel.SMS.value:
        return bool(settings.review_request_sms_template_id)
    if channel == CustomerOutreachChannel.EMAIL.value:
        return bool(settings.review_request_email_template_id)
    return False


def _resolve_outreach_channel(
    settings: CompanySettings,
    *,
    channel: Optional[str] = None,
    allow_fallback: bool = True,
) -> Optional[str]:
    explicit = _normalize_review_channel(channel)
    if explicit:
        if _channel_has_review_template(settings, explicit):
            return explicit
        return None

    preferred = _normalize_review_channel(getattr(settings, "review_request_outreach_channel", None) or "sms")
    if not preferred:
        preferred = CustomerOutreachChannel.SMS.value

    if _channel_has_review_template(settings, preferred):
        return preferred

    if not allow_fallback:
        return None

    other = (
        CustomerOutreachChannel.EMAIL.value
        if preferred == CustomerOutreachChannel.SMS.value
        else CustomerOutreachChannel.SMS.value
    )
    if _channel_has_review_template(settings, other):
        return other
    return None


def _resolve_actor_user(session: Session, order: Order) -> Optional[User]:
    if order.created_by_id:
        user = session.get(User, order.created_by_id)
        if user:
            return user
    env_id = (os.getenv("CUSTOMER_OUTREACH_ACTOR_USER_ID") or os.getenv("WEBHOOK_DEFAULT_USER_ID") or "").strip()
    if env_id:
        try:
            user = session.get(User, int(env_id))
            if user:
                return user
        except ValueError:
            pass
    system_id = get_system_user_id(session)
    if system_id:
        return session.get(User, system_id)
    return None


def _generate_thread_id(message_id: Optional[str], in_reply_to: Optional[str]) -> str:
    if in_reply_to:
        return in_reply_to.split("@")[0] if in_reply_to else str(uuid.uuid4())
    return str(uuid.uuid4())


def send_review_request_to_customer(
    order: Order,
    session: Session,
    *,
    actor_user: Optional[User] = None,
    force: bool = False,
    channel: Optional[str] = None,
) -> Tuple[bool, Optional[str]]:
    """
    Send automated review request SMS or email to the customer.
    Returns (success, error_message).
    """
    if order.review_request_customer_sent_at and not force:
        return False, "Review request already sent to customer"

    settings = _get_company_settings(session)
    if not settings:
        return False, "Company settings not found"
    if not force and not settings.review_request_customer_outreach_enabled:
        return False, "Customer review outreach is disabled"

    if not order.customer_id:
        return False, "Order has no customer"

    customer = session.get(Customer, order.customer_id)
    if not customer:
        return False, "Customer not found"

    if customer.automated_reminder_outreach_opt_out:
        return False, "Customer opted out of automated reminder messages"

    explicit_channel = _normalize_review_channel(channel)
    resolved_channel = _resolve_outreach_channel(
        settings,
        channel=channel,
        allow_fallback=explicit_channel is None,
    )
    if not resolved_channel:
        if explicit_channel:
            label = "SMS" if explicit_channel == CustomerOutreachChannel.SMS.value else "email"
            return False, f"Review request {label} template is not configured"
        return False, "No review request SMS or email template configured"
    channel = resolved_channel

    if _is_within_outreach_quiet_hours(settings):
        return False, "Skipped during outreach quiet hours (23:00-06:00 local company timezone)"

    actor = actor_user or _resolve_actor_user(session, order)
    if not actor:
        return False, "No actor user for review request outreach"

    quote = session.exec(select(Quote).where(Quote.id == order.quote_id)).first()
    lead_id = quote.lead_id if quote else None
    ensure_prize_draw_entry(order, session)
    template_ctx = build_review_template_context(settings, order, session)
    now = datetime.utcnow()

    if channel == CustomerOutreachChannel.SMS.value:
        template = session.get(SmsTemplate, settings.review_request_sms_template_id)
        if not template:
            return False, "SMS template not found"
        to_phone = (customer.phone or "").strip()
        if not to_phone and lead_id:
            to_phone = resolve_sms_to_phone(session, customer, lead_id=lead_id) or ""
        if not to_phone:
            return False, "No phone number for customer"

        body = render_sms_template(
            template,
            customer,
            user=actor,
            company_settings=settings,
            extra_context=template_ctx,
        )
        success, sid, error = send_sms(to_phone, body)
        if not success:
            if is_unsubscribed_recipient_error(error):
                customer.automated_reminder_outreach_opt_out = True
                session.add(customer)
            return False, error or "Failed to send SMS"

        from_phone = (os.getenv("TWILIO_PHONE_NUMBER") or "").strip()
        session.add(
            SmsMessage(
                customer_id=customer.id,
                lead_id=lead_id,
                direction=SmsDirection.SENT,
                from_phone=from_phone,
                to_phone=normalize_phone(to_phone),
                body=body,
                twilio_sid=sid,
                sent_at=now,
                created_by_id=actor.id,
            )
        )
        session.add(
            Activity(
                customer_id=customer.id,
                activity_type=ActivityType.SMS_SENT,
                notes=(
                    f"Post-install review request for order {order.order_number} sent by SMS "
                    f"to {to_phone}\n{body}"
                ),
                created_by_id=actor.id,
            )
        )
        order.review_request_customer_channel = CustomerOutreachChannel.SMS.value
    else:
        template = session.get(EmailTemplate, settings.review_request_email_template_id)
        if not template:
            return False, "Email template not found"
        to_email = (customer.email or "").strip()
        if not to_email:
            return False, "No email address for customer"
        if customer.wrong_email_address:
            return False, "Marked as wrong email address"

        actor_id = actor.id
        if not is_email_configured(actor_id):
            return False, "Email not configured for outreach actor"

        subject, body_html = render_email_template(template, customer, custom_variables=template_ctx)
        body_text = _html_to_plain(body_html)
        success, message_id, error, sent_html, sent_text = send_email(
            to_email=to_email,
            subject=subject,
            body_html=body_html,
            body_text=body_text,
            user_id=actor_id,
            customer_number=customer.customer_number,
        )
        if not success:
            return False, error or "Failed to send email"

        final_html = sent_html or body_html
        final_text = sent_text if sent_text is not None else body_text
        thread_id = _generate_thread_id(message_id, None)
        session.add(
            Email(
                customer_id=customer.id,
                lead_id=lead_id,
                direction=EmailDirection.SENT,
                from_email=actor.email or "",
                to_email=to_email,
                subject=subject,
                body_html=final_html,
                body_text=final_text,
                message_id=message_id,
                thread_id=thread_id,
                sent_at=now,
                created_by_id=actor_id,
            )
        )
        session.add(
            Activity(
                customer_id=customer.id,
                activity_type=ActivityType.EMAIL_SENT,
                notes=build_activity_email_notes(
                    f"Post-install review request for order {order.order_number} sent to {to_email}",
                    subject,
                    final_text,
                    final_html,
                ),
                created_by_id=actor_id,
            )
        )
        order.review_request_customer_channel = CustomerOutreachChannel.EMAIL.value

    order.review_request_customer_sent_at = now
    session.add(order)
    record_order_audit_event(
        session,
        event_type=CustomerHistoryEventType.ORDER_REVIEW_REQUEST_SENT.value,
        title="Review Request Sent",
        description=f"Post-install review request sent to customer for order {order.order_number}",
        order=order,
        metadata={
            "channel": order.review_request_customer_channel,
            "sent_at": now.isoformat(),
        },
        created_by_id=actor.id,
    )
    return True, None


def process_review_request_for_order(
    order: Order,
    session: Session,
    *,
    send_customer: bool = True,
) -> bool:
    """Create staff reminder and optionally send customer outreach. Returns True if reminder created."""
    reminder = create_review_reminder(order, session)
    if not reminder:
        return False

    settings = _get_company_settings(session)
    if send_customer and settings and settings.review_request_customer_outreach_enabled:
        send_review_request_to_customer(order, session)

    return True


def run_review_request_cycle(session: Session) -> int:
    """Background worker: process all due post-install review requests."""
    count = 0
    for order in detect_due_review_requests(session):
        if process_review_request_for_order(order, session):
            count += 1
    if count:
        session.commit()
    return count


def generate_review_reminders(session: Session) -> int:
    """Create due review reminders (used by manual Generate on Reminders page)."""
    count = 0
    for order in detect_due_review_requests(session):
        if create_review_reminder(order, session):
            count += 1
    return count
