from sqlmodel import SQLModel, create_engine, Session
from sqlalchemy import inspect, text
from typing import Generator
import os
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://user:password@localhost:5432/leadlock")

engine = create_engine(DATABASE_URL, echo=True)


def create_db_and_tables():
    """Create all tables and add missing columns to existing tables."""
    SQLModel.metadata.create_all(engine)
    
    # Add missing columns to existing Lead table if they don't exist
    # This is a simple migration approach - in production, use Alembic
    try:
        inspector = inspect(engine)
        if inspector.has_table("lead"):
            columns = [col['name'] for col in inspector.get_columns("lead")]
            
            with engine.begin() as conn:  # begin() auto-commits
                if "company_name" not in columns:
                    conn.execute(text("ALTER TABLE lead ADD COLUMN company_name VARCHAR"))
                if "address_line1" not in columns:
                    conn.execute(text("ALTER TABLE lead ADD COLUMN address_line1 VARCHAR"))
                if "address_line2" not in columns:
                    conn.execute(text("ALTER TABLE lead ADD COLUMN address_line2 VARCHAR"))
                if "city" not in columns:
                    conn.execute(text("ALTER TABLE lead ADD COLUMN city VARCHAR"))
                if "county" not in columns:
                    conn.execute(text("ALTER TABLE lead ADD COLUMN county VARCHAR"))
                if "country" not in columns:
                    conn.execute(text("ALTER TABLE lead ADD COLUMN country VARCHAR DEFAULT 'United Kingdom'"))
                if "customer_since" not in columns:
                    conn.execute(text("ALTER TABLE lead ADD COLUMN customer_since TIMESTAMP"))
                if "customer_number" not in columns:
                    conn.execute(text("ALTER TABLE lead ADD COLUMN customer_number VARCHAR"))
    except Exception as e:
        # Log error but don't crash - migration might have already run
        print(f"Migration warning: {e}")


def get_session() -> Generator[Session, None, None]:
    with Session(engine) as session:
        yield session
