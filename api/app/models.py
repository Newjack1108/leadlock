from sqlmodel import SQLModel, Field, Relationship, Column
from sqlalchemy.orm import relationship
from sqlalchemy import Boolean, Numeric, JSON, UniqueConstraint, ForeignKey, Integer, String
from typing import Optional, List
from datetime import datetime, date
from enum import Enum
from decimal import Decimal


class UserRole(str, Enum):
    DIRECTOR = "DIRECTOR"
    SALES_MANAGER = "SALES_MANAGER"
    CLOSER = "CLOSER"
    DEALER_ADMIN = "DEALER_ADMIN"
    DEALER_USER = "DEALER_USER"


class LeadStatus(str, Enum):
    NEW = "NEW"
    CONTACT_ATTEMPTED = "CONTACT_ATTEMPTED"
    ENGAGED = "ENGAGED"
    QUALIFIED = "QUALIFIED"
    QUOTED = "QUOTED"
    WON = "WON"
    LOST = "LOST"
    CLOSED = "CLOSED"


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
    CONFIGURATOR = "CONFIGURATOR"


class ConfiguratorFrontFace(str, Enum):
    TOP = "top"
    RIGHT = "right"
    BOTTOM = "bottom"
    LEFT = "left"


class ConfiguratorConnectionProfile(str, Enum):
    CORNER_LEFT = "corner_left"
    CORNER_RIGHT = "corner_right"


class LeadType(str, Enum):
    UNKNOWN = "UNKNOWN"
    STABLES = "STABLES"
    SHEDS = "SHEDS"
    CABINS = "CABINS"


class LeadSource(str, Enum):
    UNKNOWN = "UNKNOWN"
    FACEBOOK = "FACEBOOK"
    FACEBOOK_WHATSAPP = "Facebook/WhatsApp"
    INSTAGRAM = "INSTAGRAM"
    WEBSITE = "WEBSITE"  # Legacy - prefer CSGB_WEBSITE, CS_WEBSITE, BLC_WEBSITE for new leads
    CSGB_WEBSITE = "CSGB WEBSITE"
    CS_WEBSITE = "CS WEBSITE"
    BLC_WEBSITE = "BLC WEBSITE"
    MANUAL_ENTRY = "MANUAL_ENTRY"
    NINOX = "NINOX"
    SMS = "SMS"
    EMAIL = "EMAIL"
    PHONE = "PHONE"
    PAST_CUSTOMER = "Past Customer"
    REFERRAL = "REFERRAL"
    CONFIGURATOR = "CONFIGURATOR"
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
    dealer_id: Optional[int] = Field(default=None, foreign_key="dealer.id", index=True)
    dealer_commission_pct: Optional[int] = Field(default=None)
    is_active: bool = Field(default=True)
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


class Dealer(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(index=True, unique=True)
    company_name: Optional[str] = None
    contact_name: Optional[str] = None
    email: Optional[str] = Field(default=None, index=True)
    phone: Optional[str] = None
    address: Optional[str] = None
    vat_number: Optional[str] = None
    registration_number: Optional[str] = None
    website: Optional[str] = None
    logo_url: Optional[str] = None
    is_active: bool = Field(default=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


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
    sms_bot_paused_until: Optional[datetime] = None
    sms_bot_stopped: bool = Field(default=False)
    # Stops automated SMS/email from reminder-rule outreach worker only (not manual staff sends)
    automated_reminder_outreach_opt_out: bool = Field(default=False)
    # Marked when staff know email address is invalid and automated email outreach should be suppressed.
    wrong_email_address: bool = Field(default=False)
    # After a [BOT_HANDOVER] outbound, suppress auto-replies to inbound received before this UTC time (Twilio retries / clock skew).
    sms_bot_suppress_auto_reply_before_utc: Optional[datetime] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    messenger_psid: Optional[str] = Field(default=None, unique=True, index=True)  # Facebook Page-Scoped ID for Messenger
    source_system: Optional[str] = None  # e.g. "Ninox" for CSV imports from old system
    
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
    # Marked when staff know this lead email is invalid and automated email outreach should be suppressed.
    wrong_email_address: bool = Field(default=False)
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
    facebook_advert_profile_id: Optional[int] = Field(default=None, foreign_key="facebookadvertprofile.id")
    assigned_to_id: Optional[int] = Field(default=None, foreign_key="user.id")
    customer_id: Optional[int] = Field(default=None, foreign_key="customer.id")  # Link to Customer when qualified
    messenger_psid: Optional[str] = Field(default=None, index=True)  # Facebook Page-Scoped ID for Messenger
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    archived_at: Optional[datetime] = Field(default=None, index=True)

    # Relationships
    assigned_to_user: Optional[User] = Relationship(back_populates="assigned_leads")
    customer: Optional["Customer"] = Relationship(back_populates="leads")
    facebook_advert_profile: Optional["FacebookAdvertProfile"] = Relationship(back_populates="leads")
    quotes: List["Quote"] = Relationship(back_populates="lead")
    status_history: List["StatusHistory"] = Relationship(back_populates="lead")


class FacebookAdvertProfile(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    offer_type: Optional[str] = None
    image_url: Optional[str] = None
    is_active: bool = Field(default=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    leads: List["Lead"] = Relationship(back_populates="facebook_advert_profile")


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
    read_at: Optional[datetime] = None  # When RECEIVED message was read (null = unread)
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


class SalesDocument(SQLModel, table=True):
    """Reusable sales documents (price lists, spec sheets) for attaching to emails."""
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str  # Display name (e.g. "2024 Price List")
    filename: str  # Original/stored filename
    file_path: str  # Legacy local path or durable remote URL
    cloudinary_public_id: Optional[str] = Field(default=None, index=True)
    cloudinary_resource_type: Optional[str] = None  # raw/image for Cloudinary-backed docs
    content_type: Optional[str] = None  # application/pdf, etc.
    file_size: Optional[int] = None
    category: Optional[str] = None  # e.g. "Price List", "Spec Sheet"
    created_at: datetime = Field(default_factory=datetime.utcnow)
    created_by_id: Optional[int] = Field(default=None, foreign_key="user.id")


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
    FAILED = "FAILED"


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
    failure_reason: Optional[str] = None

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
    allow_trade_dealer_sale: bool = Field(default=False)  # True if visible/sellable in dealer portal
    image_url: Optional[str] = None  # Product image URL
    specifications: Optional[str] = None  # Technical specs (JSON or text)
    size: Optional[str] = None  # Display dimensions, e.g. "3m x 4m", "12ft x 16ft"
    height: Optional[str] = None  # Eave/ridge height, e.g. "2.4m"
    floor_plan_url: Optional[str] = None  # URL to floor plan image
    width: Optional[Decimal] = Field(default=None, sa_column=Column(Numeric(10, 2)))  # Numeric width (for calculations)
    length: Optional[Decimal] = Field(default=None, sa_column=Column(Numeric(10, 2)))  # Numeric length (for calculations)
    configurator_width: Optional[Decimal] = Field(default=None, sa_column=Column(Numeric(10, 2)))  # Footprint width used by configurator layout grid
    configurator_length: Optional[Decimal] = Field(default=None, sa_column=Column(Numeric(10, 2)))  # Footprint length used by configurator layout grid
    configurator_front_face: Optional[ConfiguratorFrontFace] = Field(default=None, sa_column=Column(String(16), nullable=True))  # Base face treated as the front before any layout rotation
    configurator_connection_profile: Optional[ConfiguratorConnectionProfile] = Field(default=None, sa_column=Column(String(32), nullable=True))  # Optional corner-box connection rule derived from the product's fixed front and handedness
    configurator_is_corner_box: bool = Field(default=False, sa_column=Column(Boolean, nullable=False, server_default="false"))  # Fixed-orientation corner SKU; disables layout rotation in the configurator
    configurator_is_starter_box: bool = Field(default=False, sa_column=Column(Boolean, nullable=False, server_default="false"))  # Eligible first box when starting a configurator layout
    allow_in_configurator: bool = Field(default=False)  # Extra-level opt-in for configurator selections
    configurator_per_box: bool = Field(
        default=False,
        sa_column=Column(Boolean, nullable=False, server_default="false"),
    )  # Configurator extra quantity tracks layout box count
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


class SmsBotMode(str, Enum):
    OFF = "OFF"
    AUTO = "AUTO"
    ON = "ON"


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
    footer_logo_url: Optional[str] = None  # Separate logo for PDF footer (optional; falls back to logo_url if not set)
    default_terms_and_conditions: Optional[str] = None  # Default terms and conditions for quotes
    email_disclaimer: Optional[str] = None  # Standard disclaimer appended to all outgoing emails (HTML)
    default_email_signature: Optional[str] = None  # Used when sending without a user_id (HTML); per-user signature overrides when user_id is set
    hourly_install_rate: Optional[Decimal] = Field(default=None, sa_column=Column(Numeric(10, 2)))  # Hourly rate for installation cost calculation
    installation_lead_time: Optional[InstallationLeadTime] = Field(default=None)  # Legacy fallback when per-type unset or quote type unknown
    installation_lead_time_stables: Optional[InstallationLeadTime] = Field(default=None)
    installation_lead_time_sheds: Optional[InstallationLeadTime] = Field(default=None)
    installation_lead_time_cabins: Optional[InstallationLeadTime] = Field(default=None)
    # Installation & travel (mileage, overnight, 2-man team)
    distance_before_overnight_miles: Optional[Decimal] = Field(default=None, sa_column=Column(Numeric(10, 2)))  # Stay away if distance > this
    cost_per_mile: Optional[Decimal] = Field(default=None, sa_column=Column(Numeric(10, 2)))  # Applied to return distance
    hotel_allowance_per_night: Optional[Decimal] = Field(default=None, sa_column=Column(Numeric(10, 2)))  # Per person; ×2 for 2-man team
    meal_allowance_per_day: Optional[Decimal] = Field(default=None, sa_column=Column(Numeric(10, 2)))  # Per person when staying away
    average_speed_mph: Optional[Decimal] = Field(default=None, sa_column=Column(Numeric(5, 2)))  # For travel time calculation
    install_quote_margin_pct: Optional[Decimal] = Field(default=30, sa_column=Column(Numeric(5, 2)))  # Margin % added to install quote cost (e.g. 30 = 30%); defaults to 30
    product_import_gross_margin_pct: Optional[Decimal] = Field(default=None, sa_column=Column(Numeric(5, 2)))  # e.g. 30 for 30%; applied when products pushed from production to set RRP
    # SMS bot settings (out-of-hours assistant)
    sms_bot_mode: SmsBotMode = Field(default=SmsBotMode.OFF)
    sms_bot_timezone: str = Field(default="Europe/London")
    sms_bot_business_hours_json: Optional[str] = None  # JSON string: {"mon":{"enabled":true,"start":"09:00","end":"17:00"}, ...}
    sms_bot_fallback_message: Optional[str] = None
    sms_bot_max_replies_per_thread: int = Field(default=3)
    sms_bot_pause_minutes_after_handover: int = Field(default=720)
    sms_bot_system_instructions: Optional[str] = None  # Extra system prompt for out-of-hours SMS bot (Responses API)
    # Bank details (shown on quote and invoice PDFs)
    bank_name: Optional[str] = None
    bank_account_name: Optional[str] = None  # Name on the account (payee for BACS)
    account_number: Optional[str] = None
    sort_code: Optional[str] = None
    require_engagement_proof: bool = Field(default=False)  # When True, customers need engagement (SMS/email/WhatsApp/call) before quoting
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


class DealerDiscountMode(str, Enum):
    TEMPLATE = "TEMPLATE"
    CUSTOM = "CUSTOM"


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
    lead_id: Optional[int] = Field(default=None, foreign_key="lead.id")  # Lead this quote was generated from
    quote_number: str = Field(unique=True, index=True)  # e.g., "QT-2024-001"
    version: int = Field(default=1)  # For quote revisions
    status: QuoteStatus = Field(default=QuoteStatus.DRAFT)
    subtotal: Decimal = Field(sa_column=Column(Numeric(10, 2)))  # Sum of all line items (before discounts)
    discount_total: Decimal = Field(default=0, sa_column=Column(Numeric(10, 2)))  # Total of all discounts applied
    total_amount: Decimal = Field(sa_column=Column(Numeric(10, 2)))  # subtotal - discount_total (final amount)
    deposit_amount: Decimal = Field(default=0, sa_column=Column(Numeric(10, 2)))  # Deposit amount inc VAT (default 50% of total inc VAT)
    balance_amount: Decimal = Field(default=0, sa_column=Column(Numeric(10, 2)))  # Balance amount inc VAT (total inc VAT - deposit)
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
    archived_at: Optional[datetime] = Field(default=None, index=True)

    temperature: Optional[QuoteTemperature] = Field(default=None)
    include_spec_sheets: bool = Field(default=True)  # Include product spec sheets when generating quote PDF
    include_available_optional_extras: bool = Field(default=False)  # Show extras not on quote in customer view/PDF
    include_delivery_installation_contact_note: bool = Field(default=False)  # Footer note re delivery/install contact

    # Opportunity management fields
    opportunity_stage: Optional["OpportunityStage"] = Field(default=None)
    close_probability: Optional[Decimal] = Field(default=None, sa_column=Column(Numeric(5, 2)))  # 0-100 percentage
    expected_close_date: Optional[datetime] = None
    next_action: Optional[str] = None
    next_action_due_date: Optional[datetime] = None
    loss_reason: Optional[str] = None
    loss_category: Optional["LossCategory"] = None
    owner_id: Optional[int] = Field(default=None, foreign_key="user.id")  # Opportunity owner (can differ from created_by)
    dealer_id: Optional[int] = Field(default=None, foreign_key="dealer.id", index=True)
    dealer_customer_name: Optional[str] = None
    dealer_customer_email: Optional[str] = None
    dealer_customer_phone: Optional[str] = None
    dealer_customer_address: Optional[str] = None
    dealer_customer_postcode: Optional[str] = None
    revision_hash: Optional[str] = Field(default=None, index=True)
    
    # Relationships
    customer: Optional["Customer"] = Relationship(back_populates="quotes")
    lead: Optional["Lead"] = Relationship(back_populates="quotes")
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
    include_in_building_discount: bool = Field(default=True)  # False = exclude line from PRODUCT-scope ("building items only") discounts
    installation_hours: Optional[Decimal] = Field(default=None, sa_column=Column(Numeric(10, 2)))  # Per-unit install hours for custom lines
    
    # Relationships
    quote: Quote = Relationship(back_populates="items")
    product: Optional[Product] = Relationship(back_populates="quote_items")
    discounts: List["QuoteDiscount"] = Relationship(back_populates="quote_item")


class QuoteConfiguration(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    quote_id: int = Field(foreign_key="quote.id", index=True, unique=True)
    version: int = Field(default=1)
    configuration_json: dict = Field(default_factory=dict, sa_column=Column(JSON))
    created_by_id: int = Field(foreign_key="user.id")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    quote: Quote = Relationship(sa_relationship_kwargs={"uselist": False})
    created_by: User = Relationship()


class ConfiguratorInviteStatus(str, Enum):
    PENDING_DETAILS = "PENDING_DETAILS"
    ACTIVE = "ACTIVE"
    SUBMITTED = "SUBMITTED"
    EXPIRED = "EXPIRED"


class ConfiguratorInvite(SQLModel, table=True):
    """Token-based public configurator session; links to draft quote after registration."""
    id: Optional[int] = Field(default=None, primary_key=True)
    access_token: str = Field(unique=True, index=True)
    status: ConfiguratorInviteStatus = Field(default=ConfiguratorInviteStatus.PENDING_DETAILS)
    quote_id: Optional[int] = Field(default=None, foreign_key="quote.id", index=True)
    lead_id: Optional[int] = Field(default=None, foreign_key="lead.id", index=True)
    customer_id: Optional[int] = Field(default=None, foreign_key="customer.id", index=True)
    created_by_id: Optional[int] = Field(default=None, foreign_key="user.id")
    assigned_to_id: Optional[int] = Field(default=None, foreign_key="user.id")
    campaign_slug: Optional[str] = Field(default=None, index=True)
    submitted_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    quote: Optional[Quote] = Relationship()
    lead: Optional["Lead"] = Relationship()
    customer: Optional[Customer] = Relationship()
    created_by: Optional[User] = Relationship(
        sa_relationship_kwargs={"foreign_keys": "[ConfiguratorInvite.created_by_id]"}
    )


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
    include_available_extras: bool = Field(default=False)  # Show optional extras section in view/PDF

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
    sales_document_links: List["QuoteTemplateSalesDocument"] = Relationship(
        back_populates="quote_template"
    )


class QuoteTemplateSalesDocument(SQLModel, table=True):
    """Links quote email templates to library sales documents (attached when sending quote email)."""

    __tablename__ = "quote_template_sales_document"
    __table_args__ = (
        UniqueConstraint(
            "quote_template_id",
            "sales_document_id",
            name="uq_quote_template_sales_document",
        ),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    quote_template_id: int = Field(
        sa_column=Column(
            Integer,
            ForeignKey("quotetemplate.id", ondelete="CASCADE"),
            nullable=False,
        )
    )
    sales_document_id: int = Field(
        sa_column=Column(
            Integer,
            ForeignKey("salesdocument.id", ondelete="CASCADE"),
            nullable=False,
        )
    )
    sort_order: int = Field(default=0)

    quote_template: "QuoteTemplate" = Relationship(back_populates="sales_document_links")
    sales_document: "SalesDocument" = Relationship()


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
    max_uses: Optional[int] = None  # None = unlimited; enforced on quote accept (redemptions)
    expires_at: Optional[datetime] = None  # None = never; UTC
    created_by_id: int = Field(foreign_key="user.id")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    
    # Relationships
    created_by: User = Relationship()
    quote_discounts: List["QuoteDiscount"] = Relationship(back_populates="template")
    redemptions: List["DiscountTemplateRedemption"] = Relationship(back_populates="template")


class DiscountTemplateRedemption(SQLModel, table=True):
    """One row per (template, quote) when a quote is accepted; counts toward max_uses."""
    __table_args__ = (
        UniqueConstraint("template_id", "quote_id", name="uq_discount_redemption_template_quote"),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    template_id: int = Field(
        sa_column=Column(
            Integer,
            ForeignKey("discounttemplate.id", ondelete="CASCADE"),
            nullable=False,
        )
    )
    quote_id: int = Field(
        sa_column=Column(
            Integer,
            ForeignKey("quote.id", ondelete="CASCADE"),
            nullable=False,
        )
    )
    created_at: datetime = Field(default_factory=datetime.utcnow)

    template: "DiscountTemplate" = Relationship(back_populates="redemptions")


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
    deposit_amount: Decimal = Field(default=0, sa_column=Column(Numeric(10, 2)))  # inc VAT
    balance_amount: Decimal = Field(default=0, sa_column=Column(Numeric(10, 2)))  # inc VAT
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
    # One-way drive time (hours); round-trip sent to production webhook is 2× this when set
    travel_time_hours_one_way: Optional[Decimal] = Field(default=None, sa_column=Column(Numeric(10, 4)))

    # Relationships
    quote: "Quote" = Relationship(back_populates="order")
    customer: Optional["Customer"] = Relationship(back_populates="orders")
    created_by: User = Relationship()
    items: List["OrderItem"] = Relationship(back_populates="order")
    access_sheet_requests: List["AccessSheetRequest"] = Relationship(back_populates="order")


class OrderAuditEvent(SQLModel, table=True):
    """Durable customer-facing audit trail for significant order actions."""

    id: Optional[int] = Field(default=None, primary_key=True)
    customer_id: int = Field(index=True)
    order_id: Optional[int] = Field(default=None, index=True)
    event_type: str = Field(index=True)
    title: str
    description: Optional[str] = None
    details: Optional[dict] = Field(default=None, sa_column=Column("metadata", JSON))
    created_by_id: Optional[int] = Field(default=None, foreign_key="user.id", index=True)
    created_at: datetime = Field(default_factory=datetime.utcnow, index=True)


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


class CustomerFileKind(str, Enum):
    PLAN = "PLAN"
    PHOTO = "PHOTO"
    OTHER = "OTHER"


class CustomerFile(SQLModel, table=True):
    """File anchored to a customer, optionally scoped to a quote and/or order.

    Storage is Cloudinary (folder ``customers/{customer_id}``); this row holds
    the metadata and the ``secure_url`` used to fetch/download in the UI.
    Visibility rules:
      - Customer profile: ``customer_id`` matches AND both ``quote_id`` and
        ``order_id`` are NULL.
      - Quote page: ``quote_id`` matches.
      - Order page: ``order_id`` matches.
    On quote acceptance, ``order_id`` is set on the existing row so the same
    file appears on both quote and order without duplication.
    """
    id: Optional[int] = Field(default=None, primary_key=True)
    customer_id: int = Field(foreign_key="customer.id", index=True)
    quote_id: Optional[int] = Field(default=None, foreign_key="quote.id", index=True)
    order_id: Optional[int] = Field(default=None, foreign_key="customer_order.id", index=True)
    kind: CustomerFileKind = Field(default=CustomerFileKind.PLAN)
    original_filename: str
    content_type: str
    size_bytes: int
    cloudinary_public_id: str = Field(index=True)
    cloudinary_resource_type: str  # "image" for JPG/PNG, "raw" or "image" for PDF
    secure_url: str
    uploaded_by_id: int = Field(foreign_key="user.id")
    created_at: datetime = Field(default_factory=datetime.utcnow)


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
    USER_TASK = "USER_TASK"  # User task with due date; may assign to self or others


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
    due_date: Optional[date] = Field(default=None)  # USER_TASK / optional MANUAL: drives overdue
    created_by_id: Optional[int] = Field(default=None, foreign_key="user.id")  # Who created USER_TASK
    created_at: datetime = Field(default_factory=datetime.utcnow)
    dismissed_at: Optional[datetime] = None
    acted_upon_at: Optional[datetime] = None
    
    # Relationships (two FKs to User — must specify foreign_keys each)
    lead: Optional["Lead"] = Relationship()
    quote: Optional["Quote"] = Relationship()
    customer: Optional["Customer"] = Relationship()
    assigned_to: User = Relationship(
        sa_relationship_kwargs={"foreign_keys": lambda: [Reminder.assigned_to_id]},
    )
    created_by: Optional["User"] = Relationship(
        sa_relationship_kwargs={"foreign_keys": lambda: [Reminder.created_by_id]},
    )


class ReminderCleanupTargetKind(str, Enum):
    LEAD = "LEAD"
    QUOTE = "QUOTE"


class AutomatedReminderCleanupSuppression(SQLModel, table=True):
    __table_args__ = (
        UniqueConstraint(
            "target_kind",
            "target_id",
            "reminder_type",
            name="uq_auto_reminder_cleanup_target_type",
        ),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    target_kind: ReminderCleanupTargetKind = Field(index=True)
    target_id: int = Field(index=True)
    reminder_type: ReminderType = Field(index=True)
    lead_id: Optional[int] = Field(default=None, foreign_key="lead.id")
    quote_id: Optional[int] = Field(default=None, foreign_key="quote.id")
    customer_id: Optional[int] = Field(default=None, foreign_key="customer.id")
    last_auto_outreach_status: Optional[str] = None
    last_auto_outreach_channel: Optional[str] = None
    last_auto_outreach_sent_at: Optional[datetime] = None
    cleaned_up_by_id: Optional[int] = Field(default=None, foreign_key="user.id")
    cleaned_up_at: datetime = Field(default_factory=datetime.utcnow)


class CustomerOutreachChannel(str, Enum):
    SMS = "SMS"
    EMAIL = "EMAIL"


class ReminderRule(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    rule_name: str = Field(unique=True, index=True)  # "NEW_LEAD_STALE", "QUOTE_SENT_STALE"
    entity_type: str  # "LEAD", "QUOTE"
    status: Optional[str] = None  # LeadStatus or QuoteStatus value as string
    threshold_minutes: int
    check_type: str  # "LAST_ACTIVITY", "STATUS_DURATION", "SENT_DATE", "VALID_UNTIL"
    is_active: bool = Field(default=True)
    priority: ReminderPriority = Field(default=ReminderPriority.MEDIUM)
    suggested_action: SuggestedAction
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    # Optional automatic customer message when rule matches stale detection (background worker)
    customer_outreach_channel: Optional[str] = Field(default=None)  # CustomerOutreachChannel.value or None
    customer_outreach_sms_template_id: Optional[int] = Field(default=None, foreign_key="smstemplate.id")
    customer_outreach_email_template_id: Optional[int] = Field(default=None, foreign_key="emailtemplate.id")
    customer_outreach_cooldown_days: int = Field(default=14)
    # Set when outreach is enabled so newly-enabled rules only apply forward (no backfill on old stale entities).
    outreach_enabled_from_utc: Optional[datetime] = None
    # LEAD rules only: send outreach once when a lead is created matching rule.status (in addition to stale worker).
    customer_outreach_on_lead_create: bool = Field(default=False)


class DeletedReminderRuleName(SQLModel, table=True):
    """Records reminder rule_names the user explicitly deleted, so the startup
    backfill in database.py does not re-create them on the next restart."""

    rule_name: str = Field(primary_key=True, index=True)
    deleted_at: datetime = Field(default_factory=datetime.utcnow)


class CustomerOutreachSend(SQLModel, table=True):
    """Log of automated customer SMS/email sends for cooldown and audit."""
    id: Optional[int] = Field(default=None, primary_key=True)
    reminder_rule_id: int = Field(foreign_key="reminderrule.id")
    customer_id: int = Field(foreign_key="customer.id")
    channel: str  # CustomerOutreachChannel.value
    lead_id: Optional[int] = Field(default=None, foreign_key="lead.id")
    quote_id: Optional[int] = Field(default=None, foreign_key="quote.id")
    external_message_id: Optional[str] = Field(default=None)  # Twilio SID or email Message-ID
    status: str = Field(default="SENT")  # SENT or FAILED
    failure_reason: Optional[str] = None
    sent_at: datetime = Field(default_factory=datetime.utcnow)


class WeeklyPlanItemStatus(str, Enum):
    PENDING_REVIEW = "PENDING_REVIEW"
    AUTO_SENT = "AUTO_SENT"
    REJECTED = "REJECTED"
    COMPLETED = "COMPLETED"
    AUTO_FAILED = "AUTO_FAILED"


class WeeklyPlanScope(str, Enum):
    FULL_PIPELINE = "FULL_PIPELINE"


class WeeklyPlanTemplate(SQLModel, table=True):
    __table_args__ = (
        UniqueConstraint("suggested_action", "channel", name="uq_weekly_plan_template_action_channel"),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    description: Optional[str] = None
    suggested_action: SuggestedAction
    channel: str = Field(index=True)  # EMAIL|SMS|CALL
    subject_template: Optional[str] = None  # Used for EMAIL templates
    body_template: str
    is_active: bool = Field(default=True, index=True)
    created_by_id: int = Field(foreign_key="user.id")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    created_by: Optional["User"] = Relationship()


class WeeklyPlanRun(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    week_start: date = Field(index=True)
    generated_at: datetime = Field(default_factory=datetime.utcnow, index=True)
    scope: WeeklyPlanScope = Field(default=WeeklyPlanScope.FULL_PIPELINE)
    model_version: str = Field(default="deterministic-v1")
    generated_by_id: Optional[int] = Field(default=None, foreign_key="user.id")
    total_items: int = Field(default=0)
    auto_eligible_items: int = Field(default=0)
    auto_sent_items: int = Field(default=0)

    generated_by: Optional["User"] = Relationship()


class WeeklyPlanItem(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    plan_run_id: int = Field(foreign_key="weeklyplanrun.id", index=True)
    lead_id: Optional[int] = Field(default=None, foreign_key="lead.id")
    quote_id: Optional[int] = Field(default=None, foreign_key="quote.id")
    customer_id: Optional[int] = Field(default=None, foreign_key="customer.id")
    assigned_to_id: Optional[int] = Field(default=None, foreign_key="user.id", index=True)
    priority_score: Decimal = Field(default=0, sa_column=Column(Numeric(6, 2)))
    confidence: Decimal = Field(default=0, sa_column=Column(Numeric(5, 2)))
    order_likelihood_score: Decimal = Field(default=0, sa_column=Column(Numeric(6, 2)))
    order_likelihood_confidence: Decimal = Field(default=0, sa_column=Column(Numeric(5, 2)))
    order_likelihood_reasons: List[str] = Field(default_factory=list, sa_column=Column(JSON))
    likelihood_explanation: Optional[str] = None
    recommended_next_steps: List[str] = Field(default_factory=list, sa_column=Column(JSON))
    reason_codes: List[str] = Field(default_factory=list, sa_column=Column(JSON))
    recommended_action: SuggestedAction
    channel: Optional[str] = None  # SMS|EMAIL|CALL|REQUOTE
    status: WeeklyPlanItemStatus = Field(default=WeeklyPlanItemStatus.PENDING_REVIEW, index=True)
    auto_eligible: bool = Field(default=False)
    suggested_message: Optional[str] = None
    due_date: Optional[date] = None
    executed_at: Optional[datetime] = None
    execution_error: Optional[str] = None
    outcome_result: Optional[str] = None
    response_received: bool = Field(default=False)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    plan_run: Optional["WeeklyPlanRun"] = Relationship()
    lead: Optional["Lead"] = Relationship()
    quote: Optional["Quote"] = Relationship()
    customer: Optional["Customer"] = Relationship()
    assigned_to: Optional["User"] = Relationship()


class ProductOptionalExtra(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    product_id: int = Field(foreign_key="product.id")
    optional_extra_id: int = Field(foreign_key="product.id")
    sort_order: int = Field(default=0)
    created_at: datetime = Field(default_factory=datetime.utcnow)


class DealerProductAccess(SQLModel, table=True):
    __table_args__ = (
        UniqueConstraint("dealer_id", "product_id", name="uq_dealer_product_access"),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    dealer_id: int = Field(foreign_key="dealer.id")
    product_id: int = Field(foreign_key="product.id")
    created_at: datetime = Field(default_factory=datetime.utcnow)


class DealerAllowedDiscount(SQLModel, table=True):
    __table_args__ = (
        UniqueConstraint(
            "dealer_id",
            "discount_template_id",
            name="uq_dealer_allowed_discount_template",
        ),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    dealer_id: int = Field(foreign_key="dealer.id")
    discount_template_id: int = Field(foreign_key="discounttemplate.id")
    created_at: datetime = Field(default_factory=datetime.utcnow)


class DealerDiscountPolicy(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    dealer_id: int = Field(foreign_key="dealer.id", unique=True, index=True)
    mode: DealerDiscountMode = Field(default=DealerDiscountMode.TEMPLATE)
    allow_fixed_amount: bool = Field(default=False)
    allow_percentage: bool = Field(default=False)
    max_discount_percentage: Optional[Decimal] = Field(
        default=None, sa_column=Column(Numeric(10, 2))
    )
    max_discount_amount: Optional[Decimal] = Field(
        default=None, sa_column=Column(Numeric(10, 2))
    )
    updated_at: datetime = Field(default_factory=datetime.utcnow)
