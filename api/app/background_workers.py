"""Long-running background jobs (IMAP inbound poll, scheduled SMS, customer outreach).

Used by ``python worker.py`` on the worker service, or embedded in the API when
``WORKER_MODE`` is truthy (e.g. local monolith).
"""

from __future__ import annotations

import os
import re
import threading
import time
import traceback
from datetime import datetime as dt

from sqlalchemy import func
from sqlmodel import Session, select

from app.database import engine
from app.email_service import build_activity_email_notes, receive_emails
from app.email_threading import find_thread_id_for_inbound
from app.models import (
    Activity,
    ActivityType,
    Customer,
    Email,
    EmailDirection,
    ScheduledSms,
    ScheduledSmsStatus,
    SmsDirection,
    SmsMessage,
)
from app.sms_service import is_unsubscribed_recipient_error, normalize_phone, send_sms
from app.system_user_service import get_system_user_id


def start_background_workers() -> None:
    """Start IMAP polling, scheduled SMS, and customer outreach daemon threads."""

    def poll_imap() -> None:
        """Background task to poll inbox for new emails (Graph or IMAP)."""
        poll_interval = int(os.getenv("IMAP_POLL_INTERVAL", "300"))  # Default 5 minutes

        while True:
            try:
                # Receive emails (poll first so a deploy does not wait a full interval before the first run)
                received = receive_emails()
                if received:
                    print(
                        f"Inbound poll: processing {len(received)} message(s)",
                        file=__import__("sys").stderr,
                        flush=True,
                    )

                if received:
                    with Session(engine) as session:
                        for email_data in received:
                            try:
                                from_email = email_data["from_email"]
                                email_match = re.search(r"[\w\.-]+@[\w\.-]+\.\w+", from_email)
                                if not email_match:
                                    print(
                                        f"Inbound email skipped: could not parse From address: {from_email!r}",
                                        file=__import__("sys").stderr,
                                        flush=True,
                                    )
                                    continue

                                email_address = email_match.group(0).lower()

                                statement = select(Customer).where(
                                    Customer.email.isnot(None),
                                    func.lower(Customer.email) == email_address,
                                )
                                customer = session.exec(statement).first()

                                if not customer:
                                    subj = (email_data.get("subject") or "")[:120]
                                    print(
                                        f"Inbound email skipped: no Customer with email={email_address} "
                                        f"(subject={subj!r})",
                                        file=__import__("sys").stderr,
                                        flush=True,
                                    )
                                    continue

                                if email_data["message_id"]:
                                    statement = select(Email).where(Email.message_id == email_data["message_id"])
                                    existing = session.exec(statement).first()
                                    if existing:
                                        continue

                                thread_id = find_thread_id_for_inbound(
                                    session,
                                    customer.id,
                                    email_address,
                                    email_data.get("in_reply_to"),
                                    email_data.get("references"),
                                    email_data.get("subject") or "",
                                )

                                email_record = Email(
                                    customer_id=customer.id,
                                    message_id=email_data["message_id"],
                                    in_reply_to=email_data["in_reply_to"],
                                    thread_id=thread_id,
                                    direction=EmailDirection.RECEIVED,
                                    from_email=email_address,
                                    to_email=email_data["to_email"],
                                    subject=email_data["subject"],
                                    body_html=email_data["body_html"],
                                    body_text=email_data["body_text"],
                                    attachments=email_data["attachments"],
                                    received_at=email_data["received_at"],
                                )
                                session.add(email_record)
                                session.commit()
                                session.refresh(email_record)

                                activity = Activity(
                                    customer_id=customer.id,
                                    activity_type=ActivityType.EMAIL_RECEIVED,
                                    notes=build_activity_email_notes(
                                        f"Email received from {email_address}",
                                        email_data.get("subject"),
                                        email_data.get("body_text"),
                                        email_data.get("body_html"),
                                    ),
                                    created_by_id=get_system_user_id(session),
                                )
                                session.add(activity)
                                session.commit()

                            except Exception as e:
                                print(f"Error processing received email: {e}")
                                print(traceback.format_exc())
                                session.rollback()
                                continue

                time.sleep(poll_interval)
            except Exception as e:
                print(f"Error in IMAP polling: {e}")
                print(traceback.format_exc())
                time.sleep(60)

    try:
        imap_thread = threading.Thread(target=poll_imap, daemon=True)
        imap_thread.start()
        print("IMAP polling thread started", file=__import__("sys").stderr, flush=True)
    except Exception as e:
        print("IMAP thread not started:", str(e), file=__import__("sys").stderr, flush=True)

    def poll_scheduled_sms() -> None:
        poll_interval = int(os.getenv("SMS_SCHEDULER_INTERVAL", "45"))
        while True:
            try:
                time.sleep(poll_interval)
                with Session(engine) as session:
                    due_ids = list(
                        session.exec(
                            select(ScheduledSms.id)
                            .where(ScheduledSms.status == ScheduledSmsStatus.PENDING)
                            .where(ScheduledSms.scheduled_at <= dt.utcnow())
                        ).all()
                    )

                for scheduled_id in due_ids:
                    # Keep DB sessions short and avoid holding a pooled connection
                    # while waiting on Twilio/network calls.
                    with Session(engine) as session:
                        scheduled = session.get(ScheduledSms, scheduled_id)
                        if not scheduled or scheduled.status != ScheduledSmsStatus.PENDING:
                            continue

                        payload = {
                            "customer_id": scheduled.customer_id,
                            "to_phone": scheduled.to_phone,
                            "body": scheduled.body,
                            "created_by_id": scheduled.created_by_id,
                        }
                        customer = session.get(Customer, scheduled.customer_id)
                        has_customer_phone = bool(customer and (customer.phone or "").strip())

                    if has_customer_phone:
                        try:
                            success, sid, err = send_sms(payload["to_phone"], payload["body"])
                        except Exception as e:
                            success, sid, err = False, None, str(e)
                    else:
                        success, sid, err = (
                            False,
                            None,
                            "Customer has no phone number; SMS automation disabled until number is added",
                        )

                    with Session(engine) as session:
                        scheduled = session.get(ScheduledSms, scheduled_id)
                        if not scheduled or scheduled.status != ScheduledSmsStatus.PENDING:
                            continue
                        try:
                            if success:
                                from_phone = os.getenv("TWILIO_PHONE_NUMBER", "")
                                msg = SmsMessage(
                                    customer_id=payload["customer_id"],
                                    direction=SmsDirection.SENT,
                                    from_phone=from_phone,
                                    to_phone=normalize_phone(payload["to_phone"]),
                                    body=payload["body"],
                                    twilio_sid=sid,
                                    sent_at=dt.utcnow(),
                                    created_by_id=payload["created_by_id"],
                                )
                                session.add(msg)
                                activity = Activity(
                                    customer_id=payload["customer_id"],
                                    activity_type=ActivityType.SMS_SENT,
                                    notes=f"Scheduled SMS sent to {payload['to_phone']}\n{payload['body']}",
                                    created_by_id=payload["created_by_id"],
                                )
                                session.add(activity)
                                scheduled.status = ScheduledSmsStatus.SENT
                                scheduled.sent_at = dt.utcnow()
                                scheduled.twilio_sid = sid
                                session.add(scheduled)
                            else:
                                print(
                                    f"Scheduled SMS {scheduled_id} send failed: {err}",
                                    file=__import__("sys").stderr,
                                    flush=True,
                                )
                                if is_unsubscribed_recipient_error(err):
                                    customer = session.get(Customer, payload["customer_id"])
                                    if customer:
                                        customer.automated_reminder_outreach_opt_out = True
                                        session.add(customer)
                                scheduled.status = ScheduledSmsStatus.FAILED
                                scheduled.failure_reason = (err or "Twilio send failed")[:1000]
                                session.add(scheduled)
                            session.commit()
                        except Exception as e:
                            print(
                                f"Error processing scheduled SMS {scheduled_id}: {e}",
                                file=__import__("sys").stderr,
                                flush=True,
                            )
                            session.rollback()
            except Exception as e:
                print(f"Error in scheduled SMS worker: {e}", file=__import__("sys").stderr, flush=True)
                time.sleep(60)

    try:
        sms_scheduler_thread = threading.Thread(target=poll_scheduled_sms, daemon=True)
        sms_scheduler_thread.start()
        print("Scheduled SMS worker started", file=__import__("sys").stderr, flush=True)
    except Exception as e:
        print("SMS worker not started:", str(e), file=__import__("sys").stderr, flush=True)

    def poll_customer_outreach() -> None:
        from app.customer_outreach_service import any_outreach_rules_active, run_customer_outreach_cycle

        poll_interval = int(os.getenv("CUSTOMER_OUTREACH_INTERVAL", "300"))
        while True:
            try:
                time.sleep(poll_interval)
                with Session(engine) as session:
                    if not any_outreach_rules_active(session):
                        continue
                    n = run_customer_outreach_cycle(session)
                    if n:
                        print(
                            f"Customer outreach worker sent {n} message(s)",
                            file=__import__("sys").stderr,
                            flush=True,
                        )
            except Exception as e:
                print(f"Error in customer outreach worker: {e}", file=__import__("sys").stderr, flush=True)
                time.sleep(60)

    try:
        outreach_thread = threading.Thread(target=poll_customer_outreach, daemon=True)
        outreach_thread.start()
        poll_s = int(os.getenv("CUSTOMER_OUTREACH_INTERVAL", "300"))
        print(
            "Customer outreach worker started "
            f"(CUSTOMER_OUTREACH_INTERVAL={poll_s}s; set CUSTOMER_OUTREACH_ACTOR_USER_ID or "
            "WEBHOOK_DEFAULT_USER_ID when leads have no assignee)",
            file=__import__("sys").stderr,
            flush=True,
        )
    except Exception as e:
        print("Customer outreach worker not started:", str(e), file=__import__("sys").stderr, flush=True)

    def poll_weekly_planner() -> None:
        from app.weekly_planner_service import generate_weekly_plan

        poll_interval = int(os.getenv("WEEKLY_PLANNER_INTERVAL_SECONDS", str(6 * 3600)))
        enabled = os.getenv("WEEKLY_PLANNER_ENABLED", "false").strip().lower() in ("1", "true", "yes", "on")
        if not enabled:
            return
        while True:
            try:
                time.sleep(poll_interval)
                with Session(engine) as session:
                    run = generate_weekly_plan(
                        session,
                        generated_by_id=None,
                        auto_execute=os.getenv("WEEKLY_PLANNER_AUTO_EXECUTE", "true").strip().lower() in ("1", "true", "yes", "on"),
                        dry_run=os.getenv("WEEKLY_PLANNER_DRY_RUN", "false").strip().lower() in ("1", "true", "yes", "on"),
                    )
                    print(
                        f"Weekly planner generated run={run.id} items={run.total_items} auto_sent={run.auto_sent_items}",
                        file=__import__("sys").stderr,
                        flush=True,
                    )
            except Exception as e:
                print(f"Error in weekly planner worker: {e}", file=__import__("sys").stderr, flush=True)
                time.sleep(60)

    try:
        if os.getenv("WEEKLY_PLANNER_ENABLED", "false").strip().lower() in ("1", "true", "yes", "on"):
            planner_thread = threading.Thread(target=poll_weekly_planner, daemon=True)
            planner_thread.start()
            print("Weekly planner worker started", file=__import__("sys").stderr, flush=True)
    except Exception as e:
        print("Weekly planner worker not started:", str(e), file=__import__("sys").stderr, flush=True)

    def poll_review_requests() -> None:
        from app.review_request_service import run_review_request_cycle

        poll_interval = int(os.getenv("REVIEW_REQUEST_INTERVAL", "300"))
        while True:
            try:
                time.sleep(poll_interval)
                with Session(engine) as session:
                    n = run_review_request_cycle(session)
                    if n:
                        print(
                            f"Review request worker processed {n} order(s)",
                            file=__import__("sys").stderr,
                            flush=True,
                        )
            except Exception as e:
                print(f"Error in review request worker: {e}", file=__import__("sys").stderr, flush=True)
                time.sleep(60)

    try:
        review_thread = threading.Thread(target=poll_review_requests, daemon=True)
        review_thread.start()
        poll_s = int(os.getenv("REVIEW_REQUEST_INTERVAL", "300"))
        print(
            f"Review request worker started (REVIEW_REQUEST_INTERVAL={poll_s}s)",
            file=__import__("sys").stderr,
            flush=True,
        )
    except Exception as e:
        print("Review request worker not started:", str(e), file=__import__("sys").stderr, flush=True)
