from sqlmodel import SQLModel, create_engine, Session, text as sql_text
from sqlalchemy import inspect, text
from typing import Generator
import os
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://user:password@localhost:5432/leadlock")

engine = create_engine(DATABASE_URL, echo=True)


def create_db_and_tables():
    """Create all tables and migrate existing data."""
    import sys
    from datetime import datetime, date
    
    print("Creating tables...", file=sys.stderr, flush=True)
    SQLModel.metadata.create_all(engine)
    print("Tables created/verified", file=sys.stderr, flush=True)
    
    # Migration logic for Customer model separation
    try:
        print("Checking for migration needs...", file=sys.stderr, flush=True)
        inspector = inspect(engine)
        
        has_customer_table = inspector.has_table("customer")
        has_lead_table = inspector.has_table("lead")
        has_activity_table = inspector.has_table("activity")
        has_quote_table = inspector.has_table("quote")
        
        # Step 1: Add customer_id to Lead table if it doesn't exist
        if has_lead_table:
            lead_columns = [col['name'] for col in inspector.get_columns("lead")]
            if "customer_id" not in lead_columns:
                print("Adding customer_id column to lead table...", file=sys.stderr, flush=True)
                with engine.begin() as conn:
                    conn.execute(text("ALTER TABLE lead ADD COLUMN customer_id INTEGER"))
                print("Added customer_id to lead table", file=sys.stderr, flush=True)
        
        # Step 2: Migrate existing qualified leads to Customer records
        if has_lead_table and has_customer_table:
            print("Migrating qualified leads to customers...", file=sys.stderr, flush=True)
            with Session(engine) as session:
                from app.models import Customer, Lead, LeadStatus
                from sqlmodel import select
                
                # Get all qualified leads that don't have a customer_id yet
                statement = select(Lead).where(
                    Lead.status == LeadStatus.QUALIFIED,
                    Lead.customer_id.is_(None)
                )
                qualified_leads = session.exec(statement).all()
                
                migrated_count = 0
                for lead in qualified_leads:
                    try:
                        # Check if customer already exists by email or phone
                        customer_statement = select(Customer).where(
                            (Customer.email == lead.email) | (Customer.phone == lead.phone)
                        )
                        existing_customer = session.exec(customer_statement).first()
                        
                        if not existing_customer:
                            # Generate customer number
                            year = date.today().year
                            num_statement = select(Customer).where(Customer.customer_number.like(f"CUST-{year}-%"))
                            existing_customers = session.exec(num_statement).all()
                            numbers = []
                            for cust in existing_customers:
                                try:
                                    num = int(cust.customer_number.split('-')[-1])
                                    numbers.append(num)
                                except (ValueError, IndexError):
                                    continue
                            next_num = max(numbers) + 1 if numbers else 1
                            customer_number = f"CUST-{year}-{next_num:03d}"
                            
                            customer = Customer(
                                customer_number=customer_number,
                                name=lead.name,
                                email=lead.email,
                                phone=lead.phone,
                                postcode=lead.postcode,
                                customer_since=datetime.utcnow()
                            )
                            session.add(customer)
                            session.flush()
                            lead.customer_id = customer.id
                        else:
                            lead.customer_id = existing_customer.id
                        
                        session.add(lead)
                        migrated_count += 1
                    except Exception as e:
                        print(f"Error migrating lead {lead.id}: {e}", file=sys.stderr, flush=True)
                        session.rollback()
                        continue
                
                session.commit()
                print(f"Migrated {migrated_count} qualified leads to customers", file=sys.stderr, flush=True)
        
        # Step 3: Create customers for all leads that have activities or quotes but no customer_id
        if has_lead_table and has_customer_table and (has_activity_table or has_quote_table):
            print("Creating customers for leads with activities/quotes...", file=sys.stderr, flush=True)
            with Session(engine) as session:
                from app.models import Customer, Lead
                from sqlmodel import select
                
                # Use raw SQL to find leads with activities/quotes (since models may have changed)
                if has_activity_table:
                    try:
                        result = session.exec(sql_text("""
                            SELECT DISTINCT lead.id 
                            FROM lead 
                            INNER JOIN activity ON activity.lead_id = lead.id 
                            WHERE lead.customer_id IS NULL
                        """))
                        lead_ids_with_activities = [row[0] for row in result]
                    except Exception as e:
                        print(f"Error finding leads with activities: {e}", file=sys.stderr, flush=True)
                        lead_ids_with_activities = []
                else:
                    lead_ids_with_activities = []
                
                if has_quote_table:
                    try:
                        result = session.exec(sql_text("""
                            SELECT DISTINCT lead.id 
                            FROM lead 
                            INNER JOIN quote ON quote.lead_id = lead.id 
                            WHERE lead.customer_id IS NULL
                        """))
                        lead_ids_with_quotes = [row[0] for row in result]
                    except Exception as e:
                        print(f"Error finding leads with quotes: {e}", file=sys.stderr, flush=True)
                        lead_ids_with_quotes = []
                else:
                    lead_ids_with_quotes = []
                
                all_lead_ids = list(set(lead_ids_with_activities + lead_ids_with_quotes))
                
                if all_lead_ids:
                    statement = select(Lead).where(Lead.id.in_(all_lead_ids))
                    leads_to_migrate = session.exec(statement).all()
                    
                    for lead in leads_to_migrate:
                        try:
                            # Check if customer already exists
                            customer_statement = select(Customer).where(
                                (Customer.email == lead.email) | (Customer.phone == lead.phone)
                            )
                            existing_customer = session.exec(customer_statement).first()
                            
                            if not existing_customer:
                                # Generate customer number
                                year = date.today().year
                                num_statement = select(Customer).where(Customer.customer_number.like(f"CUST-{year}-%"))
                                existing_customers = session.exec(num_statement).all()
                                numbers = []
                                for cust in existing_customers:
                                    try:
                                        num = int(cust.customer_number.split('-')[-1])
                                        numbers.append(num)
                                    except (ValueError, IndexError):
                                        continue
                                next_num = max(numbers) + 1 if numbers else 1
                                customer_number = f"CUST-{year}-{next_num:03d}"
                                
                                customer = Customer(
                                    customer_number=customer_number,
                                    name=lead.name,
                                    email=lead.email,
                                    phone=lead.phone,
                                    postcode=lead.postcode,
                                    customer_since=datetime.utcnow()
                                )
                                session.add(customer)
                                session.flush()
                                lead.customer_id = customer.id
                            else:
                                lead.customer_id = existing_customer.id
                            
                            session.add(lead)
                        except Exception as e:
                            print(f"Error creating customer for lead {lead.id}: {e}", file=sys.stderr, flush=True)
                            session.rollback()
                            continue
                    
                    session.commit()
                    print(f"Created customers for {len(leads_to_migrate)} leads", file=sys.stderr, flush=True)
        
        # Step 4: Migrate Activity table: lead_id -> customer_id
        if has_activity_table:
            activity_columns = [col['name'] for col in inspector.get_columns("activity")]
            has_lead_id = "lead_id" in activity_columns
            has_customer_id = "customer_id" in activity_columns
            
            if has_lead_id:
                print("Migrating Activity table from lead_id to customer_id...", file=sys.stderr, flush=True)
                try:
                    with engine.begin() as conn:
                        # Make lead_id nullable first (if it's not already)
                        try:
                            # Check if lead_id has NOT NULL constraint
                            conn.execute(text("""
                                ALTER TABLE activity ALTER COLUMN lead_id DROP NOT NULL
                            """))
                            print("Made lead_id nullable in activity table", file=sys.stderr, flush=True)
                        except Exception as null_error:
                            # Column might already be nullable or constraint doesn't exist
                            if "does not exist" not in str(null_error).lower() and "not found" not in str(null_error).lower():
                                print(f"Note: Could not modify lead_id constraint: {null_error}", file=sys.stderr, flush=True)
                        
                        # Add customer_id column if it doesn't exist
                        if not has_customer_id:
                            try:
                                conn.execute(text("ALTER TABLE activity ADD COLUMN customer_id INTEGER"))
                                print("Added customer_id column to activity table", file=sys.stderr, flush=True)
                            except Exception as col_error:
                                # Column might already exist from SQLModel.create_all()
                                if "already exists" not in str(col_error).lower() and "duplicate" not in str(col_error).lower():
                                    raise
                                print("customer_id column already exists in activity table", file=sys.stderr, flush=True)
                            
                            # Migrate data: for each activity, get customer_id from lead
                            conn.execute(text("""
                                UPDATE activity 
                                SET customer_id = (
                                    SELECT lead.customer_id
                                    FROM lead 
                                    WHERE lead.id = activity.lead_id
                                )
                                WHERE activity.lead_id IS NOT NULL
                                AND EXISTS (SELECT 1 FROM lead WHERE lead.id = activity.lead_id AND lead.customer_id IS NOT NULL)
                            """))
                            print("Migrated existing activity data to customer_id", file=sys.stderr, flush=True)
                except Exception as e:
                    print(f"Error migrating Activity table: {e}", file=sys.stderr, flush=True)
                    import traceback
                    print(traceback.format_exc(), file=sys.stderr, flush=True)
        
        # Step 5: Migrate Quote table: lead_id -> customer_id
        if has_quote_table:
            quote_columns = [col['name'] for col in inspector.get_columns("quote")]
            has_lead_id = "lead_id" in quote_columns
            has_customer_id = "customer_id" in quote_columns
            
            if has_lead_id and not has_customer_id:
                print("Migrating Quote table from lead_id to customer_id...", file=sys.stderr, flush=True)
                try:
                    with engine.begin() as conn:
                        # Add customer_id column (nullable first) - use IF NOT EXISTS equivalent
                        try:
                            conn.execute(text("ALTER TABLE quote ADD COLUMN customer_id INTEGER"))
                        except Exception as col_error:
                            # Column might already exist from SQLModel.create_all()
                            if "already exists" not in str(col_error).lower() and "duplicate" not in str(col_error).lower():
                                raise
                            print("customer_id column already exists in quote table", file=sys.stderr, flush=True)
                        
                        # Migrate data: for each quote, get customer_id from lead
                        conn.execute(text("""
                            UPDATE quote 
                            SET customer_id = (
                                SELECT lead.customer_id
                                FROM lead 
                                WHERE lead.id = quote.lead_id
                            )
                            WHERE quote.lead_id IS NOT NULL
                            AND EXISTS (SELECT 1 FROM lead WHERE lead.id = quote.lead_id AND lead.customer_id IS NOT NULL)
                        """))
                    print("Migrated Quote table", file=sys.stderr, flush=True)
                except Exception as e:
                    print(f"Error migrating Quote table: {e}", file=sys.stderr, flush=True)
                    import traceback
                    print(traceback.format_exc(), file=sys.stderr, flush=True)
        
        # Step 6: Add email settings columns to User table
        has_user_table = inspector.has_table("user")
        if has_user_table:
            user_columns = [col['name'] for col in inspector.get_columns("user")]
            email_settings_columns = [
                "smtp_host", "smtp_port", "smtp_user", "smtp_password", "smtp_use_tls",
                "smtp_from_email", "smtp_from_name", "imap_host", "imap_port", "imap_user",
                "imap_password", "imap_use_ssl", "email_signature", "email_test_mode", "updated_at"
            ]
            
            columns_to_add = [col for col in email_settings_columns if col not in user_columns]
            
            if columns_to_add:
                print("Adding email settings columns to user table...", file=sys.stderr, flush=True)
                try:
                    with engine.begin() as conn:
                        for col in columns_to_add:
                            try:
                                if col == "smtp_port" or col == "imap_port":
                                    conn.execute(text(f'ALTER TABLE "user" ADD COLUMN {col} INTEGER'))
                                elif col == "smtp_use_tls" or col == "imap_use_ssl" or col == "email_test_mode":
                                    conn.execute(text(f'ALTER TABLE "user" ADD COLUMN {col} BOOLEAN DEFAULT FALSE'))
                                elif col == "updated_at":
                                    conn.execute(text(f'ALTER TABLE "user" ADD COLUMN {col} TIMESTAMP DEFAULT CURRENT_TIMESTAMP'))
                                elif col == "email_signature":
                                    conn.execute(text(f'ALTER TABLE "user" ADD COLUMN {col} TEXT'))
                                else:
                                    conn.execute(text(f'ALTER TABLE "user" ADD COLUMN {col} VARCHAR(255)'))
                                print(f"Added {col} column to user table", file=sys.stderr, flush=True)
                            except Exception as col_error:
                                # Column might already exist
                                if "already exists" not in str(col_error).lower() and "duplicate" not in str(col_error).lower():
                                    print(f"Error adding {col}: {col_error}", file=sys.stderr, flush=True)
                    print("Email settings columns migration completed", file=sys.stderr, flush=True)
                except Exception as e:
                    print(f"Error migrating user email settings columns: {e}", file=sys.stderr, flush=True)
                    import traceback
                    print(traceback.format_exc(), file=sys.stderr, flush=True)
        
        print("Migration check completed", file=sys.stderr, flush=True)
    except Exception as e:
        # Log error but don't crash - migration might have already run
        import traceback
        print(f"Migration error: {e}", file=sys.stderr, flush=True)
        print(traceback.format_exc(), file=sys.stderr, flush=True)


def get_session() -> Generator[Session, None, None]:
    with Session(engine) as session:
        yield session
