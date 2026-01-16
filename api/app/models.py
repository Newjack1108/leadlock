from sqlmodel import SQLModel, Field, Relationship, Column
from sqlalchemy import Numeric
from typing import Optional, List
from datetime import datetime
from enum import Enum
from decimal import Decimal


class UserRole(str, Enum):
    DIRECTOR = "DIRECTOR"
    SALES_MANAGER = "SALES_MANAGER"
    CLOSER = "CLOSER"


class LeadStatus(str, Enum):
    NEW = "NEW"
    CONTACT_ATTEMPTED = "CONTACT_ATTEMPTED"
    ENGAGED = "ENGAGED"
    QUALIFIED = "QUALIFIED"
    QUOTED = "QUOTED"
    WON = "WON"
    LOST = "LOST"


class ActivityType(str, Enum):
    SMS_SENT = "SMS_SENT"
    SMS_RECEIVED = "SMS_RECEIVED"
    EMAIL_SENT = "EMAIL_SENT"
    EMAIL_RECEIVED = "EMAIL_RECEIVED"
    CALL_ATTEMPTED = "CALL_ATTEMPTED"
    LIVE_CALL = "LIVE_CALL"
    WHATSAPP_SENT = "WHATSAPP_SENT"
    WHATSAPP_RECEIVED = "WHATSAPP_RECEIVED"
    NOTE = "NOTE"


class Timeframe(str, Enum):
    UNKNOWN = "UNKNOWN"
    IMMEDIATE = "IMMEDIATE"
    WITHIN_MONTH = "WITHIN_MONTH"
    WITHIN_QUARTER = "WITHIN_QUARTER"
    WITHIN_YEAR = "WITHIN_YEAR"
    EXPLORING = "EXPLORING"


class ProductCategory(str, Enum):
    STABLES = "STABLES"
    SHEDS = "SHEDS"
    CABINS = "CABINS"


class LeadType(str, Enum):
    UNKNOWN = "UNKNOWN"
    STABLES = "STABLES"
    SHEDS = "SHEDS"
    CABINS = "CABINS"


class LeadSource(str, Enum):
    UNKNOWN = "UNKNOWN"
    FACEBOOK = "FACEBOOK"
    INSTAGRAM = "INSTAGRAM"
    WEBSITE = "WEBSITE"
    MANUAL_ENTRY = "MANUAL_ENTRY"
    SMS = "SMS"
    EMAIL = "EMAIL"
    PHONE = "PHONE"
    REFERRAL = "REFERRAL"
    OTHER = "OTHER"


class User(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    email: str = Field(unique=True, index=True)
    hashed_password: str
    full_name: str
    role: UserRole
    created_at: datetime = Field(default_factory=datetime.utcnow)
    
    # Email Settings (per-user)
    smtp_host: Optional[str] = None
    smtp_port: Optional[int] = None
    smtp_user: Optional[str] = None
    smtp_password: Optional[str] = None
    smtp_use_tls: bool = Field(default=True)
    smtp_from_email: Optional[str] = None
    smtp_from_name: Optional[str] = None
    imap_host: Optional[str] = None
    imap_port: Optional[int] = None
    imap_user: Optional[str] = None
    imap_password: Optional[str] = None
    imap_use_ssl: bool = Field(default=True)
    email_signature: Optional[str] = None  # HTML signature with logo support
    email_test_mode: bool = Field(default=False)  # When enabled, emails are saved but not sent via SMTP
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    
    # Relationships
    assigned_leads: List["Lead"] = Relationship(back_populates="assigned_to_user")


class Customer(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    customer_number: str = Field(unique=True, index=True)  # Auto-generated unique identifier
    name: str
    email: Optional[str] = None
    phone: Optional[str] = None
    address_line1: Optional[str] = None
    address_line2: Optional[str] = None
    city: Optional[str] = None
    county: Optional[str] = None
    postcode: Optional[str] = None
    country: Optional[str] = Field(default="United Kingdom")
    customer_since: datetime = Field(default_factory=datetime.utcnow)  # When first qualified
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    
    # Relationships
    leads: List["Lead"] = Relationship(back_populates="customer")
    quotes: List["Quote"] = Relationship(back_populates="customer")
    activities: List["Activity"] = Relationship(back_populates="customer")
    emails: List["Email"] = Relationship(back_populates="customer")


class Lead(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    email: Optional[str] = None
    phone: Optional[str] = None
    postcode: Optional[str] = None
    description: Optional[str] = None
    # Lead-specific fields
    status: LeadStatus = Field(default=LeadStatus.NEW)
    timeframe: Timeframe = Field(default=Timeframe.UNKNOWN)
    scope_notes: Optional[str] = None
    product_interest: Optional[str] = None
    lead_type: LeadType = Field(default=LeadType.UNKNOWN)
    lead_source: LeadSource = Field(default=LeadSource.UNKNOWN)
    assigned_to_id: Optional[int] = Field(default=None, foreign_key="user.id")
    customer_id: Optional[int] = Field(default=None, foreign_key="customer.id")  # Link to Customer when qualified
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    
    # Relationships
    assigned_to_user: Optional[User] = Relationship(back_populates="assigned_leads")
    customer: Optional["Customer"] = Relationship(back_populates="leads")
    status_history: List["StatusHistory"] = Relationship(back_populates="lead")


class Activity(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    customer_id: Optional[int] = Field(default=None, foreign_key="customer.id")  # Temporarily nullable for migration
    activity_type: ActivityType
    notes: Optional[str] = None
    created_by_id: int = Field(foreign_key="user.id")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    
    # Relationships
    customer: Optional["Customer"] = Relationship(back_populates="activities")
    created_by: "User" = Relationship()


class EmailDirection(str, Enum):
    SENT = "SENT"
    RECEIVED = "RECEIVED"


class Email(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    customer_id: int = Field(foreign_key="customer.id")
    message_id: Optional[str] = Field(default=None, unique=True, index=True)  # Email Message-ID header
    in_reply_to: Optional[str] = Field(default=None, index=True)  # In-Reply-To header
    thread_id: Optional[str] = Field(default=None, index=True)  # Group related emails
    direction: EmailDirection
    from_email: str
    to_email: str
    cc: Optional[str] = None  # Comma-separated
    bcc: Optional[str] = None  # Comma-separated
    subject: str
    body_html: Optional[str] = None
    body_text: Optional[str] = None
    attachments: Optional[str] = None  # JSON array of attachment metadata
    sent_at: Optional[datetime] = None
    received_at: Optional[datetime] = None
    created_by_id: Optional[int] = Field(default=None, foreign_key="user.id")  # For sent emails
    created_at: datetime = Field(default_factory=datetime.utcnow)
    
    # Relationships
    customer: "Customer" = Relationship(back_populates="emails")
    created_by: Optional["User"] = Relationship()


class StatusHistory(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    lead_id: int = Field(foreign_key="lead.id")
    old_status: Optional[LeadStatus] = None
    new_status: LeadStatus
    changed_by_id: int = Field(foreign_key="user.id")
    override_reason: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    
    # Relationships
    lead: Lead = Relationship(back_populates="status_history")
    changed_by: "User" = Relationship()


class Product(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    description: Optional[str] = None
    category: ProductCategory
    subcategory: Optional[str] = None  # For "Extras" or other subcategories
    is_extra: bool = Field(default=False)  # True if this is an optional extra
    base_price: Decimal = Field(sa_column=Column(Numeric(10, 2)))
    unit: str = Field(default="unit")  # e.g., "unit", "sqft", "per item"
    sku: Optional[str] = None  # Stock keeping unit (optional)
    is_active: bool = Field(default=True)  # For soft deletion
    image_url: Optional[str] = None  # Product image URL
    specifications: Optional[str] = None  # Technical specs (JSON or text)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    
    # Relationships
    quote_items: List["QuoteItem"] = Relationship(back_populates="product")


class CompanySettings(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    company_name: str
    trading_name: Optional[str] = None  # Trading name for quotes/branding
    company_registration_number: Optional[str] = None  # Company reg number
    vat_number: Optional[str] = None  # VAT number
    address_line1: Optional[str] = None
    address_line2: Optional[str] = None
    city: Optional[str] = None
    county: Optional[str] = None
    postcode: Optional[str] = None
    country: str = Field(default="United Kingdom")
    phone: Optional[str] = None
    email: Optional[str] = None
    website: Optional[str] = None
    logo_filename: str = Field(default="logo1.jpg")  # Company logo for quotes (different from app logo)
    updated_by_id: int = Field(foreign_key="user.id")
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    
    # Relationships
    updated_by: User = Relationship()


class QuoteStatus(str, Enum):
    DRAFT = "DRAFT"
    SENT = "SENT"
    VIEWED = "VIEWED"
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"


class OpportunityStage(str, Enum):
    DISCOVERY = "DISCOVERY"  # Discovery / Site Info
    CONCEPT = "CONCEPT"  # Concept / Configuration
    QUOTE_SENT = "QUOTE_SENT"  # Quote Sent
    FOLLOW_UP = "FOLLOW_UP"  # Follow-Up
    DECISION_PENDING = "DECISION_PENDING"  # Decision Pending
    WON = "WON"
    LOST = "LOST"


class LossCategory(str, Enum):
    PRICE = "PRICE"
    TIMING = "TIMING"
    COMPETITOR = "COMPETITOR"
    PLANNING = "PLANNING"
    OTHER = "OTHER"


class DiscountType(str, Enum):
    FIXED_AMOUNT = "FIXED_AMOUNT"
    PERCENTAGE = "PERCENTAGE"


class DiscountScope(str, Enum):
    PRODUCT = "PRODUCT"  # Applied to individual line items
    QUOTE = "QUOTE"  # Applied to entire quote total


class Quote(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    customer_id: Optional[int] = Field(default=None, foreign_key="customer.id")  # Temporarily nullable for migration
    quote_number: str = Field(unique=True, index=True)  # e.g., "QT-2024-001"
    version: int = Field(default=1)  # For quote revisions
    status: QuoteStatus = Field(default=QuoteStatus.DRAFT)
    subtotal: Decimal = Field(sa_column=Column(Numeric(10, 2)))  # Sum of all line items (before discounts)
    discount_total: Decimal = Field(default=0, sa_column=Column(Numeric(10, 2)))  # Total of all discounts applied
    total_amount: Decimal = Field(sa_column=Column(Numeric(10, 2)))  # subtotal - discount_total (final amount)
    deposit_amount: Decimal = Field(default=0, sa_column=Column(Numeric(10, 2)))  # Deposit amount (default 50% of total)
    balance_amount: Decimal = Field(default=0, sa_column=Column(Numeric(10, 2)))  # Balance amount (total - deposit)
    currency: str = Field(default="GBP")
    valid_until: Optional[datetime] = None
    terms_and_conditions: Optional[str] = None
    notes: Optional[str] = None
    created_by_id: int = Field(foreign_key="user.id")
    sent_at: Optional[datetime] = None
    viewed_at: Optional[datetime] = None
    accepted_at: Optional[datetime] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    
    # Opportunity management fields
    opportunity_stage: Optional["OpportunityStage"] = Field(default=None)
    close_probability: Optional[Decimal] = Field(default=None, sa_column=Column(Numeric(5, 2)))  # 0-100 percentage
    expected_close_date: Optional[datetime] = None
    next_action: Optional[str] = None
    next_action_due_date: Optional[datetime] = None
    loss_reason: Optional[str] = None
    loss_category: Optional["LossCategory"] = None
    owner_id: Optional[int] = Field(default=None, foreign_key="user.id")  # Opportunity owner (can differ from created_by)
    
    # Relationships
    customer: Optional["Customer"] = Relationship(back_populates="quotes")
    items: List["QuoteItem"] = Relationship(back_populates="quote")
    discounts: List["QuoteDiscount"] = Relationship(back_populates="quote")
    created_by: User = Relationship()
    owner: Optional["User"] = Relationship(foreign_keys=[owner_id])
    email_sends: List["QuoteEmail"] = Relationship(back_populates="quote")


class QuoteItem(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    quote_id: int = Field(foreign_key="quote.id")
    product_id: Optional[int] = Field(default=None, foreign_key="product.id")  # Reference to product
    description: str  # Can be from product or custom
    quantity: Decimal = Field(default=1, sa_column=Column(Numeric(10, 2)))
    unit_price: Decimal = Field(sa_column=Column(Numeric(10, 2)))  # Can be from product base_price or custom
    line_total: Decimal = Field(sa_column=Column(Numeric(10, 2)))  # quantity * unit_price (before discount)
    discount_amount: Decimal = Field(default=0, sa_column=Column(Numeric(10, 2)))  # Discount applied to this line item
    final_line_total: Decimal = Field(sa_column=Column(Numeric(10, 2)))  # line_total - discount_amount
    sort_order: int = Field(default=0)
    is_custom: bool = Field(default=False)  # True if not from product catalog
    
    # Relationships
    quote: Quote = Relationship(back_populates="items")
    product: Optional[Product] = Relationship(back_populates="quote_items")
    discounts: List["QuoteDiscount"] = Relationship(back_populates="quote_item")


class QuoteEmail(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    quote_id: int = Field(foreign_key="quote.id")
    to_email: str
    subject: str
    body_html: str
    body_text: Optional[str] = None
    sent_at: datetime = Field(default_factory=datetime.utcnow)
    opened_at: Optional[datetime] = None
    clicked_at: Optional[datetime] = None
    tracking_id: str = Field(unique=True, index=True)  # For email tracking
    
    # Relationships
    quote: Quote = Relationship(back_populates="email_sends")


class QuoteTemplate(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    description: Optional[str] = None
    email_subject_template: str
    email_body_template: str  # Jinja2 template
    pdf_template_path: Optional[str] = None
    is_default: bool = Field(default=False)
    created_by_id: int = Field(foreign_key="user.id")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    
    # Relationships
    created_by: User = Relationship()


class EmailTemplate(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    description: Optional[str] = None
    subject_template: str  # Jinja2 template for subject
    body_template: str  # Jinja2 template for body (HTML)
    is_default: bool = Field(default=False)
    created_by_id: int = Field(foreign_key="user.id")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    
    # Relationships
    created_by: User = Relationship()


class DiscountTemplate(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str  # e.g., "10% Off", "£50 New Customer Discount"
    description: Optional[str] = None
    discount_type: DiscountType
    discount_value: Decimal = Field(sa_column=Column(Numeric(10, 2)))  # Amount or percentage (e.g., 10 for 10%)
    scope: DiscountScope  # PRODUCT or QUOTE
    is_active: bool = Field(default=True)
    created_by_id: int = Field(foreign_key="user.id")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    
    # Relationships
    created_by: User = Relationship()
    quote_discounts: List["QuoteDiscount"] = Relationship(back_populates="template")


class QuoteDiscount(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    quote_id: int = Field(foreign_key="quote.id")
    quote_item_id: Optional[int] = Field(default=None, foreign_key="quoteitem.id")  # None if quote-level discount
    template_id: Optional[int] = Field(default=None, foreign_key="discounttemplate.id")  # Reference to template
    discount_type: DiscountType
    discount_value: Decimal = Field(sa_column=Column(Numeric(10, 2)))
    scope: DiscountScope
    discount_amount: Decimal = Field(sa_column=Column(Numeric(10, 2)))  # Calculated discount amount
    description: str  # Display description (from template or custom)
    applied_at: datetime = Field(default_factory=datetime.utcnow)
    applied_by_id: int = Field(foreign_key="user.id")
    
    # Relationships
    quote: Quote = Relationship(back_populates="discounts")
    quote_item: Optional[QuoteItem] = Relationship(back_populates="discounts")
    template: Optional[DiscountTemplate] = Relationship(back_populates="quote_discounts")
    applied_by: User = Relationship()


class ReminderPriority(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    URGENT = "URGENT"


class ReminderType(str, Enum):
    LEAD_STALE = "LEAD_STALE"
    QUOTE_STALE = "QUOTE_STALE"
    QUOTE_EXPIRING = "QUOTE_EXPIRING"
    QUOTE_EXPIRED = "QUOTE_EXPIRED"


class SuggestedAction(str, Enum):
    FOLLOW_UP = "FOLLOW_UP"
    MARK_LOST = "MARK_LOST"
    RESEND_QUOTE = "RESEND_QUOTE"
    REVIEW_QUOTE = "REVIEW_QUOTE"
    CONTACT_CUSTOMER = "CONTACT_CUSTOMER"


class Reminder(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    reminder_type: ReminderType
    lead_id: Optional[int] = Field(default=None, foreign_key="lead.id")
    quote_id: Optional[int] = Field(default=None, foreign_key="quote.id")
    customer_id: Optional[int] = Field(default=None, foreign_key="customer.id")
    assigned_to_id: int = Field(foreign_key="user.id")  # User who should act
    priority: ReminderPriority = Field(default=ReminderPriority.MEDIUM)
    title: str
    message: str
    suggested_action: SuggestedAction
    days_stale: int
    created_at: datetime = Field(default_factory=datetime.utcnow)
    dismissed_at: Optional[datetime] = None
    acted_upon_at: Optional[datetime] = None
    
    # Relationships
    lead: Optional["Lead"] = Relationship()
    quote: Optional["Quote"] = Relationship()
    customer: Optional["Customer"] = Relationship()
    assigned_to: User = Relationship()


class ReminderRule(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    rule_name: str = Field(unique=True, index=True)  # "NEW_LEAD_STALE", "QUOTE_SENT_STALE"
    entity_type: str  # "LEAD", "QUOTE"
    status: Optional[str] = None  # LeadStatus or QuoteStatus value as string
    threshold_days: int
    check_type: str  # "LAST_ACTIVITY", "STATUS_DURATION", "SENT_DATE", "VALID_UNTIL"
    is_active: bool = Field(default=True)
    priority: ReminderPriority = Field(default=ReminderPriority.MEDIUM)
    suggested_action: SuggestedAction
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
