"""
LeadLock background worker entry point.

Run on the Railway worker service instead of uvicorn. Starts IMAP polling,
scheduled SMS, and customer outreach threads and keeps the process alive.

Usage (Railway worker service, root directory ``api``):

    python worker.py

Environment variables match the API (``DATABASE_URL``, Twilio, IMAP, etc.).
"""

from __future__ import annotations

import sys
import time
import traceback

from sqlmodel import Session

from app.background_workers import start_background_workers
from app.database import create_db_and_tables, engine


def main() -> None:
    print("LeadLock Worker starting...", file=sys.stderr, flush=True)
    print("=" * 50, file=sys.stderr, flush=True)

    try:
        create_db_and_tables()
        print("Database initialization complete", file=sys.stderr, flush=True)
    except Exception as exc:
        print(f"Database initialization failed: {exc}", file=sys.stderr, flush=True)
        print(traceback.format_exc(), file=sys.stderr, flush=True)
        sys.exit(1)

    try:
        from app.email_service import log_inbound_poll_configuration

        log_inbound_poll_configuration()
    except Exception as exc:
        print(f"Inbound config log failed (non-fatal): {exc}", file=sys.stderr, flush=True)

    try:
        from app.sms_bot_service import backfill_stop_opt_out_customers

        with Session(engine) as session:
            updated = backfill_stop_opt_out_customers(session)
        if updated:
            print(
                f"SMS STOP backfill: updated {updated} customer(s) with stop + automated opt-out flags",
                file=sys.stderr,
                flush=True,
            )
        else:
            print("SMS STOP backfill: no customer updates needed", file=sys.stderr, flush=True)
    except Exception as exc:
        print(f"SMS STOP backfill failed (non-fatal): {exc}", file=sys.stderr, flush=True)

    print("=" * 50, file=sys.stderr, flush=True)

    try:
        start_background_workers()
    except Exception as exc:
        print(f"Background workers failed to start: {exc}", file=sys.stderr, flush=True)
        print(traceback.format_exc(), file=sys.stderr, flush=True)
        sys.exit(1)

    print("All workers running. Blocking main thread.", file=sys.stderr, flush=True)
    while True:
        time.sleep(60)


if __name__ == "__main__":
    main()
