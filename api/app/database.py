from sqlmodel import SQLModel, create_engine, Session, text as sql_text
from sqlalchemy import inspect, text
from typing import Generator
import os
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://user:password@localhost:5432/leadlock")
# Railway and some providers use postgres://; SQLAlchemy/psycopg2 expect postgresql://
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = "postgresql://" + DATABASE_URL[9:]
# Railway Postgres requires SSL; add sslmode if not localhost and not already set
if "localhost" not in DATABASE_URL and "127.0.0.1" not in DATABASE_URL:
    if "sslmode=" not in DATABASE_URL and "?" not in DATABASE_URL:
        DATABASE_URL = DATABASE_URL + "?sslmode=require"
    elif "sslmode=" not in DATABASE_URL and "?" in DATABASE_URL:
        DATABASE_URL = DATABASE_URL + "&sslmode=require"

# Only echo SQL in development (noisy in production)
_echo_sql = os.getenv("DEBUG", "false").lower() == "true" and not os.getenv("RAILWAY_ENVIRONMENT")

_engine_kwargs = {"echo": _echo_sql, "pool_pre_ping": True}
if not DATABASE_URL.startswith("sqlite"):
    _engine_kwargs.update(
        {
            "pool_size": int(os.getenv("DB_POOL_SIZE", "20")),
            "max_overflow": int(os.getenv("DB_MAX_OVERFLOW", "20")),
            "pool_timeout": int(os.getenv("DB_POOL_TIMEOUT", "30")),
            "pool_recycle": int(os.getenv("DB_POOL_RECYCLE", "1800")),
        }
    )
engine = create_engine(DATABASE_URL, **_engine_kwargs)


def _ensure_facebook_advert_schema(engine) -> None:
    """
    Ensure facebookadvertprofile exists and lead.facebook_advert_profile_id is present.
    Must run even if later migration steps error out (those errors abort the big migration try
    and previously skipped this step, leaving ORM ↔ DB mismatch and 500s on /api/leads, /api/quotes).
    """
    import sys

    try:
        insp = inspect(engine)
        if not insp.has_table("lead"):
            return

        is_pg = getattr(engine.dialect, "name", "") == "postgresql"

        if is_pg:
            try:
                with engine.begin() as conn:
                    conn.execute(
                        text(
                            """
                            CREATE TABLE IF NOT EXISTS facebookadvertprofile (
                                id SERIAL PRIMARY KEY,
                                name VARCHAR(255) NOT NULL,
                                offer_type VARCHAR(255),
                                image_url TEXT,
                                is_active BOOLEAN NOT NULL DEFAULT TRUE,
                                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                                updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                            )
                            """
                        )
                    )
                    conn.execute(
                        text(
                            "CREATE INDEX IF NOT EXISTS ix_facebookadvertprofile_is_active ON facebookadvertprofile (is_active)"
                        )
                    )
            except Exception as e:
                err = str(e).lower()
                if "already exists" not in err and "duplicate" not in err:
                    print(f"[facebook_advert] Error ensuring facebookadvertprofile: {e}", file=sys.stderr, flush=True)

        try:
            with engine.begin() as conn:
                conn.execute(
                    text(
                        "ALTER TABLE lead ADD COLUMN IF NOT EXISTS facebook_advert_profile_id INTEGER"
                    )
                )
            print("[facebook_advert] Ensured lead.facebook_advert_profile_id column", file=sys.stderr, flush=True)
        except Exception as e:
            err = str(e).lower()
            if "already exists" not in err and "duplicate" not in err:
                print(f"[facebook_advert] Error adding lead.facebook_advert_profile_id: {e}", file=sys.stderr, flush=True)

        if is_pg:
            try:
                with engine.begin() as conn:
                    conn.execute(
                        text(
                            """
                            DO $fbadvertfk$
                            BEGIN
                                IF NOT EXISTS (
                                    SELECT 1 FROM pg_constraint WHERE conname = 'fk_lead_facebook_advert_profile'
                                ) THEN
                                    ALTER TABLE lead ADD CONSTRAINT fk_lead_facebook_advert_profile
                                    FOREIGN KEY (facebook_advert_profile_id) REFERENCES facebookadvertprofile(id)
                                    ON DELETE SET NULL;
                                END IF;
                            END
                            $fbadvertfk$;
                            """
                        )
                    )
                print("[facebook_advert] Ensured fk_lead_facebook_advert_profile", file=sys.stderr, flush=True)
            except Exception as e:
                err = str(e).lower()
                if "already exists" not in err and "duplicate" not in err:
                    print(f"[facebook_advert] Error adding FK fk_lead_facebook_advert_profile: {e}", file=sys.stderr, flush=True)

        try:
            with engine.begin() as conn:
                conn.execute(
                    text(
                        "CREATE INDEX IF NOT EXISTS ix_lead_facebook_advert_profile_id ON lead (facebook_advert_profile_id)"
                    )
                )
        except Exception as e:
            err = str(e).lower()
            if "already exists" not in err and "duplicate" not in err:
                print(f"[facebook_advert] Error adding ix_lead_facebook_advert_profile_id: {e}", file=sys.stderr, flush=True)
    except Exception as e:
        print(f"[facebook_advert] Schema ensure failed: {e}", file=sys.stderr, flush=True)
        import traceback

        print(traceback.format_exc(), file=sys.stderr, flush=True)


def _ensure_archive_columns(engine) -> None:
    """Add archived_at to lead and quote for existing databases."""
    import sys

    try:
        insp = inspect(engine)
        if insp.has_table("lead"):
            cols = [c["name"] for c in insp.get_columns("lead")]
            if "archived_at" not in cols:
                with engine.begin() as conn:
                    conn.execute(text("ALTER TABLE lead ADD COLUMN archived_at TIMESTAMP"))
                    conn.execute(text("CREATE INDEX IF NOT EXISTS ix_lead_archived_at ON lead (archived_at)"))
                print("Added archived_at to lead table", file=sys.stderr, flush=True)
        if insp.has_table("quote"):
            cols = [c["name"] for c in insp.get_columns("quote")]
            if "archived_at" not in cols:
                with engine.begin() as conn:
                    conn.execute(text("ALTER TABLE quote ADD COLUMN archived_at TIMESTAMP"))
                    conn.execute(text("CREATE INDEX IF NOT EXISTS ix_quote_archived_at ON quote (archived_at)"))
                print("Added archived_at to quote table", file=sys.stderr, flush=True)
    except Exception as e:
        print(f"Warning: could not ensure archive columns: {e}", file=sys.stderr, flush=True)


def _ensure_dealer_portal_schema(engine) -> None:
    """Add dealer portal tables/columns for strict isolation."""
    import sys

    try:
        inspector = inspect(engine)
        if not inspector.has_table("user"):
            return

        with engine.begin() as conn:
            conn.execute(
                text(
                    """
                    CREATE TABLE IF NOT EXISTS dealer (
                        id SERIAL PRIMARY KEY,
                        name VARCHAR(255) NOT NULL UNIQUE,
                        company_name VARCHAR(255),
                        contact_name VARCHAR(255),
                        email VARCHAR(255),
                        phone VARCHAR(255),
                        address TEXT,
                        vat_number VARCHAR(255),
                        registration_number VARCHAR(255),
                        website VARCHAR(2048),
                        logo_url VARCHAR(2048),
                        is_active BOOLEAN NOT NULL DEFAULT TRUE,
                        created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                    )
                    """
                )
            )
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_dealer_name ON dealer (name)"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_dealer_email ON dealer (email)"))
            conn.execute(text("ALTER TABLE dealer ADD COLUMN IF NOT EXISTS company_name VARCHAR(255)"))
            conn.execute(text("ALTER TABLE dealer ADD COLUMN IF NOT EXISTS contact_name VARCHAR(255)"))
            conn.execute(text("ALTER TABLE dealer ADD COLUMN IF NOT EXISTS email VARCHAR(255)"))
            conn.execute(text("ALTER TABLE dealer ADD COLUMN IF NOT EXISTS phone VARCHAR(255)"))
            conn.execute(text("ALTER TABLE dealer ADD COLUMN IF NOT EXISTS address TEXT"))
            conn.execute(text("ALTER TABLE dealer ADD COLUMN IF NOT EXISTS vat_number VARCHAR(255)"))
            conn.execute(text("ALTER TABLE dealer ADD COLUMN IF NOT EXISTS registration_number VARCHAR(255)"))
            conn.execute(text("ALTER TABLE dealer ADD COLUMN IF NOT EXISTS website VARCHAR(2048)"))
            conn.execute(text("ALTER TABLE dealer ADD COLUMN IF NOT EXISTS logo_url VARCHAR(2048)"))

            conn.execute(text('ALTER TABLE "user" ADD COLUMN IF NOT EXISTS dealer_id INTEGER REFERENCES dealer(id)'))
            conn.execute(text('ALTER TABLE "user" ADD COLUMN IF NOT EXISTS dealer_commission_pct INTEGER'))
            conn.execute(text('CREATE INDEX IF NOT EXISTS ix_user_dealer_id ON "user" (dealer_id)'))
            conn.execute(
                text(
                    'ALTER TABLE "user" DROP CONSTRAINT IF EXISTS ck_user_dealer_commission_pct'
                )
            )
            conn.execute(
                text(
                    """
                    ALTER TABLE "user"
                    ADD CONSTRAINT ck_user_dealer_commission_pct
                    CHECK (
                        dealer_commission_pct IS NULL
                        OR dealer_commission_pct IN (10, 15)
                    )
                    """
                )
            )

            if inspector.has_table("quote"):
                conn.execute(text("ALTER TABLE quote ADD COLUMN IF NOT EXISTS dealer_id INTEGER REFERENCES dealer(id)"))
                conn.execute(text("ALTER TABLE quote ADD COLUMN IF NOT EXISTS dealer_customer_name VARCHAR(255)"))
                conn.execute(text("ALTER TABLE quote ADD COLUMN IF NOT EXISTS dealer_customer_email VARCHAR(255)"))
                conn.execute(text("ALTER TABLE quote ADD COLUMN IF NOT EXISTS dealer_customer_phone VARCHAR(255)"))
                conn.execute(text("ALTER TABLE quote ADD COLUMN IF NOT EXISTS dealer_customer_address TEXT"))
                conn.execute(
                    text("ALTER TABLE quote ADD COLUMN IF NOT EXISTS dealer_customer_postcode VARCHAR(16)")
                )
                conn.execute(text("ALTER TABLE quote ADD COLUMN IF NOT EXISTS revision_hash VARCHAR(128)"))
                conn.execute(text("CREATE INDEX IF NOT EXISTS ix_quote_dealer_id ON quote (dealer_id)"))
                conn.execute(text("CREATE INDEX IF NOT EXISTS ix_quote_revision_hash ON quote (revision_hash)"))

            conn.execute(
                text(
                    """
                    CREATE TABLE IF NOT EXISTS dealerproductaccess (
                        id SERIAL PRIMARY KEY,
                        dealer_id INTEGER NOT NULL REFERENCES dealer(id),
                        product_id INTEGER NOT NULL REFERENCES product(id),
                        created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                        CONSTRAINT uq_dealer_product_access UNIQUE (dealer_id, product_id)
                    )
                    """
                )
            )
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_dealerproductaccess_dealer_id ON dealerproductaccess (dealer_id)"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_dealerproductaccess_product_id ON dealerproductaccess (product_id)"))

            conn.execute(
                text(
                    """
                    CREATE TABLE IF NOT EXISTS dealeralloweddiscount (
                        id SERIAL PRIMARY KEY,
                        dealer_id INTEGER NOT NULL REFERENCES dealer(id),
                        discount_template_id INTEGER NOT NULL REFERENCES discounttemplate(id),
                        created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                        CONSTRAINT uq_dealer_allowed_discount_template UNIQUE (dealer_id, discount_template_id)
                    )
                    """
                )
            )
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_dealeralloweddiscount_dealer_id ON dealeralloweddiscount (dealer_id)"))

            conn.execute(
                text(
                    """
                    CREATE TABLE IF NOT EXISTS dealerdiscountpolicy (
                        id SERIAL PRIMARY KEY,
                        dealer_id INTEGER NOT NULL UNIQUE REFERENCES dealer(id),
                        mode VARCHAR(20) NOT NULL DEFAULT 'TEMPLATE',
                        allow_fixed_amount BOOLEAN NOT NULL DEFAULT FALSE,
                        allow_percentage BOOLEAN NOT NULL DEFAULT FALSE,
                        max_discount_percentage NUMERIC(10, 2),
                        max_discount_amount NUMERIC(10, 2),
                        updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                    )
                    """
                )
            )

        print("Dealer portal schema ensured", file=sys.stderr, flush=True)
    except Exception as e:
        print(f"Warning: could not ensure dealer schema: {e}", file=sys.stderr, flush=True)


def create_db_and_tables():
    """Create all tables and migrate existing data."""
    import sys
    from datetime import datetime, date
    
    # Ensure all models (including Order, OrderItem) are registered before create_all
    from app import models  # noqa: F401
    _ = models
    print("Creating tables...", file=sys.stderr, flush=True)
    SQLModel.metadata.create_all(engine)
    print("Tables created/verified", file=sys.stderr, flush=True)
    # Critical: run before the big migration try — that block catches broad exceptions and can skip later steps.
    _ensure_facebook_advert_schema(engine)
    _ensure_archive_columns(engine)
    _ensure_dealer_portal_schema(engine)

    # Migration logic for Customer model separation
    try:
        print("Checking for migration needs...", file=sys.stderr, flush=True)
        inspector = inspect(engine)
        
        has_customer_table = inspector.has_table("customer")
        has_lead_table = inspector.has_table("lead")
        has_activity_table = inspector.has_table("activity")
        has_quote_table = inspector.has_table("quote")
        has_customer_order_table = inspector.has_table("customer_order")
        has_orderitem_table = inspector.has_table("orderitem")

        # Ensure leadstatus enum contains CLOSED before any queries rely on it.
        if has_lead_table:
            try:
                with engine.begin() as conn:
                    conn.execute(text("ALTER TYPE leadstatus ADD VALUE IF NOT EXISTS 'CLOSED'"))
                print("Ensured leadstatus enum value: CLOSED", file=sys.stderr, flush=True)
            except Exception as e:
                error_str = str(e).lower()
                if "already exists" not in error_str:
                    print(f"Warning: could not add leadstatus value CLOSED: {e}", file=sys.stderr, flush=True)
        
        # Step 0a: Create order tables (customer_order, orderitem) if missing - order-from-quote feature
        if has_quote_table and (not has_customer_order_table or not has_orderitem_table):
            print("Creating order tables if missing...", file=sys.stderr, flush=True)
            try:
                with engine.begin() as conn:
                    if not has_customer_order_table:
                        conn.execute(text("""
                            CREATE TABLE IF NOT EXISTS customer_order (
                                id SERIAL PRIMARY KEY,
                                quote_id INTEGER NOT NULL UNIQUE REFERENCES quote(id),
                                customer_id INTEGER REFERENCES customer(id),
                                order_number VARCHAR(255) NOT NULL UNIQUE,
                                subtotal NUMERIC(10, 2) NOT NULL,
                                discount_total NUMERIC(10, 2) DEFAULT 0 NOT NULL,
                                total_amount NUMERIC(10, 2) NOT NULL,
                                deposit_amount NUMERIC(10, 2) DEFAULT 0 NOT NULL,
                                balance_amount NUMERIC(10, 2) DEFAULT 0 NOT NULL,
                                currency VARCHAR(10) DEFAULT 'GBP' NOT NULL,
                                terms_and_conditions TEXT,
                                notes TEXT,
                                created_by_id INTEGER NOT NULL REFERENCES "user"(id),
                                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL
                            )
                        """))
                        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_customer_order_order_number ON customer_order (order_number)"))
                        print("Created customer_order table", file=sys.stderr, flush=True)
                    if not has_orderitem_table:
                        conn.execute(text("""
                            CREATE TABLE IF NOT EXISTS orderitem (
                                id SERIAL PRIMARY KEY,
                                order_id INTEGER NOT NULL REFERENCES customer_order(id),
                                quote_item_id INTEGER REFERENCES quoteitem(id),
                                product_id INTEGER REFERENCES product(id),
                                description TEXT NOT NULL,
                                quantity NUMERIC(10, 2) DEFAULT 1 NOT NULL,
                                unit_price NUMERIC(10, 2) NOT NULL,
                                line_total NUMERIC(10, 2) NOT NULL,
                                discount_amount NUMERIC(10, 2) DEFAULT 0 NOT NULL,
                                final_line_total NUMERIC(10, 2) NOT NULL,
                                sort_order INTEGER DEFAULT 0 NOT NULL,
                                is_custom BOOLEAN DEFAULT FALSE NOT NULL
                            )
                        """))
                        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_orderitem_order_id ON orderitem (order_id)"))
                        print("Created orderitem table", file=sys.stderr, flush=True)
            except Exception as e:
                print(f"Error creating order tables: {e}", file=sys.stderr, flush=True)
                import traceback
                print(traceback.format_exc(), file=sys.stderr, flush=True)
        
        # Step 0a2: Add order status columns to customer_order if missing
        if has_customer_order_table or inspector.has_table("customer_order"):
            order_columns = [col["name"] for col in inspector.get_columns("customer_order")]
            for col_name in ("deposit_paid", "balance_paid", "paid_in_full", "installation_booked", "installation_completed"):
                if col_name not in order_columns:
                    try:
                        with engine.begin() as conn:
                            conn.execute(text(f"ALTER TABLE customer_order ADD COLUMN {col_name} BOOLEAN DEFAULT FALSE"))
                        print(f"Added {col_name} to customer_order", file=sys.stderr, flush=True)
                    except Exception as e:
                        if "already exists" not in str(e).lower():
                            print(f"Warning adding {col_name}: {e}", file=sys.stderr, flush=True)
            for col_name in ("invoice_number", "xero_invoice_id"):
                if col_name not in order_columns:
                    try:
                        with engine.begin() as conn:
                            if col_name == "invoice_number":
                                conn.execute(text("ALTER TABLE customer_order ADD COLUMN invoice_number VARCHAR(255)"))
                                conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS ix_customer_order_invoice_number ON customer_order (invoice_number) WHERE invoice_number IS NOT NULL"))
                            else:
                                conn.execute(text("ALTER TABLE customer_order ADD COLUMN xero_invoice_id VARCHAR(255)"))
                        print(f"Added {col_name} to customer_order", file=sys.stderr, flush=True)
                    except Exception as e:
                        if "already exists" not in str(e).lower():
                            print(f"Warning adding {col_name}: {e}", file=sys.stderr, flush=True)
            # One-way travel time (hours) for production sync; nullable
            order_columns = [col["name"] for col in inspector.get_columns("customer_order")]
            if "travel_time_hours_one_way" not in order_columns:
                try:
                    with engine.begin() as conn:
                        conn.execute(
                            text(
                                "ALTER TABLE customer_order ADD COLUMN travel_time_hours_one_way NUMERIC(10, 4)"
                            )
                        )
                    print("Added travel_time_hours_one_way to customer_order", file=sys.stderr, flush=True)
                except Exception as e:
                    if "already exists" not in str(e).lower():
                        print(f"Warning adding travel_time_hours_one_way: {e}", file=sys.stderr, flush=True)

        # Step 0a3: Create access_sheet_request table if missing
        has_access_sheet_table = inspector.has_table("accesssheetrequest")
        if has_customer_order_table and not has_access_sheet_table:
            print("Creating accesssheetrequest table...", file=sys.stderr, flush=True)
            try:
                with engine.begin() as conn:
                    conn.execute(text("""
                        CREATE TABLE IF NOT EXISTS accesssheetrequest (
                            id SERIAL PRIMARY KEY,
                            order_id INTEGER NOT NULL REFERENCES customer_order(id),
                            access_token VARCHAR(255) NOT NULL UNIQUE,
                            completed_at TIMESTAMP,
                            answers JSONB,
                            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
                            sent_at TIMESTAMP
                        )
                    """))
                    conn.execute(text("CREATE INDEX IF NOT EXISTS ix_accesssheetrequest_access_token ON accesssheetrequest (access_token)"))
                    conn.execute(text("CREATE INDEX IF NOT EXISTS ix_accesssheetrequest_order_id ON accesssheetrequest (order_id)"))
                    print("Created accesssheetrequest table", file=sys.stderr, flush=True)
            except Exception as e:
                print(f"Error creating accesssheetrequest table: {e}", file=sys.stderr, flush=True)
                import traceback
                print(traceback.format_exc(), file=sys.stderr, flush=True)
        
        # Step 0: Facebook Messenger - messenger_psid on Customer/Lead (run first so it's never skipped)
        if has_customer_table:
            customer_columns = [col['name'] for col in inspector.get_columns("customer")]
            if "messenger_psid" not in customer_columns:
                print("Adding messenger_psid column to customer table...", file=sys.stderr, flush=True)
                try:
                    with engine.begin() as conn:
                        conn.execute(text("ALTER TABLE customer ADD COLUMN messenger_psid VARCHAR(255)"))
                        conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS ix_customer_messenger_psid ON customer (messenger_psid) WHERE messenger_psid IS NOT NULL"))
                    print("Added messenger_psid column to customer table", file=sys.stderr, flush=True)
                except Exception as e:
                    error_str = str(e).lower()
                    if "already exists" not in error_str and "duplicate" not in error_str:
                        print(f"Error adding messenger_psid to customer: {e}", file=sys.stderr, flush=True)
            if "source_system" not in customer_columns:
                print("Adding source_system column to customer table...", file=sys.stderr, flush=True)
                try:
                    with engine.begin() as conn:
                        conn.execute(text("ALTER TABLE customer ADD COLUMN source_system VARCHAR(50)"))
                    print("Added source_system column to customer table", file=sys.stderr, flush=True)
                except Exception as e:
                    error_str = str(e).lower()
                    if "already exists" not in error_str:
                        print(f"Error adding source_system to customer: {e}", file=sys.stderr, flush=True)
            customer_columns = [col['name'] for col in inspector.get_columns("customer")]
            if "sms_bot_paused_until" not in customer_columns:
                print("Adding sms_bot_paused_until column to customer table...", file=sys.stderr, flush=True)
                try:
                    with engine.begin() as conn:
                        conn.execute(text("ALTER TABLE customer ADD COLUMN sms_bot_paused_until TIMESTAMP"))
                    print("Added sms_bot_paused_until column to customer table", file=sys.stderr, flush=True)
                except Exception as e:
                    error_str = str(e).lower()
                    if "already exists" not in error_str:
                        print(f"Error adding sms_bot_paused_until to customer: {e}", file=sys.stderr, flush=True)
            customer_columns = [col["name"] for col in inspector.get_columns("customer")]
            if "sms_bot_suppress_auto_reply_before_utc" not in customer_columns:
                print(
                    "Adding sms_bot_suppress_auto_reply_before_utc column to customer table...",
                    file=sys.stderr,
                    flush=True,
                )
                try:
                    with engine.begin() as conn:
                        conn.execute(
                            text(
                                "ALTER TABLE customer ADD COLUMN sms_bot_suppress_auto_reply_before_utc TIMESTAMP"
                            )
                        )
                    print(
                        "Added sms_bot_suppress_auto_reply_before_utc column to customer table",
                        file=sys.stderr,
                        flush=True,
                    )
                except Exception as e:
                    error_str = str(e).lower()
                    if "already exists" not in error_str:
                        print(
                            f"Error adding sms_bot_suppress_auto_reply_before_utc to customer: {e}",
                            file=sys.stderr,
                            flush=True,
                        )
            customer_columns = [col["name"] for col in inspector.get_columns("customer")]
            if "sms_bot_stopped" not in customer_columns:
                print("Adding sms_bot_stopped column to customer table...", file=sys.stderr, flush=True)
                try:
                    with engine.begin() as conn:
                        conn.execute(
                            text("ALTER TABLE customer ADD COLUMN sms_bot_stopped BOOLEAN DEFAULT FALSE NOT NULL")
                        )
                    print("Added sms_bot_stopped column to customer table", file=sys.stderr, flush=True)
                except Exception as e:
                    error_str = str(e).lower()
                    if "already exists" not in error_str and "duplicate" not in error_str:
                        print(f"Error adding sms_bot_stopped to customer: {e}", file=sys.stderr, flush=True)
            customer_columns = [col["name"] for col in inspector.get_columns("customer")]
            if "automated_reminder_outreach_opt_out" not in customer_columns:
                print(
                    "Adding automated_reminder_outreach_opt_out column to customer table...",
                    file=sys.stderr,
                    flush=True,
                )
                try:
                    with engine.begin() as conn:
                        conn.execute(
                            text(
                                "ALTER TABLE customer ADD COLUMN automated_reminder_outreach_opt_out "
                                "BOOLEAN DEFAULT FALSE NOT NULL"
                            )
                        )
                    print(
                        "Added automated_reminder_outreach_opt_out column to customer table",
                        file=sys.stderr,
                        flush=True,
                    )
                except Exception as e:
                    error_str = str(e).lower()
                    if "already exists" not in error_str and "duplicate" not in error_str:
                        print(
                            f"Error adding automated_reminder_outreach_opt_out to customer: {e}",
                            file=sys.stderr,
                            flush=True,
                        )
        if has_lead_table:
            lead_columns = [col['name'] for col in inspector.get_columns("lead")]
            if "messenger_psid" not in lead_columns:
                print("Adding messenger_psid column to lead table...", file=sys.stderr, flush=True)
                try:
                    with engine.begin() as conn:
                        conn.execute(text("ALTER TABLE lead ADD COLUMN messenger_psid VARCHAR(255)"))
                    print("Added messenger_psid column to lead table", file=sys.stderr, flush=True)
                except Exception as e:
                    error_str = str(e).lower()
                    if "already exists" not in error_str and "duplicate" not in error_str:
                        print(f"Error adding messenger_psid to lead: {e}", file=sys.stderr, flush=True)
        
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
            
            if has_lead_id:
                print("Migrating Quote table from lead_id to customer_id...", file=sys.stderr, flush=True)
                try:
                    with engine.begin() as conn:
                        # Add customer_id column if it doesn't exist
                        if not has_customer_id:
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
                        
                        # Make lead_id nullable to allow quotes without leads
                        try:
                            # PostgreSQL syntax
                            conn.execute(text("ALTER TABLE quote ALTER COLUMN lead_id DROP NOT NULL"))
                            print("Made lead_id nullable in quote table", file=sys.stderr, flush=True)
                        except Exception as alter_error:
                            # Try to get more info about the error
                            error_str = str(alter_error).lower()
                            if "does not exist" not in error_str and "not-null" not in error_str and "constraint" not in error_str:
                                print(f"Warning: Could not make lead_id nullable: {alter_error}", file=sys.stderr, flush=True)
                    print("Migrated Quote table", file=sys.stderr, flush=True)
                except Exception as e:
                    print(f"Error migrating Quote table: {e}", file=sys.stderr, flush=True)
                    import traceback
                    print(traceback.format_exc(), file=sys.stderr, flush=True)
            
            # Add opportunity management columns to quote table if they don't exist
            quote_columns = [col['name'] for col in inspector.get_columns("quote")]
            opportunity_columns = {
                'opportunity_stage': 'VARCHAR(50)',
                'close_probability': 'NUMERIC(5, 2)',
                'expected_close_date': 'TIMESTAMP',
                'next_action': 'TEXT',
                'next_action_due_date': 'TIMESTAMP',
                'loss_reason': 'TEXT',
                'loss_category': 'VARCHAR(50)',
                'owner_id': 'INTEGER'
            }
            
            for col_name, col_type in opportunity_columns.items():
                if col_name not in quote_columns:
                    print(f"Adding {col_name} column to quote table...", file=sys.stderr, flush=True)
                    try:
                        with engine.begin() as conn:
                            if col_name == 'owner_id':
                                # Add foreign key constraint for owner_id (nullable)
                                conn.execute(text(f"ALTER TABLE quote ADD COLUMN {col_name} {col_type} REFERENCES \"user\"(id)"))
                            else:
                                conn.execute(text(f"ALTER TABLE quote ADD COLUMN {col_name} {col_type}"))
                        print(f"Added {col_name} column to quote table", file=sys.stderr, flush=True)
                    except Exception as col_error:
                        error_str = str(col_error).lower()
                        if "already exists" not in error_str and "duplicate" not in error_str:
                            print(f"Warning: Could not add {col_name} column: {col_error}", file=sys.stderr, flush=True)
            
            # Add temperature column to quote table (hot/warm/cold)
            quote_columns = [col['name'] for col in inspector.get_columns("quote")]
            if "temperature" not in quote_columns:
                print("Adding temperature column to quote table...", file=sys.stderr, flush=True)
                try:
                    with engine.begin() as conn:
                        conn.execute(text("ALTER TABLE quote ADD COLUMN temperature VARCHAR(20)"))
                    print("Added temperature column to quote table", file=sys.stderr, flush=True)
                except Exception as col_error:
                    error_str = str(col_error).lower()
                    if "already exists" not in error_str and "duplicate" not in error_str:
                        print(f"Warning: Could not add temperature column: {col_error}", file=sys.stderr, flush=True)

            # Add include_spec_sheets to quote table (product spec sheets in quote PDF)
            quote_columns = [col['name'] for col in inspector.get_columns("quote")]
            if "include_spec_sheets" not in quote_columns:
                print("Adding include_spec_sheets column to quote table...", file=sys.stderr, flush=True)
                try:
                    with engine.begin() as conn:
                        conn.execute(text("ALTER TABLE quote ADD COLUMN include_spec_sheets BOOLEAN DEFAULT TRUE"))
                    print("Added include_spec_sheets column to quote table", file=sys.stderr, flush=True)
                except Exception as col_error:
                    error_str = str(col_error).lower()
                    if "already exists" not in error_str and "duplicate" not in error_str:
                        print(f"Warning: Could not add include_spec_sheets column: {col_error}", file=sys.stderr, flush=True)

            # Add include_available_optional_extras to quote table (optional extras section on customer view/PDF)
            quote_columns = [col['name'] for col in inspector.get_columns("quote")]
            if "include_available_optional_extras" not in quote_columns:
                print("Adding include_available_optional_extras column to quote table...", file=sys.stderr, flush=True)
                try:
                    with engine.begin() as conn:
                        conn.execute(text("ALTER TABLE quote ADD COLUMN include_available_optional_extras BOOLEAN DEFAULT FALSE"))
                    print("Added include_available_optional_extras column to quote table", file=sys.stderr, flush=True)
                except Exception as col_error:
                    error_str = str(col_error).lower()
                    if "already exists" not in error_str and "duplicate" not in error_str:
                        print(f"Warning: Could not add include_available_optional_extras column: {col_error}", file=sys.stderr, flush=True)

            # Add include_delivery_installation_contact_note to quote table
            quote_columns = [col['name'] for col in inspector.get_columns("quote")]
            if "include_delivery_installation_contact_note" not in quote_columns:
                print("Adding include_delivery_installation_contact_note column to quote table...", file=sys.stderr, flush=True)
                try:
                    with engine.begin() as conn:
                        conn.execute(text("ALTER TABLE quote ADD COLUMN include_delivery_installation_contact_note BOOLEAN DEFAULT FALSE"))
                    print("Added include_delivery_installation_contact_note column to quote table", file=sys.stderr, flush=True)
                except Exception as col_error:
                    error_str = str(col_error).lower()
                    if "already exists" not in error_str and "duplicate" not in error_str:
                        print(f"Warning: Could not add include_delivery_installation_contact_note column: {col_error}", file=sys.stderr, flush=True)

            # Add lead_id to quote table (quote generated from lead)
            quote_columns = [col['name'] for col in inspector.get_columns("quote")]
            if "lead_id" not in quote_columns:
                print("Adding lead_id column to quote table...", file=sys.stderr, flush=True)
                try:
                    with engine.begin() as conn:
                        conn.execute(text("ALTER TABLE quote ADD COLUMN lead_id INTEGER REFERENCES lead(id)"))
                    print("Added lead_id column to quote table", file=sys.stderr, flush=True)
                except Exception as col_error:
                    error_str = str(col_error).lower()
                    if "already exists" not in error_str and "duplicate" not in error_str:
                        print(f"Warning: Could not add lead_id column: {col_error}", file=sys.stderr, flush=True)
        
        # Step 6: Add trading_name and default_terms_and_conditions to CompanySettings table
        has_company_settings = inspector.has_table("companysettings")
        if has_company_settings:
            company_columns = [col['name'] for col in inspector.get_columns("companysettings")]
            if "trading_name" not in company_columns:
                print("Adding trading_name column to companysettings table...", file=sys.stderr, flush=True)
                try:
                    with engine.begin() as conn:
                        conn.execute(text('ALTER TABLE companysettings ADD COLUMN trading_name VARCHAR(255)'))
                    print("Added trading_name column to companysettings table", file=sys.stderr, flush=True)
                except Exception as e:
                    print(f"Error adding trading_name column: {e}", file=sys.stderr, flush=True)
                    import traceback
                    print(traceback.format_exc(), file=sys.stderr, flush=True)
            
            if "default_terms_and_conditions" not in company_columns:
                print("Adding default_terms_and_conditions column to companysettings table...", file=sys.stderr, flush=True)
                try:
                    with engine.begin() as conn:
                        conn.execute(text('ALTER TABLE companysettings ADD COLUMN default_terms_and_conditions TEXT'))
                    print("Added default_terms_and_conditions column to companysettings table", file=sys.stderr, flush=True)
                except Exception as e:
                    error_str = str(e).lower()
                    if "already exists" not in error_str and "duplicate" not in error_str:
                        print(f"Error adding default_terms_and_conditions column: {e}", file=sys.stderr, flush=True)
                        import traceback
                        print(traceback.format_exc(), file=sys.stderr, flush=True)

            company_columns = [col['name'] for col in inspector.get_columns("companysettings")]
            if "email_disclaimer" not in company_columns:
                print("Adding email_disclaimer column to companysettings table...", file=sys.stderr, flush=True)
                try:
                    with engine.begin() as conn:
                        conn.execute(text('ALTER TABLE companysettings ADD COLUMN email_disclaimer TEXT'))
                    print("Added email_disclaimer column to companysettings table", file=sys.stderr, flush=True)
                except Exception as e:
                    error_str = str(e).lower()
                    if "already exists" not in error_str and "duplicate" not in error_str:
                        print(f"Error adding email_disclaimer column: {e}", file=sys.stderr, flush=True)

            company_columns = [col['name'] for col in inspector.get_columns("companysettings")]
            if "default_email_signature" not in company_columns:
                print("Adding default_email_signature column to companysettings table...", file=sys.stderr, flush=True)
                try:
                    with engine.begin() as conn:
                        conn.execute(text('ALTER TABLE companysettings ADD COLUMN default_email_signature TEXT'))
                    print("Added default_email_signature column to companysettings table", file=sys.stderr, flush=True)
                except Exception as e:
                    error_str = str(e).lower()
                    if "already exists" not in error_str and "duplicate" not in error_str:
                        print(f"Error adding default_email_signature column: {e}", file=sys.stderr, flush=True)

            if "hourly_install_rate" not in company_columns:
                print("Adding hourly_install_rate column to companysettings table...", file=sys.stderr, flush=True)
                try:
                    with engine.begin() as conn:
                        conn.execute(text('ALTER TABLE companysettings ADD COLUMN hourly_install_rate NUMERIC(10, 2)'))
                    print("Added hourly_install_rate column to companysettings table", file=sys.stderr, flush=True)
                except Exception as e:
                    error_str = str(e).lower()
                    if "already exists" not in error_str and "duplicate" not in error_str:
                        print(f"Error adding hourly_install_rate column: {e}", file=sys.stderr, flush=True)
            
            # Installation lead time (amendable by production, visible to sales on dashboard)
            company_columns = [col['name'] for col in inspector.get_columns("companysettings")]
            if "installation_lead_time" not in company_columns:
                print("Adding installation_lead_time column to companysettings table...", file=sys.stderr, flush=True)
                try:
                    with engine.begin() as conn:
                        conn.execute(text('ALTER TABLE companysettings ADD COLUMN installation_lead_time VARCHAR(20)'))
                    print("Added installation_lead_time column to companysettings table", file=sys.stderr, flush=True)
                except Exception as col_error:
                    error_str = str(col_error).lower()
                    if "already exists" not in error_str and "duplicate" not in error_str:
                        print(f"Warning: Could not add installation_lead_time column: {col_error}", file=sys.stderr, flush=True)

            # Per-product-type installation lead times (same enum storage as installation_lead_time)
            for col_name in (
                "installation_lead_time_stables",
                "installation_lead_time_sheds",
                "installation_lead_time_cabins",
            ):
                company_columns = [col["name"] for col in inspector.get_columns("companysettings")]
                if col_name not in company_columns:
                    print(f"Adding {col_name} column to companysettings table...", file=sys.stderr, flush=True)
                    try:
                        with engine.begin() as conn:
                            conn.execute(
                                text(f"ALTER TABLE companysettings ADD COLUMN {col_name} VARCHAR(20)")
                            )
                        print(f"Added {col_name} column to companysettings table", file=sys.stderr, flush=True)
                    except Exception as col_error:
                        error_str = str(col_error).lower()
                        if "already exists" not in error_str and "duplicate" not in error_str:
                            print(
                                f"Warning: Could not add {col_name} column: {col_error}",
                                file=sys.stderr,
                                flush=True,
                            )
            # Backfill per-type from legacy when all three are still null
            try:
                with engine.begin() as conn:
                    conn.execute(
                        text(
                            """
                            UPDATE companysettings SET
                                installation_lead_time_stables = installation_lead_time,
                                installation_lead_time_sheds = installation_lead_time,
                                installation_lead_time_cabins = installation_lead_time
                            WHERE installation_lead_time IS NOT NULL
                              AND installation_lead_time_stables IS NULL
                              AND installation_lead_time_sheds IS NULL
                              AND installation_lead_time_cabins IS NULL
                            """
                        )
                    )
            except Exception as bf_err:
                print(
                    f"Warning: installation lead time per-type backfill skipped: {bf_err}",
                    file=sys.stderr,
                    flush=True,
                )

            # Logo URL (uploaded image URL for quote PDFs)
            company_columns = [col['name'] for col in inspector.get_columns("companysettings")]
            if "logo_url" not in company_columns:
                print("Adding logo_url column to companysettings table...", file=sys.stderr, flush=True)
                try:
                    with engine.begin() as conn:
                        conn.execute(text('ALTER TABLE companysettings ADD COLUMN logo_url VARCHAR(2048)'))
                    print("Added logo_url column to companysettings table", file=sys.stderr, flush=True)
                except Exception as col_error:
                    error_str = str(col_error).lower()
                    if "already exists" not in error_str and "duplicate" not in error_str:
                        print(f"Warning: Could not add logo_url column: {col_error}", file=sys.stderr, flush=True)

            # Footer logo URL (separate logo for PDF footer)
            company_columns = [col['name'] for col in inspector.get_columns("companysettings")]
            if "footer_logo_url" not in company_columns:
                print("Adding footer_logo_url column to companysettings table...", file=sys.stderr, flush=True)
                try:
                    with engine.begin() as conn:
                        conn.execute(text('ALTER TABLE companysettings ADD COLUMN footer_logo_url VARCHAR(2048)'))
                    print("Added footer_logo_url column to companysettings table", file=sys.stderr, flush=True)
                except Exception as col_error:
                    error_str = str(col_error).lower()
                    if "already exists" not in error_str and "duplicate" not in error_str:
                        print(f"Warning: Could not add footer_logo_url column: {col_error}", file=sys.stderr, flush=True)

            # Bank details (quote/invoice PDFs)
            for col_name, col_sql in [
                ("bank_name", "VARCHAR(255)"),
                ("bank_account_name", "VARCHAR(255)"),
                ("account_number", "VARCHAR(50)"),
                ("sort_code", "VARCHAR(20)"),
            ]:
                company_columns = [col['name'] for col in inspector.get_columns("companysettings")]
                if col_name not in company_columns:
                    print(f"Adding {col_name} column to companysettings table...", file=sys.stderr, flush=True)
                    try:
                        with engine.begin() as conn:
                            conn.execute(text(f'ALTER TABLE companysettings ADD COLUMN {col_name} {col_sql}'))
                        print(f"Added {col_name} column to companysettings table", file=sys.stderr, flush=True)
                    except Exception as e:
                        error_str = str(e).lower()
                        if "already exists" not in error_str and "duplicate" not in error_str:
                            print(f"Error adding {col_name} column: {e}", file=sys.stderr, flush=True)

            # Installation & travel (mileage, overnight, 2-man team) + install quote margin + product import gross margin
            for col_name, col_sql in [
                ("distance_before_overnight_miles", "NUMERIC(10, 2)"),
                ("cost_per_mile", "NUMERIC(10, 2)"),
                ("hotel_allowance_per_night", "NUMERIC(10, 2)"),
                ("meal_allowance_per_day", "NUMERIC(10, 2)"),
                ("average_speed_mph", "NUMERIC(5, 2)"),
                ("install_quote_margin_pct", "NUMERIC(5, 2) DEFAULT 30"),
                ("product_import_gross_margin_pct", "NUMERIC(5, 2)"),
            ]:
                company_columns = [col['name'] for col in inspector.get_columns("companysettings")]
                if col_name not in company_columns:
                    print(f"Adding {col_name} column to companysettings table...", file=sys.stderr, flush=True)
                    try:
                        with engine.begin() as conn:
                            conn.execute(text(f'ALTER TABLE companysettings ADD COLUMN {col_name} {col_sql}'))
                        print(f"Added {col_name} column to companysettings table", file=sys.stderr, flush=True)
                    except Exception as e:
                        error_str = str(e).lower()
                        if "already exists" not in error_str and "duplicate" not in error_str:
                            print(f"Error adding {col_name} column: {e}", file=sys.stderr, flush=True)

            # Quote requirements: require engagement proof before quoting (toggle)
            company_columns = [col['name'] for col in inspector.get_columns("companysettings")]
            if "require_engagement_proof" not in company_columns:
                print("Adding require_engagement_proof column to companysettings table...", file=sys.stderr, flush=True)
                try:
                    with engine.begin() as conn:
                        conn.execute(text('ALTER TABLE companysettings ADD COLUMN require_engagement_proof BOOLEAN DEFAULT FALSE'))
                    print("Added require_engagement_proof column to companysettings table", file=sys.stderr, flush=True)
                except Exception as e:
                    error_str = str(e).lower()
                    if "already exists" not in error_str and "duplicate" not in error_str:
                        print(f"Error adding require_engagement_proof column: {e}", file=sys.stderr, flush=True)

            # SMS bot settings for out-of-hours assistant
            for col_name, col_sql in [
                ("sms_bot_mode", "VARCHAR(10) DEFAULT 'OFF'"),
                ("sms_bot_timezone", "VARCHAR(100) DEFAULT 'Europe/London'"),
                ("sms_bot_business_hours_json", "TEXT"),
                ("sms_bot_fallback_message", "TEXT"),
                ("sms_bot_max_replies_per_thread", "INTEGER DEFAULT 3"),
                ("sms_bot_pause_minutes_after_handover", "INTEGER DEFAULT 720"),
                ("sms_bot_system_instructions", "TEXT"),
            ]:
                company_columns = [col['name'] for col in inspector.get_columns("companysettings")]
                if col_name not in company_columns:
                    print(f"Adding {col_name} column to companysettings table...", file=sys.stderr, flush=True)
                    try:
                        with engine.begin() as conn:
                            conn.execute(text(f'ALTER TABLE companysettings ADD COLUMN {col_name} {col_sql}'))
                        print(f"Added {col_name} column to companysettings table", file=sys.stderr, flush=True)
                    except Exception as e:
                        error_str = str(e).lower()
                        if "already exists" not in error_str and "duplicate" not in error_str:
                            print(f"Error adding {col_name} column: {e}", file=sys.stderr, flush=True)

        # Step 7: Add is_active and email settings columns to User table
        has_user_table = inspector.has_table("user")
        if has_user_table:
            user_columns = [col['name'] for col in inspector.get_columns("user")]
            if "is_active" not in user_columns:
                print("Adding is_active column to user table...", file=sys.stderr, flush=True)
                try:
                    with engine.begin() as conn:
                        conn.execute(text('ALTER TABLE "user" ADD COLUMN is_active BOOLEAN DEFAULT TRUE'))
                    print("Added is_active column to user table", file=sys.stderr, flush=True)
                except Exception as e:
                    error_str = str(e).lower()
                    if "already exists" not in error_str and "duplicate" not in error_str:
                        print(f"Error adding is_active column: {e}", file=sys.stderr, flush=True)
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
        
        # Step 8: Add deposit_amount and balance_amount to Quote table
        if has_quote_table:
            quote_columns = [col['name'] for col in inspector.get_columns("quote")]
            if "deposit_amount" not in quote_columns:
                print("Adding deposit_amount and balance_amount columns to quote table...", file=sys.stderr, flush=True)
                try:
                    with engine.begin() as conn:
                        conn.execute(text('ALTER TABLE quote ADD COLUMN deposit_amount NUMERIC(10, 2) DEFAULT 0'))
                        conn.execute(text('ALTER TABLE quote ADD COLUMN balance_amount NUMERIC(10, 2) DEFAULT 0'))
                        
                        # Calculate and set deposit/balance for existing quotes (50% default)
                        conn.execute(text("""
                            UPDATE quote 
                            SET deposit_amount = total_amount * 0.5,
                                balance_amount = total_amount * 0.5
                            WHERE deposit_amount = 0 AND balance_amount = 0
                        """))
                        print("Added deposit_amount and balance_amount columns to quote table", file=sys.stderr, flush=True)
                except Exception as e:
                    print(f"Error adding deposit/balance columns: {e}", file=sys.stderr, flush=True)
                    import traceback
                    print(traceback.format_exc(), file=sys.stderr, flush=True)
        
        # Step 8b: Add view_token and open_count to QuoteEmail table
        has_quoteemail_table = inspector.has_table("quoteemail")
        if has_quoteemail_table:
            quoteemail_columns = [col["name"] for col in inspector.get_columns("quoteemail")]
            if "view_token" not in quoteemail_columns:
                print("Adding view_token column to quoteemail table...", file=sys.stderr, flush=True)
                try:
                    with engine.begin() as conn:
                        conn.execute(text("ALTER TABLE quoteemail ADD COLUMN view_token VARCHAR(255)"))
                        conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS ix_quoteemail_view_token ON quoteemail (view_token) WHERE view_token IS NOT NULL"))
                    print("Added view_token column to quoteemail table", file=sys.stderr, flush=True)
                except Exception as e:
                    error_str = str(e).lower()
                    if "already exists" not in error_str and "duplicate" not in error_str:
                        print(f"Error adding view_token to quoteemail: {e}", file=sys.stderr, flush=True)
            if "open_count" not in quoteemail_columns:
                print("Adding open_count column to quoteemail table...", file=sys.stderr, flush=True)
                try:
                    with engine.begin() as conn:
                        conn.execute(text("ALTER TABLE quoteemail ADD COLUMN open_count INTEGER DEFAULT 0"))
                    print("Added open_count column to quoteemail table", file=sys.stderr, flush=True)
                except Exception as e:
                    error_str = str(e).lower()
                    if "already exists" not in error_str and "duplicate" not in error_str:
                        print(f"Error adding open_count to quoteemail: {e}", file=sys.stderr, flush=True)
            if "include_available_extras" not in quoteemail_columns:
                print("Adding include_available_extras column to quoteemail table...", file=sys.stderr, flush=True)
                try:
                    with engine.begin() as conn:
                        conn.execute(text("ALTER TABLE quoteemail ADD COLUMN include_available_extras BOOLEAN DEFAULT FALSE"))
                    print("Added include_available_extras column to quoteemail table", file=sys.stderr, flush=True)
                except Exception as e:
                    error_str = str(e).lower()
                    if "already exists" not in error_str and "duplicate" not in error_str:
                        print(f"Error adding include_available_extras to quoteemail: {e}", file=sys.stderr, flush=True)
        
        # Step 8c: Add last_viewed_at to quote table
        if has_quote_table:
            quote_columns = [col["name"] for col in inspector.get_columns("quote")]
            if "last_viewed_at" not in quote_columns:
                print("Adding last_viewed_at column to quote table...", file=sys.stderr, flush=True)
                try:
                    with engine.begin() as conn:
                        conn.execute(text("ALTER TABLE quote ADD COLUMN last_viewed_at TIMESTAMP"))
                    print("Added last_viewed_at column to quote table", file=sys.stderr, flush=True)
                except Exception as e:
                    error_str = str(e).lower()
                    if "already exists" not in error_str and "duplicate" not in error_str:
                        print(f"Error adding last_viewed_at to quote: {e}", file=sys.stderr, flush=True)
        
        # Step 8d: Migrate deposit/balance from ex VAT to inc VAT (one-time data migration)
        try:
            with engine.begin() as conn:
                conn.execute(text("""
                    CREATE TABLE IF NOT EXISTS applied_data_migrations (
                        migration_name VARCHAR(255) PRIMARY KEY,
                        applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """))
            with engine.connect() as conn:
                result = conn.execute(text(
                    "SELECT 1 FROM applied_data_migrations WHERE migration_name = 'deposit_balance_inc_vat'"
                ))
                if result.fetchone() is None:
                    print("Migrating deposit/balance from ex VAT to inc VAT...", file=sys.stderr, flush=True)
                    with engine.begin() as mig_conn:
                        mig_conn.execute(text("""
                            UPDATE quote
                            SET deposit_amount = ROUND(deposit_amount * 1.2, 2),
                                balance_amount = ROUND(balance_amount * 1.2, 2)
                        """))
                        if inspector.has_table("customer_order"):
                            mig_conn.execute(text("""
                                UPDATE customer_order
                                SET deposit_amount = ROUND(deposit_amount * 1.2, 2),
                                    balance_amount = ROUND(balance_amount * 1.2, 2)
                            """))
                        mig_conn.execute(text(
                            "INSERT INTO applied_data_migrations (migration_name) VALUES ('deposit_balance_inc_vat')"
                        ))
                    print("Deposit/balance inc VAT migration completed", file=sys.stderr, flush=True)
        except Exception as e:
            error_str = str(e).lower()
            if "already exists" not in error_str and "duplicate" not in error_str:
                print(f"Error in deposit/balance inc VAT migration: {e}", file=sys.stderr, flush=True)
                import traceback
                print(traceback.format_exc(), file=sys.stderr, flush=True)

        # Step 8e: (Rolled back) Had migrated WEBSITE -> CS WEBSITE; reverted in 8f for backward compat.
        # Step 8f: Revert CS WEBSITE back to WEBSITE (keep WEBSITE in enum for backward compat with existing data)
        try:
            with engine.connect() as conn:
                result = conn.execute(text(
                    "SELECT 1 FROM applied_data_migrations WHERE migration_name = 'lead_source_revert_cs_to_website'"
                ))
                if result.fetchone() is None:
                    print("Reverting CS WEBSITE lead source to WEBSITE...", file=sys.stderr, flush=True)
                    with engine.begin() as mig_conn:
                        mig_conn.execute(text(
                            "UPDATE lead SET lead_source = 'WEBSITE' WHERE lead_source = 'CS WEBSITE'"
                        ))
                        mig_conn.execute(text(
                            "INSERT INTO applied_data_migrations (migration_name) VALUES ('lead_source_revert_cs_to_website')"
                        ))
                    print("Lead source revert completed", file=sys.stderr, flush=True)
        except Exception as e:
            error_str = str(e).lower()
            if "already exists" not in error_str and "duplicate" not in error_str:
                print(f"Error in lead source revert migration: {e}", file=sys.stderr, flush=True)
        
        # Step 9: Create Reminder and ReminderRule tables + seed default rules
        has_reminder_table = inspector.has_table("reminder")
        has_reminder_rule_table = inspector.has_table("reminderrule")

        # Step 9b: Migrate reminderrule.threshold_days -> threshold_hours (existing DBs store days; multiply by 24)
        if has_reminder_rule_table or inspector.has_table("reminderrule"):
            try:
                with engine.begin() as conn:
                    conn.execute(
                        text(
                            """
                            CREATE TABLE IF NOT EXISTS applied_data_migrations (
                                migration_name VARCHAR(255) PRIMARY KEY,
                                applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                            )
                            """
                        )
                    )
                rr_cols = {c["name"] for c in inspector.get_columns("reminderrule")}
                with engine.connect() as conn:
                    already = conn.execute(
                        text(
                            "SELECT 1 FROM applied_data_migrations "
                            "WHERE migration_name = 'reminderrule_threshold_days_to_hours'"
                        )
                    ).fetchone()
                if not already:
                    dialect = getattr(engine.dialect, "name", "")
                    if "threshold_days" in rr_cols and "threshold_hours" not in rr_cols:
                        with engine.begin() as conn:
                            conn.execute(
                                text("ALTER TABLE reminderrule RENAME COLUMN threshold_days TO threshold_hours")
                            )
                            conn.execute(
                                text(
                                    "UPDATE reminderrule SET threshold_hours = COALESCE(threshold_hours, 0) * 24"
                                )
                            )
                            conn.execute(
                                text(
                                    "INSERT INTO applied_data_migrations (migration_name) "
                                    "VALUES ('reminderrule_threshold_days_to_hours')"
                                )
                            )
                        print(
                            "Migrated reminderrule.threshold_days to threshold_hours",
                            file=sys.stderr,
                            flush=True,
                        )
                    elif "threshold_days" in rr_cols and "threshold_hours" in rr_cols:
                        with engine.begin() as conn:
                            conn.execute(
                                text(
                                    "UPDATE reminderrule SET threshold_hours = COALESCE(threshold_days, 0) * 24"
                                )
                            )
                            if dialect == "postgresql":
                                conn.execute(text("ALTER TABLE reminderrule DROP COLUMN threshold_days"))
                            else:
                                try:
                                    conn.execute(text("ALTER TABLE reminderrule DROP COLUMN threshold_days"))
                                except Exception as drop_e:
                                    print(
                                        f"Could not DROP threshold_days from reminderrule: {drop_e}",
                                        file=sys.stderr,
                                        flush=True,
                                    )
                            conn.execute(
                                text(
                                    "INSERT INTO applied_data_migrations (migration_name) "
                                    "VALUES ('reminderrule_threshold_days_to_hours')"
                                )
                            )
                        print(
                            "Migrated reminderrule (dual column) to threshold_hours only",
                            file=sys.stderr,
                            flush=True,
                        )
                    elif "threshold_hours" in rr_cols:
                        with engine.begin() as conn:
                            conn.execute(
                                text(
                                    "INSERT INTO applied_data_migrations (migration_name) "
                                    "VALUES ('reminderrule_threshold_days_to_hours')"
                                )
                            )
                    elif (
                        "threshold_minutes" in rr_cols
                        and "threshold_hours" not in rr_cols
                        and "threshold_days" not in rr_cols
                    ):
                        # ORM created reminderrule with threshold_minutes only (skipped legacy day columns)
                        with engine.begin() as conn:
                            conn.execute(
                                text(
                                    "INSERT INTO applied_data_migrations (migration_name) "
                                    "VALUES ('reminderrule_threshold_days_to_hours')"
                                )
                            )
            except Exception as e:
                error_str = str(e).lower()
                if "already exists" not in error_str and "duplicate" not in error_str:
                    print(
                        f"Error migrating reminderrule threshold to hours: {e}",
                        file=sys.stderr,
                        flush=True,
                    )
                    import traceback

                    print(traceback.format_exc(), file=sys.stderr, flush=True)

        # Step 9c: Migrate reminderrule.threshold_hours -> threshold_minutes (values were hours; multiply by 60)
        if has_reminder_rule_table or inspector.has_table("reminderrule"):
            try:
                with engine.begin() as conn:
                    conn.execute(
                        text(
                            """
                            CREATE TABLE IF NOT EXISTS applied_data_migrations (
                                migration_name VARCHAR(255) PRIMARY KEY,
                                applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                            )
                            """
                        )
                    )
                insp_m = inspect(engine)
                rr_cols_m = {c["name"] for c in insp_m.get_columns("reminderrule")}
                with engine.connect() as conn:
                    already_m = conn.execute(
                        text(
                            "SELECT 1 FROM applied_data_migrations "
                            "WHERE migration_name = 'reminderrule_threshold_hours_to_minutes'"
                        )
                    ).fetchone()
                if not already_m:
                    dialect_m = getattr(engine.dialect, "name", "")
                    if "threshold_hours" in rr_cols_m and "threshold_minutes" not in rr_cols_m:
                        with engine.begin() as conn:
                            conn.execute(
                                text(
                                    "ALTER TABLE reminderrule RENAME COLUMN threshold_hours TO threshold_minutes"
                                )
                            )
                            conn.execute(
                                text(
                                    "UPDATE reminderrule SET threshold_minutes = COALESCE(threshold_minutes, 0) * 60"
                                )
                            )
                            conn.execute(
                                text(
                                    "INSERT INTO applied_data_migrations (migration_name) "
                                    "VALUES ('reminderrule_threshold_hours_to_minutes')"
                                )
                            )
                        print(
                            "Migrated reminderrule.threshold_hours to threshold_minutes",
                            file=sys.stderr,
                            flush=True,
                        )
                    elif "threshold_hours" in rr_cols_m and "threshold_minutes" in rr_cols_m:
                        with engine.begin() as conn:
                            conn.execute(
                                text(
                                    "UPDATE reminderrule SET threshold_minutes = COALESCE(threshold_hours, 0) * 60"
                                )
                            )
                            if dialect_m == "postgresql":
                                conn.execute(text("ALTER TABLE reminderrule DROP COLUMN threshold_hours"))
                            else:
                                try:
                                    conn.execute(text("ALTER TABLE reminderrule DROP COLUMN threshold_hours"))
                                except Exception as drop_e:
                                    print(
                                        f"Could not DROP threshold_hours from reminderrule: {drop_e}",
                                        file=sys.stderr,
                                        flush=True,
                                    )
                            conn.execute(
                                text(
                                    "INSERT INTO applied_data_migrations (migration_name) "
                                    "VALUES ('reminderrule_threshold_hours_to_minutes')"
                                )
                            )
                        print(
                            "Migrated reminderrule (dual column) to threshold_minutes only",
                            file=sys.stderr,
                            flush=True,
                        )
                    elif "threshold_minutes" in rr_cols_m:
                        with engine.begin() as conn:
                            conn.execute(
                                text(
                                    "INSERT INTO applied_data_migrations (migration_name) "
                                    "VALUES ('reminderrule_threshold_hours_to_minutes')"
                                )
                            )
            except Exception as e:
                error_str = str(e).lower()
                if "already exists" not in error_str and "duplicate" not in error_str:
                    print(
                        f"Error migrating reminderrule threshold to minutes: {e}",
                        file=sys.stderr,
                        flush=True,
                    )
                    import traceback

                    print(traceback.format_exc(), file=sys.stderr, flush=True)
        
        # Insert any canonical default ReminderRule rows missing by rule_name (fixes partial legacy seeds)
        def _backfill_default_reminder_rules(session):
            from app.models import ReminderRule, ReminderPriority, SuggestedAction
            from sqlmodel import select
            existing = set(session.exec(select(ReminderRule.rule_name)).all())
            default_rules = [
                ReminderRule(
                    rule_name="NEW_LEAD_STALE",
                    entity_type="LEAD",
                    status="NEW",
                    threshold_minutes=4320,
                    check_type="LAST_ACTIVITY",
                    is_active=True,
                    priority=ReminderPriority.HIGH,
                    suggested_action=SuggestedAction.FOLLOW_UP,
                ),
                ReminderRule(
                    rule_name="CONTACT_ATTEMPTED_STALE",
                    entity_type="LEAD",
                    status="CONTACT_ATTEMPTED",
                    threshold_minutes=7200,
                    check_type="LAST_ACTIVITY",
                    is_active=True,
                    priority=ReminderPriority.HIGH,
                    suggested_action=SuggestedAction.FOLLOW_UP,
                ),
                ReminderRule(
                    rule_name="ENGAGED_STALE",
                    entity_type="LEAD",
                    status="ENGAGED",
                    threshold_minutes=10080,
                    check_type="LAST_ACTIVITY",
                    is_active=True,
                    priority=ReminderPriority.MEDIUM,
                    suggested_action=SuggestedAction.FOLLOW_UP,
                ),
                ReminderRule(
                    rule_name="QUALIFIED_STALE",
                    entity_type="LEAD",
                    status="QUALIFIED",
                    threshold_minutes=10080,
                    check_type="LAST_ACTIVITY",
                    is_active=True,
                    priority=ReminderPriority.MEDIUM,
                    suggested_action=SuggestedAction.CONTACT_CUSTOMER,
                ),
                ReminderRule(
                    rule_name="QUOTED_STALE",
                    entity_type="LEAD",
                    status="QUOTED",
                    threshold_minutes=7200,
                    check_type="LAST_ACTIVITY",
                    is_active=True,
                    priority=ReminderPriority.HIGH,
                    suggested_action=SuggestedAction.FOLLOW_UP,
                ),
                ReminderRule(
                    rule_name="QUOTE_SENT_STALE",
                    entity_type="QUOTE",
                    status="SENT",
                    threshold_minutes=10080,
                    check_type="SENT_DATE",
                    is_active=True,
                    priority=ReminderPriority.HIGH,
                    suggested_action=SuggestedAction.RESEND_QUOTE,
                ),
                ReminderRule(
                    rule_name="QUOTE_EXPIRED",
                    entity_type="QUOTE",
                    status=None,
                    threshold_minutes=0,
                    check_type="VALID_UNTIL",
                    is_active=True,
                    priority=ReminderPriority.URGENT,
                    suggested_action=SuggestedAction.REVIEW_QUOTE,
                ),
                ReminderRule(
                    rule_name="QUOTE_NOT_OPENED_48H",
                    entity_type="QUOTE",
                    status="SENT",
                    threshold_minutes=2880,
                    check_type="SENT_NOT_OPENED",
                    is_active=True,
                    priority=ReminderPriority.HIGH,
                    suggested_action=SuggestedAction.RESEND_QUOTE,
                ),
                ReminderRule(
                    rule_name="QUOTE_OPENED_NO_REPLY",
                    entity_type="QUOTE",
                    status="SENT",
                    threshold_minutes=7200,
                    check_type="OPENED_NO_REPLY",
                    is_active=True,
                    priority=ReminderPriority.HIGH,
                    suggested_action=SuggestedAction.PHONE_CALL,
                ),
            ]
            to_add = [r for r in default_rules if r.rule_name not in existing]
            for rule in to_add:
                session.add(rule)
            if to_add:
                session.commit()
                print(f"Backfilled {len(to_add)} default reminder rules", file=sys.stderr, flush=True)
        
        if has_reminder_rule_table or inspector.has_table("reminderrule"):
            try:
                with Session(engine) as session:
                    _backfill_default_reminder_rules(session)
            except Exception as e:
                print(f"Error backfilling default reminder rules: {e}", file=sys.stderr, flush=True)
                import traceback
                print(traceback.format_exc(), file=sys.stderr, flush=True)
        
        # Step 9a: Extend suggestedaction enum with PHONE_CALL if missing (before reminder seeding)
        if has_reminder_rule_table or inspector.has_table("reminderrule"):
            try:
                with engine.begin() as conn:
                    conn.execute(text("ALTER TYPE suggestedaction ADD VALUE IF NOT EXISTS 'PHONE_CALL'"))
                print("Added suggestedaction enum value: PHONE_CALL", file=sys.stderr, flush=True)
            except Exception as e:
                error_str = str(e).lower()
                if "already exists" not in error_str:
                    print(f"Warning: could not add suggestedaction value PHONE_CALL: {e}", file=sys.stderr, flush=True)
        
        # Step 9c: Extend remindertype enum with QUOTE_NOT_OPENED and QUOTE_OPENED_NO_REPLY (if reminder table exists)
        if has_reminder_table or inspector.has_table("reminder"):
            for enum_value in ("QUOTE_NOT_OPENED", "QUOTE_OPENED_NO_REPLY"):
                try:
                    with engine.begin() as conn:
                        conn.execute(text(f"ALTER TYPE remindertype ADD VALUE IF NOT EXISTS '{enum_value}'"))
                    print(f"Added remindertype enum value: {enum_value}", file=sys.stderr, flush=True)
                except Exception as e:
                    error_str = str(e).lower()
                    if "already exists" not in error_str:
                        print(f"Warning: could not add remindertype value {enum_value}: {e}", file=sys.stderr, flush=True)
        
        # Step 9d: USER_TASK reminders — enum value + due_date + created_by_id
        if has_reminder_table or inspector.has_table("reminder"):
            try:
                with engine.begin() as conn:
                    conn.execute(text("ALTER TYPE remindertype ADD VALUE IF NOT EXISTS 'USER_TASK'"))
                print("Added remindertype enum value: USER_TASK", file=sys.stderr, flush=True)
            except Exception as e:
                error_str = str(e).lower()
                if "already exists" not in error_str:
                    print(f"Warning: could not add remindertype value USER_TASK: {e}", file=sys.stderr, flush=True)
            reminder_columns = [col["name"] for col in inspector.get_columns("reminder")]
            if "due_date" not in reminder_columns:
                print("Adding due_date column to reminder table...", file=sys.stderr, flush=True)
                try:
                    with engine.begin() as conn:
                        conn.execute(text("ALTER TABLE reminder ADD COLUMN due_date DATE"))
                    print("Added due_date column to reminder table", file=sys.stderr, flush=True)
                except Exception as e:
                    error_str = str(e).lower()
                    if "already exists" not in error_str and "duplicate" not in error_str:
                        print(f"Warning: could not add due_date to reminder: {e}", file=sys.stderr, flush=True)
            reminder_columns = [col["name"] for col in inspector.get_columns("reminder")]
            if "created_by_id" not in reminder_columns:
                print("Adding created_by_id column to reminder table...", file=sys.stderr, flush=True)
                try:
                    with engine.begin() as conn:
                        conn.execute(text('ALTER TABLE reminder ADD COLUMN created_by_id INTEGER REFERENCES "user"(id)'))
                    print("Added created_by_id column to reminder table", file=sys.stderr, flush=True)
                except Exception as e:
                    error_str = str(e).lower()
                    if "already exists" not in error_str and "duplicate" not in error_str:
                        print(f"Warning: could not add created_by_id to reminder: {e}", file=sys.stderr, flush=True)
        
        # Step 10: Add installation_hours to Product table
        has_product_table = inspector.has_table("product")
        if has_product_table:
            product_columns = [col['name'] for col in inspector.get_columns("product")]
            if "installation_hours" not in product_columns:
                print("Adding installation_hours column to product table...", file=sys.stderr, flush=True)
                try:
                    with engine.begin() as conn:
                        conn.execute(text("ALTER TABLE product ADD COLUMN installation_hours NUMERIC(10, 2)"))
                    print("Added installation_hours column to product table", file=sys.stderr, flush=True)
                except Exception as e:
                    error_str = str(e).lower()
                    if "already exists" not in error_str and "duplicate" not in error_str:
                        print(f"Error adding installation_hours column: {e}", file=sys.stderr, flush=True)
            if "boxes_per_product" not in product_columns:
                print("Adding boxes_per_product column to product table...", file=sys.stderr, flush=True)
                try:
                    with engine.begin() as conn:
                        conn.execute(text("ALTER TABLE product ADD COLUMN boxes_per_product INTEGER"))
                    print("Added boxes_per_product column to product table", file=sys.stderr, flush=True)
                except Exception as e:
                    error_str = str(e).lower()
                    if "already exists" not in error_str and "duplicate" not in error_str:
                        print(f"Error adding boxes_per_product column: {e}", file=sys.stderr, flush=True)
            if "production_product_id" not in product_columns:
                print("Adding production_product_id column to product table...", file=sys.stderr, flush=True)
                try:
                    with engine.begin() as conn:
                        conn.execute(text("ALTER TABLE product ADD COLUMN production_product_id INTEGER"))
                        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_product_production_product_id ON product (production_product_id)"))
                    print("Added production_product_id column to product table", file=sys.stderr, flush=True)
                except Exception as e:
                    error_str = str(e).lower()
                    if "already exists" not in error_str and "duplicate" not in error_str:
                        print(f"Error adding production_product_id column: {e}", file=sys.stderr, flush=True)
            product_columns = [col["name"] for col in inspector.get_columns("product")]
            if "allow_trade_dealer_sale" not in product_columns:
                print("Adding allow_trade_dealer_sale column to product table...", file=sys.stderr, flush=True)
                try:
                    with engine.begin() as conn:
                        conn.execute(
                            text("ALTER TABLE product ADD COLUMN allow_trade_dealer_sale BOOLEAN DEFAULT FALSE")
                        )
                    print("Added allow_trade_dealer_sale column to product table", file=sys.stderr, flush=True)
                except Exception as e:
                    error_str = str(e).lower()
                    if "already exists" not in error_str and "duplicate" not in error_str:
                        print(
                            f"Error adding allow_trade_dealer_sale column: {e}",
                            file=sys.stderr,
                            flush=True,
                        )

            # Product spec sheet fields: size, height, floor_plan_url, width, length
            for col_name, col_sql in [
                ("size", "VARCHAR(100)"),
                ("height", "VARCHAR(100)"),
                ("floor_plan_url", "VARCHAR(2048)"),
                ("width", "NUMERIC(10, 2)"),
                ("length", "NUMERIC(10, 2)"),
            ]:
                product_columns = [col["name"] for col in inspector.get_columns("product")]
                if col_name not in product_columns:
                    print(f"Adding {col_name} column to product table...", file=sys.stderr, flush=True)
                    try:
                        with engine.begin() as conn:
                            conn.execute(text(f"ALTER TABLE product ADD COLUMN {col_name} {col_sql}"))
                        print(f"Added {col_name} column to product table", file=sys.stderr, flush=True)
                    except Exception as e:
                        error_str = str(e).lower()
                        if "already exists" not in error_str and "duplicate" not in error_str:
                            print(f"Error adding {col_name} column: {e}", file=sys.stderr, flush=True)

        # Step 11: Add is_giveaway to DiscountTemplate table
        has_discount_template_table = inspector.has_table("discounttemplate")
        if has_discount_template_table:
            dt_columns = [col['name'] for col in inspector.get_columns("discounttemplate")]
            if "is_giveaway" not in dt_columns:
                print("Adding is_giveaway column to discounttemplate table...", file=sys.stderr, flush=True)
                try:
                    with engine.begin() as conn:
                        conn.execute(text("ALTER TABLE discounttemplate ADD COLUMN is_giveaway BOOLEAN DEFAULT FALSE"))
                    print("Added is_giveaway column to discounttemplate table", file=sys.stderr, flush=True)
                except Exception as e:
                    error_str = str(e).lower()
                    if "already exists" not in error_str and "duplicate" not in error_str:
                        print(f"Error adding is_giveaway column: {e}", file=sys.stderr, flush=True)

            # Step 11b: max_uses, expires_at on discounttemplate; discounttemplateredemption table
            dt_columns = [col["name"] for col in inspector.get_columns("discounttemplate")]
            if "max_uses" not in dt_columns:
                print("Adding max_uses column to discounttemplate table...", file=sys.stderr, flush=True)
                try:
                    with engine.begin() as conn:
                        conn.execute(text("ALTER TABLE discounttemplate ADD COLUMN max_uses INTEGER"))
                    print("Added max_uses column to discounttemplate table", file=sys.stderr, flush=True)
                except Exception as e:
                    error_str = str(e).lower()
                    if "already exists" not in error_str and "duplicate" not in error_str:
                        print(f"Error adding max_uses column: {e}", file=sys.stderr, flush=True)
            dt_columns = [col["name"] for col in inspector.get_columns("discounttemplate")]
            if "expires_at" not in dt_columns:
                print("Adding expires_at column to discounttemplate table...", file=sys.stderr, flush=True)
                try:
                    with engine.begin() as conn:
                        conn.execute(text("ALTER TABLE discounttemplate ADD COLUMN expires_at TIMESTAMP"))
                    print("Added expires_at column to discounttemplate table", file=sys.stderr, flush=True)
                except Exception as e:
                    error_str = str(e).lower()
                    if "already exists" not in error_str and "duplicate" not in error_str:
                        print(f"Error adding expires_at column: {e}", file=sys.stderr, flush=True)

        if not inspector.has_table("discounttemplateredemption"):
            print("Creating discounttemplateredemption table...", file=sys.stderr, flush=True)
            try:
                with engine.begin() as conn:
                    conn.execute(
                        text(
                            """
                            CREATE TABLE discounttemplateredemption (
                                id SERIAL PRIMARY KEY,
                                template_id INTEGER NOT NULL REFERENCES discounttemplate(id) ON DELETE CASCADE,
                                quote_id INTEGER NOT NULL REFERENCES quote(id) ON DELETE CASCADE,
                                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                                CONSTRAINT uq_discount_redemption_template_quote UNIQUE (template_id, quote_id)
                            )
                            """
                        )
                    )
                print("Created discounttemplateredemption table", file=sys.stderr, flush=True)
            except Exception as e:
                error_str = str(e).lower()
                if "already exists" not in error_str and "duplicate" not in error_str:
                    print(f"Error creating discounttemplateredemption: {e}", file=sys.stderr, flush=True)
        
        # Step 12: Add parent_quote_item_id to QuoteItem table
        has_quoteitem_table = inspector.has_table("quoteitem")
        if has_quoteitem_table:
            quoteitem_columns = [col['name'] for col in inspector.get_columns("quoteitem")]
            if "parent_quote_item_id" not in quoteitem_columns:
                print("Adding parent_quote_item_id column to quoteitem table...", file=sys.stderr, flush=True)
                try:
                    with engine.begin() as conn:
                        conn.execute(text("ALTER TABLE quoteitem ADD COLUMN parent_quote_item_id INTEGER REFERENCES quoteitem(id)"))
                    print("Added parent_quote_item_id column to quoteitem table", file=sys.stderr, flush=True)
                except Exception as e:
                    error_str = str(e).lower()
                    if "already exists" not in error_str and "duplicate" not in error_str:
                        print(f"Error adding parent_quote_item_id column: {e}", file=sys.stderr, flush=True)
        
        # Step 12b: Add line_type to QuoteItem table (DELIVERY/INSTALLATION excluded from product discount)
        if has_quoteitem_table:
            quoteitem_columns = [col['name'] for col in inspector.get_columns("quoteitem")]
            if "line_type" not in quoteitem_columns:
                print("Adding line_type column to quoteitem table...", file=sys.stderr, flush=True)
                try:
                    with engine.begin() as conn:
                        conn.execute(text("ALTER TABLE quoteitem ADD COLUMN line_type VARCHAR(20)"))
                    print("Added line_type column to quoteitem table", file=sys.stderr, flush=True)
                except Exception as e:
                    error_str = str(e).lower()
                    if "already exists" not in error_str and "duplicate" not in error_str:
                        print(f"Error adding line_type column: {e}", file=sys.stderr, flush=True)

        # Step 12c: include_in_building_discount on QuoteItem (opt out of PRODUCT-scope discount per line)
        if has_quoteitem_table:
            quoteitem_columns = [col["name"] for col in inspector.get_columns("quoteitem")]
            if "include_in_building_discount" not in quoteitem_columns:
                print("Adding include_in_building_discount column to quoteitem table...", file=sys.stderr, flush=True)
                try:
                    with engine.begin() as conn:
                        conn.execute(
                            text(
                                "ALTER TABLE quoteitem ADD COLUMN include_in_building_discount BOOLEAN DEFAULT TRUE"
                            )
                        )
                    print("Added include_in_building_discount column to quoteitem table", file=sys.stderr, flush=True)
                except Exception as e:
                    error_str = str(e).lower()
                    if "already exists" not in error_str and "duplicate" not in error_str:
                        print(f"Error adding include_in_building_discount column: {e}", file=sys.stderr, flush=True)

        # Step 13: Add read_at to SmsMessage table (unread tracking for received SMS)
        has_smsmessage_table = inspector.has_table("smsmessage")
        if has_smsmessage_table:
            sms_columns = [col['name'] for col in inspector.get_columns("smsmessage")]
            if "read_at" not in sms_columns:
                print("Adding read_at column to smsmessage table...", file=sys.stderr, flush=True)
                try:
                    with engine.begin() as conn:
                        conn.execute(text("ALTER TABLE smsmessage ADD COLUMN read_at TIMESTAMP"))
                    print("Added read_at column to smsmessage table", file=sys.stderr, flush=True)
                except Exception as e:
                    error_str = str(e).lower()
                    if "already exists" not in error_str and "duplicate" not in error_str:
                        print(f"Error adding read_at column: {e}", file=sys.stderr, flush=True)

        # Step 13b: Add read_at to Email table (unread tracking for received inbound mail)
        has_email_table = inspector.has_table("email")
        if has_email_table:
            email_columns = [col["name"] for col in inspector.get_columns("email")]
            if "read_at" not in email_columns:
                print("Adding read_at column to email table...", file=sys.stderr, flush=True)
                try:
                    with engine.begin() as conn:
                        conn.execute(text("ALTER TABLE email ADD COLUMN read_at TIMESTAMP"))
                        # Historical RECEIVED rows: treat as already read so deploy does not flood the UI
                        conn.execute(
                            text(
                                "UPDATE email SET read_at = COALESCE(received_at, created_at) "
                                "WHERE direction = 'RECEIVED'"
                            )
                        )
                    print("Added read_at column to email table and backfilled RECEIVED rows", file=sys.stderr, flush=True)
                except Exception as e:
                    error_str = str(e).lower()
                    if "already exists" not in error_str and "duplicate" not in error_str:
                        print(f"Error adding read_at to email: {e}", file=sys.stderr, flush=True)

        # Step 13c: Scheduled SMS schema hardening (FAILED status + failure_reason)
        has_scheduledsms_table = inspector.has_table("scheduledsms")
        if has_scheduledsms_table:
            # Ensure enum includes FAILED for one-shot failure finalization.
            try:
                with engine.begin() as conn:
                    conn.execute(text("ALTER TYPE scheduledsmsstatus ADD VALUE IF NOT EXISTS 'FAILED'"))
                print("Ensured scheduledsmsstatus enum value: FAILED", file=sys.stderr, flush=True)
            except Exception as e:
                error_str = str(e).lower()
                # Non-Postgres DBs or preexisting enum values can safely continue.
                if "already exists" not in error_str and "duplicate" not in error_str:
                    print(f"Warning: could not ensure scheduledsmsstatus value FAILED: {e}", file=sys.stderr, flush=True)

            scheduledsms_columns = [col["name"] for col in inspector.get_columns("scheduledsms")]
            if "failure_reason" not in scheduledsms_columns:
                print("Adding failure_reason column to scheduledsms table...", file=sys.stderr, flush=True)
                try:
                    with engine.begin() as conn:
                        conn.execute(text("ALTER TABLE scheduledsms ADD COLUMN failure_reason TEXT"))
                    print("Added failure_reason column to scheduledsms table", file=sys.stderr, flush=True)
                except Exception as e:
                    error_str = str(e).lower()
                    if "already exists" not in error_str and "duplicate" not in error_str:
                        print(f"Error adding failure_reason to scheduledsms: {e}", file=sys.stderr, flush=True)

        # Step 14: ReminderRule customer outreach + CustomerOutreachSend audit table
        if has_reminder_rule_table:
            outreach_alters = [
                ("customer_outreach_channel", "ALTER TABLE reminderrule ADD COLUMN customer_outreach_channel VARCHAR(10)"),
                ("customer_outreach_sms_template_id", "ALTER TABLE reminderrule ADD COLUMN customer_outreach_sms_template_id INTEGER REFERENCES smstemplate(id)"),
                ("customer_outreach_email_template_id", "ALTER TABLE reminderrule ADD COLUMN customer_outreach_email_template_id INTEGER REFERENCES emailtemplate(id)"),
                ("customer_outreach_cooldown_days", "ALTER TABLE reminderrule ADD COLUMN customer_outreach_cooldown_days INTEGER DEFAULT 14 NOT NULL"),
                ("outreach_enabled_from_utc", "ALTER TABLE reminderrule ADD COLUMN outreach_enabled_from_utc TIMESTAMP"),
                (
                    "customer_outreach_on_lead_create",
                    "ALTER TABLE reminderrule ADD COLUMN customer_outreach_on_lead_create BOOLEAN DEFAULT FALSE NOT NULL",
                ),
            ]
            for col_name, ddl in outreach_alters:
                rr_columns = [col["name"] for col in inspector.get_columns("reminderrule")]
                if col_name not in rr_columns:
                    print(f"Adding {col_name} to reminderrule...", file=sys.stderr, flush=True)
                    try:
                        with engine.begin() as conn:
                            conn.execute(text(ddl))
                    except Exception as e:
                        error_str = str(e).lower()
                        if "already exists" not in error_str and "duplicate" not in error_str:
                            print(f"Error adding {col_name} to reminderrule: {e}", file=sys.stderr, flush=True)

            try:
                with engine.begin() as conn:
                    conn.execute(
                        text(
                            "UPDATE reminderrule SET customer_outreach_cooldown_days = 14 "
                            "WHERE customer_outreach_cooldown_days IS NULL"
                        )
                    )
            except Exception:
                pass

        has_outreach_table = inspector.has_table("customeroutreachsend")
        if not has_outreach_table:
            print("Creating customeroutreachsend table...", file=sys.stderr, flush=True)
            try:
                with engine.begin() as conn:
                    conn.execute(
                        text(
                            """
                            CREATE TABLE customeroutreachsend (
                                id SERIAL PRIMARY KEY,
                                reminder_rule_id INTEGER NOT NULL REFERENCES reminderrule(id) ON DELETE CASCADE,
                                customer_id INTEGER NOT NULL REFERENCES customer(id) ON DELETE CASCADE,
                                channel VARCHAR(10) NOT NULL,
                                lead_id INTEGER REFERENCES lead(id) ON DELETE SET NULL,
                                quote_id INTEGER REFERENCES quote(id) ON DELETE SET NULL,
                                external_message_id VARCHAR(512),
                                status VARCHAR(16) NOT NULL DEFAULT 'SENT',
                                failure_reason TEXT,
                                sent_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                            )
                            """
                        )
                    )
                    conn.execute(
                        text(
                            "CREATE INDEX ix_customeroutreachsend_rule_lead ON customeroutreachsend (reminder_rule_id, lead_id)"
                        )
                    )
                    conn.execute(
                        text(
                            "CREATE INDEX ix_customeroutreachsend_rule_quote ON customeroutreachsend (reminder_rule_id, quote_id)"
                        )
                    )
                print("Created customeroutreachsend table", file=sys.stderr, flush=True)
            except Exception as e:
                error_str = str(e).lower()
                if "already exists" not in error_str and "duplicate" not in error_str:
                    print(f"Error creating customeroutreachsend: {e}", file=sys.stderr, flush=True)
        else:
            outreach_columns = [col["name"] for col in inspector.get_columns("customeroutreachsend")]
            if "status" not in outreach_columns:
                print("Adding status column to customeroutreachsend table...", file=sys.stderr, flush=True)
                try:
                    with engine.begin() as conn:
                        conn.execute(
                            text(
                                "ALTER TABLE customeroutreachsend "
                                "ADD COLUMN status VARCHAR(16) DEFAULT 'SENT' NOT NULL"
                            )
                        )
                except Exception as e:
                    error_str = str(e).lower()
                    if "already exists" not in error_str and "duplicate" not in error_str:
                        print(f"Error adding status to customeroutreachsend: {e}", file=sys.stderr, flush=True)
            if "failure_reason" not in outreach_columns:
                print("Adding failure_reason column to customeroutreachsend table...", file=sys.stderr, flush=True)
                try:
                    with engine.begin() as conn:
                        conn.execute(text("ALTER TABLE customeroutreachsend ADD COLUMN failure_reason TEXT"))
                except Exception as e:
                    error_str = str(e).lower()
                    if "already exists" not in error_str and "duplicate" not in error_str:
                        print(f"Error adding failure_reason to customeroutreachsend: {e}", file=sys.stderr, flush=True)

        # Facebook advert schema: handled by _ensure_facebook_advert_schema() immediately after create_all.

        # messenger_message table is created by SQLModel.metadata.create_all() when MessengerMessage model is imported
        
        print("Migration check completed", file=sys.stderr, flush=True)
    except Exception as e:
        # Log error but don't crash - migration might have already run
        import traceback
        print(f"Migration error: {e}", file=sys.stderr, flush=True)
        print(traceback.format_exc(), file=sys.stderr, flush=True)

    try:
        with Session(engine) as session:
            from app.system_user_service import get_or_create_system_user

            get_or_create_system_user(session)
    except Exception as e:
        print(f"System user ensure skipped: {e}", file=sys.stderr, flush=True)

    try:
        with Session(engine) as session:
            from app.archive_service import apply_auto_archive

            r = apply_auto_archive(session)
            if r["leads_archived"] or r["quotes_archived"]:
                print(f"Auto-archive on startup: {r}", file=sys.stderr, flush=True)
    except Exception as e:
        print(f"Auto-archive pass skipped: {e}", file=sys.stderr, flush=True)


def get_session() -> Generator[Session, None, None]:
    with Session(engine) as session:
        yield session
