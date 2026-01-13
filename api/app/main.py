from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from app.database import create_db_and_tables, engine
from app.routers import auth, leads, dashboard
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
        "https://*.vercel.app",  # Vercel preview deployments
        "https://*.netlify.app",  # Netlify deployments
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(auth.router)
app.include_router(leads.router)
app.include_router(dashboard.router)


@app.on_event("startup")
def on_startup():
    create_db_and_tables()


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
