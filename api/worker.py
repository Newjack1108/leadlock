"""
LeadLock background worker entry point.

Run on the Railway worker service instead of uvicorn. Starts IMAP polling,
scheduled SMS, and customer outreach threads and keeps the process alive.

Usage (Railway worker service, root directory ``api``):

    python worker.py

Environment variables match the API (``DATABASE_URL``, Twilio, IMAP, etc.).
"""

from __future__ import annotations

import json
import os
import sys
import threading
import time
import traceback
from http.server import BaseHTTPRequestHandler, HTTPServer

from sqlmodel import Session

from app.background_workers import start_background_workers
from app.database import create_db_and_tables, engine


def _start_railway_health_server() -> None:
    """
    Railway web/worker deploys often require a process listening on $PORT for health checks.
    Background workers do not run uvicorn; expose a minimal /health/live endpoint instead.
    """
    port = int(os.getenv("PORT", "8080"))

    class _Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            if self.path.split("?", 1)[0] in ("/health/live", "/health"):
                body = json.dumps({"status": "live", "service": "worker"}).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            else:
                self.send_response(404)
                self.end_headers()

        def log_message(self, *_args) -> None:
            return

    def _serve() -> None:
        server = HTTPServer(("0.0.0.0", port), _Handler)
        print(f"Worker health server on 0.0.0.0:{port} (/health/live)", file=sys.stderr, flush=True)
        server.serve_forever()

    threading.Thread(target=_serve, name="worker-health", daemon=True).start()


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

    _start_railway_health_server()

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
