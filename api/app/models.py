from sqlmodel import SQLModel, Field, Relationship, Column
from sqlalchemy.orm import relationship
from sqlalchemy import Numeric, JSON
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
    MESSENGER_SENT = "MESSENGER_SENT"
    MESSENGER_RECEIVED = "MESSENGER_RECEIVED"
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


class TrackedWebsite(str, Enum):
    CHESHIRE_STABLES = "CHESHIRE_STABLES"
    CSGB = "CSGB"
    BLC = "BLC"


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
    messenger_psid: Optional[str] = Field(default=None, unique=True, index=True)  # Facebook Page-Scoped ID for Messenger
    
    # Relationships
    leads: List["Lead"] = Relationship(back_populates="customer")
    quotes: List["Quote"] = Relationship(back_populates="customer")
    orders: List["Order"] = Relationship(back_populates="customer")
    activities: List["Activity"] = Relationship(back_populates="customer")
    emails: List["Email"] = Relationship(back_populates="customer")
    sms_messages: List["SmsMessage"] = Relationship(back_populates="customer")
    messenger_messages: List["MessengerMessage"] = Relationship(back_populates="customer")
    website_visits: List["WebsiteVisit"] = Relationship(back_populates="customer")


class WebsiteVisit(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    customer_id: int = Field(foreign_key="customer.id")
    site: TrackedWebsite
    visited_at: datetime = Field(default_factory=datetime.utcnow)

    # Relationships
    customer: Optional["Customer"] = Relationship(back_populates="website_visits")


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
    messenger_psid: Optional[str] = Field(default=None, index=True)  # Facebook Page-Scoped ID for Messenger
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


class SmsDirection(str, Enum):
    SENT = "SENT"
    RECEIVED = "RECEIVED"


class SmsMessage(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    customer_id: int = Field(foreign_key="customer.id")
    lead_id: Optional[int] = Field(default=None, foreign_key="lead.id")
    direction: SmsDirection
    from_phone: str
    to_phone: str
    body: str
    twilio_sid: Optional[str] = Field(default=None, index=True)
    sent_at: Optional[datetime] = None
    received_at: Optional[datetime] = None
    read_at: Optional[datetime] = None  # When RECEIVED message was read (null = unread)
    created_by_id: Optional[int] = Field(default=None, foreign_key="user.id")
    created_at: datetime = Field(default_factory=datetime.utcnow)

    # Relationships
    customer: "Customer" = Relationship(back_populates="sms_messages")
    created_by: Optional["User"] = Relationship()


class MessengerDirection(str, Enum):
    SENT = "SENT"
    RECEIVED = "RECEIVED"


class MessengerMessage(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    customer_id: int = Field(foreign_key="customer.id")
    lead_id: Optional[int] = Field(default=None, foreign_key="lead.id")
    direction: MessengerDirection
    from_psid: str  # Sender PSID (user for RECEIVED, our page for SENT)
    to_psid: Optional[str] = None  # Recipient PSID (our page for RECEIVED, user for SENT)
    body: str
    facebook_mid: Optional[str] = Field(default=None, index=True)  # Facebook message ID
    sent_at: Optional[datetime] = None
    received_at: Optional[datetime] = None
    read_at: Optional[datetime] = None  # When RECEIVED message was read (null = unread)
    created_by_id: Optional[int] = Field(default=None, foreign_key="user.id")
    created_at: datetime = Field(default_factory=datetime.utcnow)

    # Relationships
    customer: "Customer" = Relationship(back_populates="messenger_messages")
    created_by: Optional["User"] = Relationship()


class ScheduledSmsStatus(str, Enum):
    PENDING = "PENDING"
    SENT = "SENT"
    CANCELLED = "CANCELLED"


class ScheduledSms(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    customer_id: int = Field(foreign_key="customer.id")
    to_phone: str
    body: str
    scheduled_at: datetime
    status: ScheduledSmsStatus = Field(default=ScheduledSmsStatus.PENDING)
    created_by_id: int = Field(foreign_key="user.id")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    sent_at: Optional[datetime] = None
    twilio_sid: Optional[str] = None

    # Relationships
    created_by: "User" = Relationship()


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
    installation_hours: Optional[Decimal] = Field(default=None, sa_column=Column(Numeric(10, 2)))  # Hours required for installation
    boxes_per_product: Optional[int] = None  # Number of boxes per product (optional; used in installation calculation)
    production_product_id: Optional[int] = Field(default=None, index=True)  # Production app's product ID for sync
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    
    # Relationships
    quote_items: List["QuoteItem"] = Relationship(back_populates="product")


class InstallationLeadTime(str, Enum):
    """Installation lead time options for quotes. Amended by production, visible to sales."""
    ONE_TWO_WEEKS = "1-2 weeks"
    TWO_THREE_WEEKS = "2-3 weeks"
    THREE_FOUR_WEEKS = "3-4 weeks"
    FOUR_FIVE_WEEKS = "4-5 weeks"
    FIVE_SIX_WEEKS = "5-6 weeks"


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
    logo_url: Optional[str] = None  # Uploaded logo URL (Cloudinary or /static/...); preferred over logo_filename for PDFs
    default_terms_and_conditions: Optional[str] = None  # Default terms and conditions for quotes
    hourly_install_rate: Optional[Decimal] = Field(default=None, sa_column=Column(Numeric(10, 2)))  # Hourly rate for installation cost calculation
    installation_lead_time: Optional[InstallationLeadTime] = Field(default=None)  # Current lead time; amended by production, visible to sales
    # Installation & travel (mileage, overnight, 2-man team)
    distance_before_overnight_miles: Optional[Decimal] = Field(default=None, sa_column=Column(Numeric(10, 2)))  # Stay away if distance > this
    cost_per_mile: Optional[Decimal] = Field(default=None, sa_column=Column(Numeric(10, 2)))  # Applied to return distance
    hotel_allowance_per_night: Optional[Decimal] = Field(default=None, sa_column=Column(Numeric(10, 2)))  # Per person; ×2 for 2-man team
    meal_allowance_per_day: Optional[Decimal] = Field(default=None, sa_column=Column(Numeric(10, 2)))  # Per person when staying away
    average_speed_mph: Optional[Decimal] = Field(default=None, sa_column=Column(Numeric(5, 2)))  # For travel time calculation
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


class QuoteTemperature(str, Enum):
    HOT = "HOT"
    WARM = "WARM"
    COLD = "COLD"


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


class QuoteItemLineType(str, Enum):
    """Line types excluded from PRODUCT-scope discounts. None = building product."""
    DELIVERY = "DELIVERY"
    INSTALLATION = "INSTALLATION"


class DiscountRequestStatus(str, Enum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


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
    viewed_at: Optional[datetime] = None  # First time quote view link was opened
    last_viewed_at: Optional[datetime] = None  # Most recent time quote view link was opened
    accepted_at: Optional[datetime] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    
    temperature: Optional[QuoteTemperature] = Field(default=None)
    
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
    discount_requests: List["DiscountRequest"] = Relationship(back_populates="quote")
    # Explicitly specify created_by_id as the foreign key since we also have owner_id
    # SQLAlchemy needs explicit foreign_keys when multiple FKs point to same table
    # Use sa_relationship_kwargs to pass SQLAlchemy-specific parameters
    created_by: User = Relationship(sa_relationship_kwargs={"foreign_keys": "[Quote.created_by_id]"})
    email_sends: List["QuoteEmail"] = Relationship(back_populates="quote")
    order: Optional["Order"] = Relationship(back_populates="quote", sa_relationship_kwargs={"uselist": False})


class QuoteItem(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    quote_id: int = Field(foreign_key="quote.id")
    parent_quote_item_id: Optional[int] = Field(default=None, foreign_key="quoteitem.id")  # Optional extra under this parent line
    product_id: Optional[int] = Field(default=None, foreign_key="product.id")  # Reference to product
    description: str  # Can be from product or custom
    quantity: Decimal = Field(default=1, sa_column=Column(Numeric(10, 2)))
    unit_price: Decimal = Field(sa_column=Column(Numeric(10, 2)))  # Can be from product base_price or custom
    line_total: Decimal = Field(sa_column=Column(Numeric(10, 2)))  # quantity * unit_price (before discount)
    discount_amount: Decimal = Field(default=0, sa_column=Column(Numeric(10, 2)))  # Discount applied to this line item
    final_line_total: Decimal = Field(sa_column=Column(Numeric(10, 2)))  # line_total - discount_amount
    sort_order: int = Field(default=0)
    is_custom: bool = Field(default=False)  # True if not from product catalog
    line_type: Optional[QuoteItemLineType] = Field(default=None)  # DELIVERY or INSTALLATION; excluded from PRODUCT-scope discount
    
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
    view_token: Optional[str] = Field(default=None, unique=True, index=True)  # For public quote view URL
    open_count: int = Field(default=0)  # Number of times view link was opened

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


class SmsTemplate(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    description: Optional[str] = None
    body_template: str  # Jinja2 template for SMS body
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
    is_giveaway: bool = Field(default=False)  # True if this is a giveaway discount
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


class DiscountRequest(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    quote_id: int = Field(foreign_key="quote.id")
    requested_by_id: int = Field(foreign_key="user.id")
    discount_type: DiscountType
    discount_value: Decimal = Field(sa_column=Column(Numeric(10, 2)))
    scope: DiscountScope
    reason: Optional[str] = None
    status: DiscountRequestStatus = Field(default=DiscountRequestStatus.PENDING)
    approved_by_id: Optional[int] = Field(default=None, foreign_key="user.id")
    responded_at: Optional[datetime] = None
    rejection_reason: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    # Relationships
    quote: "Quote" = Relationship(back_populates="discount_requests")
    requested_by: User = Relationship(sa_relationship_kwargs={"foreign_keys": "[DiscountRequest.requested_by_id]"})
    approved_by: Optional[User] = Relationship(sa_relationship_kwargs={"foreign_keys": "[DiscountRequest.approved_by_id]"})


class Order(SQLModel, table=True):
    """Order created from an accepted quote. One-to-one with Quote."""
    __tablename__ = "customer_order"  # "order" is a reserved SQL keyword
    id: Optional[int] = Field(default=None, primary_key=True)
    quote_id: int = Field(unique=True, foreign_key="quote.id")
    customer_id: Optional[int] = Field(default=None, foreign_key="customer.id")
    order_number: str = Field(unique=True, index=True)  # e.g., "ORD-2025-001"
    subtotal: Decimal = Field(sa_column=Column(Numeric(10, 2)))
    discount_total: Decimal = Field(default=0, sa_column=Column(Numeric(10, 2)))
    total_amount: Decimal = Field(sa_column=Column(Numeric(10, 2)))
    deposit_amount: Decimal = Field(default=0, sa_column=Column(Numeric(10, 2)))
    balance_amount: Decimal = Field(default=0, sa_column=Column(Numeric(10, 2)))
    currency: str = Field(default="GBP")
    terms_and_conditions: Optional[str] = None
    notes: Optional[str] = None
    created_by_id: int = Field(foreign_key="user.id")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    deposit_paid: bool = Field(default=False)
    balance_paid: bool = Field(default=False)
    paid_in_full: bool = Field(default=False)
    installation_booked: bool = Field(default=False)
    installation_completed: bool = Field(default=False)
    invoice_number: Optional[str] = Field(default=None, unique=True, index=True)  # e.g. "INV-2025-001"
    xero_invoice_id: Optional[str] = Field(default=None)  # XERO invoice ID after push

    # Relationships
    quote: "Quote" = Relationship(back_populates="order")
    customer: Optional["Customer"] = Relationship(back_populates="orders")
    created_by: User = Relationship()
    items: List["OrderItem"] = Relationship(back_populates="order")
    access_sheet_requests: List["AccessSheetRequest"] = Relationship(back_populates="order")


class OrderItem(SQLModel, table=True):
    """Line item on an order; snapshot of quote line at acceptance."""
    id: Optional[int] = Field(default=None, primary_key=True)
    order_id: int = Field(foreign_key="customer_order.id")
    quote_item_id: Optional[int] = Field(default=None, foreign_key="quoteitem.id")
    product_id: Optional[int] = Field(default=None, foreign_key="product.id")
    description: str
    quantity: Decimal = Field(default=1, sa_column=Column(Numeric(10, 2)))
    unit_price: Decimal = Field(sa_column=Column(Numeric(10, 2)))
    line_total: Decimal = Field(sa_column=Column(Numeric(10, 2)))
    discount_amount: Decimal = Field(default=0, sa_column=Column(Numeric(10, 2)))
    final_line_total: Decimal = Field(sa_column=Column(Numeric(10, 2)))
    sort_order: int = Field(default=0)
    is_custom: bool = Field(default=False)

    # Relationships
    order: "Order" = Relationship(back_populates="items")
    quote_item: Optional["QuoteItem"] = Relationship()
    product: Optional["Product"] = Relationship()


class AccessSheetRequest(SQLModel, table=True):
    """Token-based access sheet form. One per order; customer fills via public link."""
    id: Optional[int] = Field(default=None, primary_key=True)
    order_id: int = Field(foreign_key="customer_order.id")
    access_token: str = Field(unique=True, index=True)
    completed_at: Optional[datetime] = None
    answers: Optional[dict] = Field(default=None, sa_column=Column(JSON))  # Form answers as JSON
    created_at: datetime = Field(default_factory=datetime.utcnow)
    sent_at: Optional[datetime] = None

    # Relationships
    order: "Order" = Relationship(back_populates="access_sheet_requests")


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
    QUOTE_NOT_OPENED = "QUOTE_NOT_OPENED"  # Sent but view link not opened in 48h
    QUOTE_OPENED_NO_REPLY = "QUOTE_OPENED_NO_REPLY"  # Opened but no reply, phone call
    MANUAL = "MANUAL"  # User-created follow-up (e.g. call back)


class SuggestedAction(str, Enum):
    FOLLOW_UP = "FOLLOW_UP"
    MARK_LOST = "MARK_LOST"
    RESEND_QUOTE = "RESEND_QUOTE"
    REVIEW_QUOTE = "REVIEW_QUOTE"
    CONTACT_CUSTOMER = "CONTACT_CUSTOMER"
    PHONE_CALL = "PHONE_CALL"


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


class ProductOptionalExtra(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    product_id: int = Field(foreign_key="product.id")
    optional_extra_id: int = Field(foreign_key="product.id")
    sort_order: int = Field(default=0)
    created_at: datetime = Field(default_factory=datetime.utcnow)
