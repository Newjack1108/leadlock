import json

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

from app.json_datetime import json_dumps_utf8, normalize_json_datetimes
from app.database import create_db_and_tables, engine
from sqlmodel import Session, select
from app.routers import auth, leads, dashboard, reports, webhooks, products, settings, quotes, customers, emails, email_templates, quote_templates, sms_templates, reminders, discounts, discount_requests, sms, messenger, public, public_configurator, delivery_install, orders, customer_files, users, sales_documents, facebook_adverts, dealer_portal, dealer_discount_admin, configurator, configurator_invites
from app.models import User
import os
import traceback
import shutil
from pathlib import Path

app = FastAPI(title="LeadLock API", version="1.0.0")

# Setup static files directory for logos and other assets
static_dir = Path(__file__).parent.parent / "static"
static_dir.mkdir(exist_ok=True)

# Copy logo from frontend public folder if it exists and static doesn't have it
_web_public = Path(__file__).parent.parent.parent / "web" / "public"
for _logo_name in ("logo1.jpg", "logo1.png"):
    _src = _web_public / _logo_name
    _dst = static_dir / _logo_name
    if _src.exists() and not _dst.exists():
        try:
            shutil.copy2(_src, _dst)
            print(f"Copied logo from {_src} to {_dst}", file=__import__('sys').stderr, flush=True)
        except Exception as e:
            print(f"Warning: Could not copy logo: {e}", file=__import__('sys').stderr, flush=True)

# Mount static files
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

# CORS: os.getenv("CORS_ORIGINS", default) does NOT use default when the var is set but empty
# (common in dashboards). Empty list => no Access-Control-Allow-Origin on any response.
# Production domains are always merged in so a partial CORS_ORIGINS env cannot drop the live site.
_REQUIRED_CORS_ORIGINS = (
    "http://localhost:3000",
    "http://localhost:3001",
    "https://leadlock-frontend-production.up.railway.app",
    "https://leadlock-production.up.railway.app",
    "https://www.csgbsales.co.uk",
    "https://csgbsales.co.uk",
)
_raw_cors = os.getenv("CORS_ORIGINS", "").strip()
_cors_from_env = [origin.strip() for origin in _raw_cors.split(",") if origin.strip()]
allowed_origins = list(dict.fromkeys([*_REQUIRED_CORS_ORIGINS, *_cors_from_env]))

_sys = __import__("sys")
if os.getenv("DEBUG", "false").lower() == "true" or not os.getenv("RAILWAY_ENVIRONMENT"):
    print(f"CORS allowed origins: {allowed_origins}", file=_sys.stderr, flush=True)
elif os.getenv("RAILWAY_ENVIRONMENT"):
    _cors_msg = f"CORS: {len(allowed_origins)} allowed origin(s)"
    if not _raw_cors:
        _cors_msg += " (using defaults; CORS_ORIGINS unset/blank)"
    print(_cors_msg, file=_sys.stderr, flush=True)

# CORS middleware - must be added before routers
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["*"],
    expose_headers=["*"],
)


class UtcIsoJsonMiddleware(BaseHTTPMiddleware):
    """Append Z to naive ISO datetimes in JSON so clients interpret values as UTC."""

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        ct = response.headers.get("content-type", "")
        if "application/json" not in ct or response.status_code == 204:
            return response
        chunks: list[bytes] = []
        async for chunk in response.body_iterator:
            chunks.append(chunk)
        body = b"".join(chunks)
        if not body:
            return Response(
                content=body,
                status_code=response.status_code,
                headers=dict(response.headers),
                media_type=response.media_type,
            )
        try:
            data = json.loads(body)
        except json.JSONDecodeError:
            return Response(
                content=body,
                status_code=response.status_code,
                headers=dict(response.headers),
                media_type=response.media_type,
            )
        fixed = normalize_json_datetimes(data)
        new_body = json_dumps_utf8(fixed)
        out_headers = {k: v for k, v in response.headers.items() if k.lower() != "content-length"}
        return Response(
            content=new_body,
            status_code=response.status_code,
            headers=out_headers,
            media_type=response.media_type,
        )


app.add_middleware(UtcIsoJsonMiddleware)

# Global exception handler to ensure CORS headers are always present on errors
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Global exception handler that ensures CORS headers are always present."""
    import sys
    
    # Don't handle HTTPException - let FastAPI handle it (it already has CORS support)
    if isinstance(exc, HTTPException):
        raise exc
    
    # Log the error
    error_msg = f"Unhandled exception: {str(exc)}"
    print(error_msg, file=sys.stderr, flush=True)
    print(traceback.format_exc(), file=sys.stderr, flush=True)
    
    # Get the origin from request headers
    origin = request.headers.get("origin")
    
    # Create response with error details
    response = JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "Internal server error", "error": str(exc) if os.getenv("DEBUG", "false").lower() == "true" else "An error occurred"}
    )
    
    # Add CORS headers manually if origin is allowed
    if origin and origin in allowed_origins:
        response.headers["Access-Control-Allow-Origin"] = origin
        response.headers["Access-Control-Allow-Credentials"] = "true"
        response.headers["Access-Control-Allow-Methods"] = "*"
        response.headers["Access-Control-Allow-Headers"] = "*"
    
    return response

# Include routers
app.include_router(auth.router)
app.include_router(leads.router)
app.include_router(dashboard.router)
app.include_router(reports.router)
app.include_router(webhooks.router)
app.include_router(products.router)
app.include_router(settings.router)
app.include_router(facebook_adverts.router)
app.include_router(quotes.router)
app.include_router(customers.router)
app.include_router(emails.router)
app.include_router(email_templates.router)
app.include_router(quote_templates.router)
app.include_router(sms_templates.router)
app.include_router(reminders.router)
app.include_router(discounts.router)
app.include_router(discount_requests.router)
app.include_router(sms.router)
app.include_router(messenger.router)
app.include_router(delivery_install.router)
app.include_router(orders.router)
app.include_router(customer_files.router)
app.include_router(users.router)
app.include_router(sales_documents.router)
app.include_router(public.router)
app.include_router(dealer_portal.router)
app.include_router(dealer_discount_admin.router)
app.include_router(configurator.router)
app.include_router(public_configurator.router)
app.include_router(configurator_invites.router)

# Set during background DB init (see _run_database_initialization).
_db_ready = False  # True once Postgres accepts connections (app can serve traffic).
_migrations_complete = False  # True after create_db_and_tables() finishes.
_db_init_error = None  # str when database init failed


def _run_database_initialization() -> None:
    """Run migrations/seed steps without blocking the HTTP server from accepting traffic."""
    global _db_ready, _migrations_complete, _db_init_error
    import sys

    print("LeadLock API database init (background)...", file=sys.stderr, flush=True)
    try:
        from sqlalchemy import text

        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        _db_ready = True
        _db_init_error = None
        print("Database connection OK; serving API while migrations run.", file=sys.stderr, flush=True)
    except Exception as e:
        _db_init_error = str(e)
        print("Database connection failed:", str(e), file=sys.stderr, flush=True)
        print(traceback.format_exc(), file=sys.stderr, flush=True)
        return

    try:
        from sqlalchemy import text

        with engine.begin() as conn:
            conn.execute(text("DROP TABLE IF EXISTS orderfile"))
    except Exception as e:
        print(f"Legacy orderfile drop skipped: {e}", file=sys.stderr, flush=True)
    try:
        create_db_and_tables()
        _migrations_complete = True
        print("Database initialization complete", file=sys.stderr, flush=True)
    except Exception as e:
        _db_init_error = str(e)
        print("Database migration failed:", str(e), file=sys.stderr, flush=True)
        print(traceback.format_exc(), file=sys.stderr, flush=True)
        return

    try:
        from app.email_service import log_inbound_poll_configuration

        log_inbound_poll_configuration()
    except Exception as e:
        print(f"Inbound config log failed: {e}", file=sys.stderr, flush=True)
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
    except Exception as e:
        print(f"SMS STOP backfill failed: {e}", file=sys.stderr, flush=True)

    _db_init_error = None

    _wm = os.getenv("WORKER_MODE", "").strip().lower()
    _embed_workers = _wm in ("true", "1", "yes", "on")
    if not _embed_workers:
        print(
            "Background workers (IMAP, scheduled SMS, outreach) skipped in API process. "
            "Use the worker service (python worker.py) or set WORKER_MODE=true to embed workers.",
            file=sys.stderr,
            flush=True,
        )
        return

    try:
        from app.background_workers import start_background_workers

        start_background_workers()
    except Exception as e:
        print(f"Background workers not started: {e}", file=sys.stderr, flush=True)


@app.on_event("startup")
def on_startup():
    import sys
    import threading

    print("LeadLock API startup...", file=sys.stderr, flush=True)
    db_url = os.getenv("DATABASE_URL", "")
    if not db_url.strip():
        print(
            "WARNING: DATABASE_URL is not set — API will start but all DB routes will fail. "
            "In Railway, link the Postgres plugin to this service.",
            file=sys.stderr,
            flush=True,
        )
    elif db_url.startswith("sqlite"):
        print(f"DATABASE_URL uses sqlite ({db_url[:40]}...)", file=sys.stderr, flush=True)
    else:
        # Log host only (no credentials)
        try:
            from urllib.parse import urlparse

            host = urlparse(db_url.replace("postgres://", "postgresql://", 1)).hostname
            print(f"DATABASE_URL host: {host or '(unknown)'}", file=sys.stderr, flush=True)
            if os.getenv("DATABASE_USE_PUBLIC", "").strip().lower() in ("1", "true", "yes"):
                print("DATABASE_USE_PUBLIC is enabled (TCP proxy URL).", file=sys.stderr, flush=True)
            elif host and host.endswith(".railway.internal"):
                print(
                    "Using Railway private Postgres host. If connection times out, "
                    "link API+Postgres in the same project or set DATABASE_USE_PUBLIC=true "
                    "and reference DATABASE_PUBLIC_URL from the Postgres service.",
                    file=sys.stderr,
                    flush=True,
                )
        except Exception:
            print("DATABASE_URL is set (host not parsed)", file=sys.stderr, flush=True)

    threading.Thread(target=_run_database_initialization, daemon=True).start()
    print("HTTP server ready; database init running in background.", file=sys.stderr, flush=True)


@app.get("/")
async def root():
    return {"message": "LeadLock API"}


@app.get("/health/live")
async def health_live():
    """
    Liveness probe for Railway — returns immediately without touching Postgres.
    Set the service health check path to /health/live so deploys succeed while
    migrations run in the background.
    """
    return {"status": "live"}


def _probe_database_connection():
    """Return (ok: bool, error_message: str | None)."""
    from sqlalchemy import text

    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
    return True, None


@app.get("/health")
async def health():
    """Health check for Railway/load balancers. Reports connection and migration status."""
    db_status = "initializing"
    db_detail = None
    if _db_init_error:
        db_status = "error"
        db_detail = _db_init_error
    elif _db_ready:
        try:
            _probe_database_connection()
            db_status = "ok"
        except Exception as exc:
            db_status = "error"
            db_detail = str(exc)
    else:
        # Background init not finished yet — probe live so we don't stay "initializing" forever.
        try:
            _probe_database_connection()
            db_status = "ok"
        except Exception as exc:
            db_status = "error"
            db_detail = str(exc)

    if db_status == "ok" and not _migrations_complete:
        overall = "degraded"
        migrations = "running"
    elif db_status == "ok":
        overall = "ok"
        migrations = "complete"
    elif db_status == "initializing":
        overall = "degraded"
        migrations = "pending"
    else:
        overall = "error"
        migrations = "failed" if _db_init_error else "unknown"

    payload = {
        "status": overall,
        "version": "1.0.1",
        "database": db_status,
        "migrations": migrations,
        "database_error": db_detail,
        "features": ["engagement_proof_toggle"],
    }
    if db_status == "ok":
        try:
            from sqlmodel import Session, select, func
            from app.models import Customer, Lead, User
            from app.db_utils import scalar_int

            with Session(engine) as session:
                def _count_table(model):
                    row = session.exec(select(func.count()).select_from(model)).one()
                    return scalar_int(row)

                payload["row_counts"] = {
                    "customers": _count_table(Customer),
                    "leads": _count_table(Lead),
                    "users": _count_table(User),
                }
        except Exception as exc:
            payload["row_counts_error"] = str(exc)
    return payload


@app.post("/api/seed")
@app.get("/api/seed")
async def seed_database():
    """Seed the database with initial users. Only works if no users exist."""
    # Check if users already exist
    with Session(engine) as session:
        statement = select(User)
        existing = session.exec(statement).first()
        if existing:
            raise HTTPException(status_code=400, detail="Users already exist. Database already seeded.")
        
        # Import here to avoid circular imports
        from app.models import UserRole
        from app.auth import get_password_hash
        
        users = [
            User(
                email="director@cheshirestables.com",
                hashed_password=get_password_hash("director123"),
                full_name="Director",
                role=UserRole.DIRECTOR
            ),
            User(
                email="manager@cheshirestables.com",
                hashed_password=get_password_hash("manager123"),
                full_name="Sales Manager",
                role=UserRole.SALES_MANAGER
            ),
            User(
                email="closer@cheshirestables.com",
                hashed_password=get_password_hash("closer123"),
                full_name="Closer",
                role=UserRole.CLOSER
            ),
        ]
        
        for user in users:
            session.add(user)
        
        session.commit()
        
        return {
            "message": "Database seeded successfully",
            "users": [
                {"email": "director@cheshirestables.com", "password": "director123", "role": "DIRECTOR"},
                {"email": "manager@cheshirestables.com", "password": "manager123", "role": "SALES_MANAGER"},
                {"email": "closer@cheshirestables.com", "password": "closer123", "role": "CLOSER"},
            ]
        }
