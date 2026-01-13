"""
Seed script to create initial users.
Run with: python seed.py
"""
from app.database import engine, create_db_and_tables
from app.models import User, UserRole
from app.auth import get_password_hash
from sqlmodel import Session, select

def seed_users():
    create_db_and_tables()
    
    with Session(engine) as session:
        # Check if users already exist
        from sqlmodel import select
        statement = select(User)
        existing = session.exec(statement).first()
        if existing:
            print("Users already exist. Skipping seed.")
            return
        
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
        print("✓ Seeded users:")
        print("  - director@cheshirestables.com / director123")
        print("  - manager@cheshirestables.com / manager123")
        print("  - closer@cheshirestables.com / closer123")

if __name__ == "__main__":
    seed_users()
