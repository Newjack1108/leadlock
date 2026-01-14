from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from app.database import create_db_and_tables, engine
from sqlmodel import Session
from app.routers import auth, leads, dashboard, webhooks, products, settings, quotes, customers, emails
from sqlmodel import Session, select
from app.models import User
import os

app = FastAPI(title="LeadLock API", version="1.0.0")

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://localhost:3001",
        "https://leadlock-frontend-production.up.railway.app",
        "https://leadlock-production.up.railway.app",  # Backend URL (if needed)
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

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
