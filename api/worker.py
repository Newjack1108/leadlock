"""
LeadLock background worker entry point.

Run this instead of the FastAPI app when WORKER_MODE=true.  It starts the
three long-running background threads (IMAP polling, scheduled SMS, customer
outreach) and then blocks forever so the process stays alive.

Usage (Railway worker service):
    python worker.py

Required env vars are the same as the API service (DATABASE_URL, etc.).
WORKER_MODE is set to "true" automatically by the worker service in Railway,
but this file does not depend on it — it always starts workers directly.
"""

import os
import sys
import time
import threading
import traceback

# ---------------------------------------------------------------------------
# Bootstrap: make sure imports resolve the same way as in the API process.
# When Railway sets Root Directory = "api" the CWD is already /app (inside
# the api build context), so "app.*" imports work without any path surgery.
# ---------------------------------------------------------------------------

from app.database import create_db_and_tables, engine
from sqlmodel import Session, select
from sqlalchemy import func


def _start_imap_worker() -> threading.Thread:
    """Poll inbox for inbound emails and store them against matching customers."""

    def poll_imap():
        import re
        from app.email_service import receive_emails, build_activity_email_notes
        from app.email_threading import find_thread_id_for_inbound
        from app.models import Email, Customer, Activity, ActivityType, EmailDirection
        from app.system_user_service import get_system_user_id

        poll_interval = int(os.getenv("IMAP_POLL_INTERVAL", "300"))  # Default 5 minutes

        while True:
            try:
                received = receive_emails()
                if received:
                    print(
                        f"Inbound poll: processing {len(received)} message(s)",
                        file=sys.stderr,
                        flush=True,
                    )
                    with Session(engine) as session:
                        for email_data in received:
                            try:
                                from_email = email_data["from_email"]
                                email_match = re.search(r"[\w\.-]+@[\w\.-]+\.\w+", from_email)
                                if not email_match:
                                    print(
                                        f"Inbound email skipped: could not parse From address: {from_email!r}",
                                        file=sys.stderr,
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
                                        file=sys.stderr,
                                        flush=True,
                                    )
                                    continue

                                if email_data["message_id"]:
                                    existing = session.exec(
                                        select(Email).where(Email.message_id == email_data["message_id"])
                                    ).first()
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

                            except Exception as exc:
                                print(f"Error processing received email: {exc}", file=sys.stderr, flush=True)
                                print(traceback.format_exc(), file=sys.stderr, flush=True)
                                session.rollback()
                                continue

                time.sleep(poll_interval)
            except Exception as exc:
                print(f"Error in IMAP polling: {exc}", file=sys.stderr, flush=True)
                print(traceback.format_exc(), file=sys.stderr, flush=True)
                time.sleep(60)

    t = threading.Thread(target=poll_imap, daemon=True, name="imap-poller")
    t.start()
    return t


def _start_sms_worker() -> threading.Thread:
    """Send scheduled SMS messages as they become due."""

    def poll_scheduled_sms():
        from datetime import datetime as dt
        from app.models import (
            Activity,
            ActivityType,
            Customer,
            ScheduledSms,
            SmsMessage,
            SmsDirection,
            ScheduledSmsStatus,
        )
        from app.sms_service import send_sms, normalize_phone, is_unsubscribed_recipient_error

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
                        except Exception as exc:
                            success, sid, err = False, None, str(exc)
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
                                    file=sys.stderr,
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
                        except Exception as exc:
                            print(
                                f"Error processing scheduled SMS {scheduled_id}: {exc}",
                                file=sys.stderr,
                                flush=True,
                            )
                            session.rollback()
            except Exception as exc:
                print(f"Error in scheduled SMS worker: {exc}", file=sys.stderr, flush=True)
                time.sleep(60)

    t = threading.Thread(target=poll_scheduled_sms, daemon=True, name="sms-scheduler")
    t.start()
    return t


def _start_outreach_worker() -> threading.Thread:
    """Send automated customer outreach messages when reminder rules match stale leads/quotes."""

    def poll_customer_outreach():
        from app.customer_outreach_service import run_customer_outreach_cycle, any_outreach_rules_active

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
                            file=sys.stderr,
                            flush=True,
                        )
            except Exception as exc:
                print(f"Error in customer outreach worker: {exc}", file=sys.stderr, flush=True)
                time.sleep(60)

    t = threading.Thread(target=poll_customer_outreach, daemon=True, name="outreach-worker")
    t.start()
    return t


def main():
    print("LeadLock Worker starting...", file=sys.stderr, flush=True)
    print("=" * 50, file=sys.stderr, flush=True)

    # Initialise DB (run migrations, ensure schema is up to date)
    try:
        create_db_and_tables()
        print("Database initialisation complete", file=sys.stderr, flush=True)
    except Exception as exc:
        print(f"Database initialisation failed: {exc}", file=sys.stderr, flush=True)
        print(traceback.format_exc(), file=sys.stderr, flush=True)
        sys.exit(1)

    # SMS STOP backfill (idempotent, safe to run on every worker start)
    try:
        from app.sms_bot_service import backfill_stop_opt_out_customers

        with Session(engine) as session:
            updated = backfill_stop_opt_out_customers(session)
        if updated:
            print(
                f"SMS STOP backfill: updated {updated} customer(s)",
                file=sys.stderr,
                flush=True,
            )
        else:
            print("SMS STOP backfill: no updates needed", file=sys.stderr, flush=True)
    except Exception as exc:
        print(f"SMS STOP backfill failed (non-fatal): {exc}", file=sys.stderr, flush=True)

    # Log inbound email configuration
    try:
        from app.email_service import log_inbound_poll_configuration

        log_inbound_poll_configuration()
    except Exception as exc:
        print(f"Inbound config log failed (non-fatal): {exc}", file=sys.stderr, flush=True)

    print("=" * 50, file=sys.stderr, flush=True)

    # Start the three background workers
    try:
        _start_imap_worker()
        print("IMAP polling thread started", file=sys.stderr, flush=True)
    except Exception as exc:
        print(f"IMAP worker not started: {exc}", file=sys.stderr, flush=True)

    try:
        _start_sms_worker()
        print("Scheduled SMS worker started", file=sys.stderr, flush=True)
    except Exception as exc:
        print(f"SMS worker not started: {exc}", file=sys.stderr, flush=True)

    try:
        _start_outreach_worker()
        poll_s = int(os.getenv("CUSTOMER_OUTREACH_INTERVAL", "300"))
        print(
            f"Customer outreach worker started (CUSTOMER_OUTREACH_INTERVAL={poll_s}s)",
            file=sys.stderr,
            flush=True,
        )
    except Exception as exc:
        print(f"Customer outreach worker not started: {exc}", file=sys.stderr, flush=True)

    print("All workers running. Blocking main thread.", file=sys.stderr, flush=True)

    # Keep the process alive — daemon threads die when the main thread exits.
    while True:
        time.sleep(60)


if __name__ == "__main__":
    main()
