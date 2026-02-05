from fastapi import FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from app.database import create_db_and_tables, engine
from sqlmodel import Session
from app.routers import auth, leads, dashboard, webhooks, products, settings, quotes, customers, emails, email_templates, sms_templates, reminders, discounts, discount_requests, sms, messenger, public
from sqlmodel import Session, select
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
frontend_logo = Path(__file__).parent.parent.parent / "web" / "public" / "logo1.jpg"
static_logo = static_dir / "logo1.jpg"
if frontend_logo.exists() and not static_logo.exists():
    try:
        shutil.copy2(frontend_logo, static_logo)
        print(f"Copied logo from {frontend_logo} to {static_logo}", file=__import__('sys').stderr, flush=True)
    except Exception as e:
        print(f"Warning: Could not copy logo: {e}", file=__import__('sys').stderr, flush=True)

# Mount static files
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

# Get allowed origins from environment or use defaults
allowed_origins_str = os.getenv(
    "CORS_ORIGINS",
    "http://localhost:3000,http://localhost:3001,https://leadlock-frontend-production.up.railway.app,https://leadlock-production.up.railway.app"
)
allowed_origins = [origin.strip() for origin in allowed_origins_str.split(",") if origin.strip()]

# Log allowed origins for debugging (only in non-production or if DEBUG is set)
if os.getenv("DEBUG", "false").lower() == "true" or not os.getenv("RAILWAY_ENVIRONMENT"):
    print(f"CORS allowed origins: {allowed_origins}", file=__import__('sys').stderr, flush=True)

# CORS middleware - must be added before routers
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["*"],
    expose_headers=["*"],
)

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
app.include_router(webhooks.router)
app.include_router(products.router)
app.include_router(settings.router)
app.include_router(quotes.router)
app.include_router(customers.router)
app.include_router(emails.router)
app.include_router(email_templates.router)
app.include_router(sms_templates.router)
app.include_router(reminders.router)
app.include_router(discounts.router)
app.include_router(discount_requests.router)
app.include_router(sms.router)
app.include_router(messenger.router)
app.include_router(public.router)


@app.on_event("startup")
def on_startup():
    print("=" * 50)
    print("Starting database initialization...")
    print("=" * 50)
    create_db_and_tables()
    print("=" * 50)
    print("Database initialization complete")
    print("=" * 50)
    
    # Start IMAP polling background task
    import threading
    import time
    from app.email_service import receive_emails
    from app.models import Email, Customer, Activity, ActivityType, EmailDirection
    from sqlmodel import select
    import re
    
    def poll_imap():
        """Background task to poll IMAP for new emails."""
        poll_interval = int(os.getenv("IMAP_POLL_INTERVAL", "300"))  # Default 5 minutes
        
        while True:
            try:
                time.sleep(poll_interval)
                
                # Receive emails
                received = receive_emails()
                
                if received:
                    with Session(engine) as session:
                        for email_data in received:
                            try:
                                # Extract email address from "From" field
                                from_email = email_data["from_email"]
                                # Extract email address (handle "Name <email@domain.com>" format)
                                email_match = re.search(r'[\w\.-]+@[\w\.-]+\.\w+', from_email)
                                if not email_match:
                                    continue
                                
                                email_address = email_match.group(0)
                                
                                # Find customer by email
                                statement = select(Customer).where(Customer.email == email_address)
                                customer = session.exec(statement).first()
                                
                                if not customer:
                                    # Skip emails from unknown customers
                                    continue
                                
                                # Check if email already exists
                                if email_data["message_id"]:
                                    statement = select(Email).where(Email.message_id == email_data["message_id"])
                                    existing = session.exec(statement).first()
                                    if existing:
                                        continue
                                
                                # Generate thread_id if in_reply_to exists
                                thread_id = None
                                if email_data["in_reply_to"]:
                                    # Try to find existing email with this message_id as thread_id
                                    statement = select(Email).where(Email.message_id == email_data["in_reply_to"])
                                    parent_email = session.exec(statement).first()
                                    if parent_email and parent_email.thread_id:
                                        thread_id = parent_email.thread_id
                                    else:
                                        thread_id = email_data["in_reply_to"]
                                
                                # Create email record
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
                                    received_at=email_data["received_at"]
                                )
                                session.add(email_record)
                                session.commit()
                                session.refresh(email_record)
                                
                                # Create EMAIL_RECEIVED activity
                                activity = Activity(
                                    customer_id=customer.id,
                                    activity_type=ActivityType.EMAIL_RECEIVED,
                                    notes=f"Email received from {email_address}: {email_data['subject']}",
                                    created_by_id=1  # System user (will need to handle this better)
                                )
                                session.add(activity)
                                session.commit()
                                
                            except Exception as e:
                                print(f"Error processing received email: {e}")
                                import traceback
                                print(traceback.format_exc())
                                session.rollback()
                                continue
                
            except Exception as e:
                print(f"Error in IMAP polling: {e}")
                import traceback
                print(traceback.format_exc())
                time.sleep(60)  # Wait 1 minute before retrying
    
    # Start background thread
    imap_thread = threading.Thread(target=poll_imap, daemon=True)
    imap_thread.start()
    print("IMAP polling thread started", file=__import__('sys').stderr, flush=True)

    # Scheduled SMS worker: send due messages every 45 seconds
    from app.models import ScheduledSms, SmsMessage, SmsDirection, ScheduledSmsStatus
    from app.sms_service import send_sms, normalize_phone
    from datetime import datetime as dt

    def poll_scheduled_sms():
        poll_interval = int(os.getenv("SMS_SCHEDULER_INTERVAL", "45"))
        while True:
            try:
                time.sleep(poll_interval)
                with Session(engine) as session:
                    statement = (
                        select(ScheduledSms)
                        .where(ScheduledSms.status == ScheduledSmsStatus.PENDING)
                        .where(ScheduledSms.scheduled_at <= dt.utcnow())
                    )
                    due = list(session.exec(statement).all())
                    for scheduled in due:
                        try:
                            success, sid, err = send_sms(scheduled.to_phone, scheduled.body)
                            if success:
                                from_phone = os.getenv("TWILIO_PHONE_NUMBER", "")
                                msg = SmsMessage(
                                    customer_id=scheduled.customer_id,
                                    direction=SmsDirection.SENT,
                                    from_phone=from_phone,
                                    to_phone=normalize_phone(scheduled.to_phone),
                                    body=scheduled.body,
                                    twilio_sid=sid,
                                    sent_at=dt.utcnow(),
                                    created_by_id=scheduled.created_by_id,
                                )
                                session.add(msg)
                                activity = Activity(
                                    customer_id=scheduled.customer_id,
                                    activity_type=ActivityType.SMS_SENT,
                                    notes=f"Scheduled SMS sent to {scheduled.to_phone}",
                                    created_by_id=scheduled.created_by_id,
                                )
                                session.add(activity)
                                scheduled.status = ScheduledSmsStatus.SENT
                                scheduled.sent_at = dt.utcnow()
                                scheduled.twilio_sid = sid
                                session.add(scheduled)
                            else:
                                print(f"Scheduled SMS {scheduled.id} send failed: {err}", file=__import__("sys").stderr, flush=True)
                            session.commit()
                        except Exception as e:
                            print(f"Error processing scheduled SMS {scheduled.id}: {e}", file=__import__("sys").stderr, flush=True)
                            session.rollback()
            except Exception as e:
                print(f"Error in scheduled SMS worker: {e}", file=__import__("sys").stderr, flush=True)
                time.sleep(60)

    sms_scheduler_thread = threading.Thread(target=poll_scheduled_sms, daemon=True)
    sms_scheduler_thread.start()
    print("Scheduled SMS worker started", file=__import__("sys").stderr, flush=True)


@app.get("/")
async def root():
    return {"message": "LeadLock API"}


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
