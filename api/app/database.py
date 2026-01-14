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
    import sys
    print("Creating tables...", file=sys.stderr, flush=True)
    SQLModel.metadata.create_all(engine)
    print("Tables created/verified", file=sys.stderr, flush=True)
    
    # Add missing columns to existing Lead table if they don't exist
    # This is a simple migration approach - in production, use Alembic
    try:
        print("Checking for migration needs...", file=sys.stderr, flush=True)
        inspector = inspect(engine)
        if inspector.has_table("lead"):
            columns = [col['name'] for col in inspector.get_columns("lead")]
            print(f"Existing lead table columns: {columns}", file=sys.stderr, flush=True)
            
            columns_to_add = []
            if "company_name" not in columns:
                columns_to_add.append("company_name VARCHAR")
            if "address_line1" not in columns:
                columns_to_add.append("address_line1 VARCHAR")
            if "address_line2" not in columns:
                columns_to_add.append("address_line2 VARCHAR")
            if "city" not in columns:
                columns_to_add.append("city VARCHAR")
            if "county" not in columns:
                columns_to_add.append("county VARCHAR")
            if "country" not in columns:
                columns_to_add.append("country VARCHAR DEFAULT 'United Kingdom'")
            if "customer_since" not in columns:
                columns_to_add.append("customer_since TIMESTAMP")
            if "customer_number" not in columns:
                columns_to_add.append("customer_number VARCHAR")
            
            if columns_to_add:
                print(f"Adding {len(columns_to_add)} columns to lead table...", file=sys.stderr, flush=True)
                with engine.begin() as conn:  # begin() auto-commits
                    for col_def in columns_to_add:
                        col_name = col_def.split()[0]
                        print(f"  Adding column: {col_name}", file=sys.stderr, flush=True)
                        conn.execute(text(f"ALTER TABLE lead ADD COLUMN {col_def}"))
                print("Migration completed successfully", file=sys.stderr, flush=True)
            else:
                print("All columns already exist, no migration needed", file=sys.stderr, flush=True)
        else:
            print("Lead table does not exist yet, will be created by SQLModel", file=sys.stderr, flush=True)
    except Exception as e:
        # Log error but don't crash - migration might have already run
        import traceback
        print(f"Migration error: {e}", file=sys.stderr, flush=True)
        print(traceback.format_exc(), file=sys.stderr, flush=True)


def get_session() -> Generator[Session, None, None]:
    with Session(engine) as session:
        yield session
