from pydantic import BaseModel, EmailStr, field_validator
from typing import Optional, List
from datetime import datetime, date
from decimal import Decimal
from enum import Enum
from app.models import (
    LeadStatus, ActivityType, Timeframe, UserRole, ProductCategory,
    QuoteStatus, QuoteTemperature, DiscountType, DiscountScope, DiscountRequestStatus,
    LeadType, LeadSource, EmailDirection, ReminderPriority, ReminderType,
    SuggestedAction, OpportunityStage, LossCategory, InstallationLeadTime,
    SmsDirection, ScheduledSmsStatus, MessengerDirection, QuoteItemLineType,
)


class Token(BaseModel):
    access_token: str
    token_type: str


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class BootstrapCreate(BaseModel):
    """Create first director when no users exist. No auth required."""
    email: EmailStr
    full_name: str
    password: str


class UserResponse(BaseModel):
    id: int
    email: str
    full_name: str
    role: UserRole


class UserCreate(BaseModel):
    email: EmailStr
    full_name: str
    password: str
    role: UserRole


class UserUpdate(BaseModel):
    full_name: Optional[str] = None
    role: Optional[UserRole] = None
    password: Optional[str] = None


class UserListResponse(BaseModel):
    id: int
    email: str
    full_name: str
    role: UserRole
    is_active: bool
    created_at: datetime


class UserEmailSettingsUpdate(BaseModel):
    smtp_host: Optional[str] = None
    smtp_port: Optional[int] = None
    smtp_user: Optional[str] = None
    smtp_password: Optional[str] = None
    smtp_use_tls: Optional[bool] = None
    smtp_from_email: Optional[str] = None
    smtp_from_name: Optional[str] = None
    imap_host: Optional[str] = None
    imap_port: Optional[int] = None
    imap_user: Optional[str] = None
    imap_password: Optional[str] = None
    imap_use_ssl: Optional[bool] = None
    email_signature: Optional[str] = None
    email_test_mode: Optional[bool] = None


class UserEmailSettingsResponse(BaseModel):
    smtp_host: Optional[str] = None
    smtp_port: Optional[int] = None
    smtp_user: Optional[str] = None
    smtp_use_tls: bool = True
    smtp_from_email: Optional[str] = None
    smtp_from_name: Optional[str] = None
    imap_host: Optional[str] = None
    imap_port: Optional[int] = None
    imap_user: Optional[str] = None
    imap_use_ssl: bool = True
    email_signature: Optional[str] = None
    email_test_mode: bool = False
    # Note: Passwords are excluded from response for security


class CustomerCreate(BaseModel):
    name: str
    email: Optional[str] = None
    phone: Optional[str] = None
    address_line1: Optional[str] = None
    address_line2: Optional[str] = None
    city: Optional[str] = None
    county: Optional[str] = None
    postcode: Optional[str] = None
    country: Optional[str] = "United Kingdom"


class CustomerUpdate(BaseModel):
    name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    address_line1: Optional[str] = None
    address_line2: Optional[str] = None
    city: Optional[str] = None
    county: Optional[str] = None
    postcode: Optional[str] = None
    country: Optional[str] = None


class CustomerResponse(BaseModel):
    id: int
    customer_number: str
    name: str
    email: Optional[str]
    phone: Optional[str]
    address_line1: Optional[str]
    address_line2: Optional[str]
    city: Optional[str]
    county: Optional[str]
    postcode: Optional[str]
    country: Optional[str]
    customer_since: datetime
    created_at: datetime
    updated_at: datetime
    messenger_psid: Optional[str] = None


class WebsiteVisitResponse(BaseModel):
    site: str
    visited_at: datetime


class WebsiteVisitsListResponse(BaseModel):
    visits: List[WebsiteVisitResponse]


class EmailCreate(BaseModel):
    customer_id: int
    to_email: str
    cc: Optional[str] = None
    bcc: Optional[str] = None
    subject: str
    body_html: Optional[str] = None
    body_text: Optional[str] = None
    template_id: Optional[int] = None  # EmailTemplate ID, None to use provided subject/body


class EmailResponse(BaseModel):
    id: int
    customer_id: int
    message_id: Optional[str]
    in_reply_to: Optional[str]
    thread_id: Optional[str]
    direction: EmailDirection
    from_email: str
    to_email: str
    cc: Optional[str]
    bcc: Optional[str]
    subject: str
    body_html: Optional[str]
    body_text: Optional[str]
    attachments: Optional[str]
    sent_at: Optional[datetime]
    received_at: Optional[datetime]
    created_by_id: Optional[int]
    created_at: datetime
    created_by_name: Optional[str] = None


class EmailReplyRequest(BaseModel):
    body_html: Optional[str] = None
    body_text: Optional[str] = None
    cc: Optional[str] = None
    bcc: Optional[str] = None


class SmsCreate(BaseModel):
    customer_id: int
    to_phone: Optional[str] = None
    body: str
    lead_id: Optional[int] = None


class SmsResponse(BaseModel):
    id: int
    customer_id: int
    lead_id: Optional[int] = None
    direction: SmsDirection
    from_phone: str
    to_phone: str
    body: str
    twilio_sid: Optional[str] = None
    sent_at: Optional[datetime] = None
    received_at: Optional[datetime] = None
    read_at: Optional[datetime] = None
    created_by_id: Optional[int] = None
    created_at: datetime
    created_by_name: Optional[str] = None


class SmsScheduledCreate(BaseModel):
    customer_id: int
    to_phone: str
    body: str
    scheduled_at: datetime


class SmsScheduledResponse(BaseModel):
    id: int
    customer_id: int
    to_phone: str
    body: str
    scheduled_at: datetime
    status: ScheduledSmsStatus
    created_by_id: int
    created_at: datetime
    sent_at: Optional[datetime] = None
    twilio_sid: Optional[str] = None


class SmsScheduledUpdate(BaseModel):
    scheduled_at: Optional[datetime] = None
    status: Optional[ScheduledSmsStatus] = None


class SmsTemplateCreate(BaseModel):
    name: str
    description: Optional[str] = None
    body_template: str
    is_default: Optional[bool] = False


class SmsTemplateUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    body_template: Optional[str] = None
    is_default: Optional[bool] = None


class SmsTemplateResponse(BaseModel):
    id: int
    name: str
    description: Optional[str] = None
    body_template: str
    is_default: bool
    created_by_id: int
    created_at: datetime
    updated_at: datetime
    created_by_name: Optional[str] = None


class SmsTemplatePreviewRequest(BaseModel):
    customer_id: Optional[int] = None


class SmsTemplatePreviewResponse(BaseModel):
    body: str


class EmailTemplateCreate(BaseModel):
    name: str
    description: Optional[str] = None
    subject_template: str
    body_template: str
    is_default: Optional[bool] = False


class EmailTemplateUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    subject_template: Optional[str] = None
    body_template: Optional[str] = None
    is_default: Optional[bool] = None


class EmailTemplateResponse(BaseModel):
    id: int
    name: str
    description: Optional[str]
    subject_template: str
    body_template: str
    is_default: bool
    created_by_id: int
    created_at: datetime
    updated_at: datetime
    created_by_name: Optional[str] = None


class EmailTemplatePreviewRequest(BaseModel):
    customer_id: Optional[int] = None  # If provided, use real customer data, otherwise use sample


class EmailTemplatePreviewResponse(BaseModel):
    subject: str
    body_html: str


class QuoteEmailSendRequest(BaseModel):
    template_id: Optional[int] = None  # QuoteTemplate ID, None for default
    to_email: str
    cc: Optional[str] = None
    bcc: Optional[str] = None
    custom_message: Optional[str] = None  # Optional message appended to template


class QuoteEmailSendResponse(BaseModel):
    email_id: int
    quote_email_id: int
    message: str
    view_url: Optional[str] = None  # For testing: open/copy link when in test mode
    test_mode: Optional[bool] = None  # True when email was not sent via SMTP


class QuoteViewLinkResponse(BaseModel):
    view_url: Optional[str] = None  # Latest customer view link for this quote, or null


class OpportunityWonRequest(BaseModel):
    confirmed_value: Optional[Decimal] = None  # Optional confirmation of final value


class OpportunityLostRequest(BaseModel):
    loss_reason: str
    loss_category: "LossCategory"


class OpportunityCloseRequest(BaseModel):
    reason: Optional[str] = None  # e.g. "Another quote won"


class LeadCreate(BaseModel):
    name: str
    email: Optional[str] = None
    phone: Optional[str] = None
    postcode: Optional[str] = None
    description: Optional[str] = None
    lead_type: Optional[LeadType] = None
    lead_source: Optional[LeadSource] = None


class LeadUpdate(BaseModel):
    name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    postcode: Optional[str] = None
    description: Optional[str] = None
    timeframe: Optional[Timeframe] = None
    scope_notes: Optional[str] = None
    product_interest: Optional[str] = None
    lead_type: Optional[LeadType] = None
    lead_source: Optional[LeadSource] = None
    assigned_to_id: Optional[int] = None


class LeadResponse(BaseModel):
    id: int
    name: str
    email: Optional[str]
    phone: Optional[str]
    postcode: Optional[str]
    description: Optional[str]
    status: LeadStatus
    timeframe: Timeframe
    scope_notes: Optional[str]
    product_interest: Optional[str]
    lead_type: LeadType
    lead_source: LeadSource
    assigned_to_id: Optional[int]
    customer_id: Optional[int] = None
    created_at: datetime
    updated_at: datetime
    sla_badge: Optional[str] = None
    quote_locked: bool = False
    quote_lock_reason: Optional[dict] = None
    customer: Optional[CustomerResponse] = None


class StatusTransitionRequest(BaseModel):
    new_status: LeadStatus
    override_reason: Optional[str] = None


class ActivityCreate(BaseModel):
    activity_type: ActivityType
    notes: Optional[str] = None


class ActivityResponse(BaseModel):
    id: int
    customer_id: Optional[int]
    activity_type: ActivityType
    notes: Optional[str]
    created_by_id: int
    created_at: datetime
    created_by_name: Optional[str] = None


class StatusHistoryResponse(BaseModel):
    id: int
    lead_id: int
    old_status: Optional[LeadStatus]
    new_status: LeadStatus
    changed_by_id: int
    override_reason: Optional[str]
    created_at: datetime
    changed_by_name: Optional[str] = None


class LeadSourceCount(BaseModel):
    source: str
    count: int


class LeadLocationItem(BaseModel):
    """Geocoded lead location for map pins."""
    lat: float
    lng: float
    postcode: str
    count: int


class DashboardStats(BaseModel):
    total_leads: int
    new_count: int
    engaged_count: int
    qualified_count: int
    quoted_count: int
    quotes_sent_count: int
    leads_with_sent_quotes_count: int
    won_count: int
    lost_count: int
    engaged_percentage: float
    qualified_percentage: float
    leads_by_source: List[LeadSourceCount] = []


class UnreadSmsMessageItem(BaseModel):
    """Single unread SMS for dashboard list."""
    id: int
    customer_id: int
    customer_name: str
    body: str  # snippet, full or truncated
    received_at: Optional[datetime] = None
    from_phone: str


class UnreadSmsSummary(BaseModel):
    count: int
    messages: List[UnreadSmsMessageItem] = []


class MessengerCreate(BaseModel):
    customer_id: int
    to_psid: Optional[str] = None  # If omitted, use customer's messenger_psid
    body: str


class MessengerResponse(BaseModel):
    id: int
    customer_id: int
    lead_id: Optional[int] = None
    direction: MessengerDirection
    from_psid: str
    to_psid: Optional[str] = None
    body: str
    facebook_mid: Optional[str] = None
    sent_at: Optional[datetime] = None
    received_at: Optional[datetime] = None
    read_at: Optional[datetime] = None
    created_by_id: Optional[int] = None
    created_at: datetime
    created_by_name: Optional[str] = None


class UnreadMessengerMessageItem(BaseModel):
    id: int
    customer_id: int
    customer_name: str
    body: str
    received_at: Optional[datetime] = None
    from_psid: str


class UnreadMessengerSummary(BaseModel):
    count: int
    messages: List[UnreadMessengerMessageItem] = []


class UnreadByCustomerItem(BaseModel):
    """Per-customer unread message count (SMS + Messenger)."""
    customer_id: int
    unread_count: int


PRODUCT_UNIT_VALUES = ("Per Box", "Unit", "Set")


class ProductCreate(BaseModel):
    name: str
    description: Optional[str] = None
    category: ProductCategory
    subcategory: Optional[str] = None
    is_extra: bool = False
    base_price: Decimal
    unit: str = "Unit"
    sku: Optional[str] = None
    image_url: Optional[str] = None
    specifications: Optional[str] = None
    size: Optional[str] = None
    height: Optional[str] = None
    floor_plan_url: Optional[str] = None
    width: Optional[Decimal] = None
    length: Optional[Decimal] = None
    installation_hours: Optional[Decimal] = None
    boxes_per_product: Optional[int] = None  # Number of boxes per product (optional; used in installation calculation)
    optional_extras: Optional[List[int]] = None  # List of product IDs that are optional extras

    @field_validator("unit")
    @classmethod
    def unit_must_be_allowed(cls, v: str) -> str:
        if v not in PRODUCT_UNIT_VALUES:
            raise ValueError(f'unit must be one of: {", ".join(PRODUCT_UNIT_VALUES)}')
        return v


class ProductUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    category: Optional[ProductCategory] = None
    subcategory: Optional[str] = None
    is_extra: Optional[bool] = None
    base_price: Optional[Decimal] = None
    unit: Optional[str] = None
    sku: Optional[str] = None
    is_active: Optional[bool] = None
    image_url: Optional[str] = None
    specifications: Optional[str] = None
    size: Optional[str] = None
    height: Optional[str] = None
    floor_plan_url: Optional[str] = None
    width: Optional[Decimal] = None
    length: Optional[Decimal] = None
    installation_hours: Optional[Decimal] = None
    boxes_per_product: Optional[int] = None
    optional_extras: Optional[List[int]] = None  # List of product IDs that are optional extras

    @field_validator("unit")
    @classmethod
    def unit_must_be_allowed(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        if v not in PRODUCT_UNIT_VALUES:
            raise ValueError(f'unit must be one of: {", ".join(PRODUCT_UNIT_VALUES)}')
        return v


class ProductResponse(BaseModel):
    id: int
    name: str
    description: Optional[str]
    category: ProductCategory
    subcategory: Optional[str]
    is_extra: bool
    base_price: Decimal
    unit: str
    sku: Optional[str]
    is_active: bool
    image_url: Optional[str]
    specifications: Optional[str]
    size: Optional[str] = None
    height: Optional[str] = None
    floor_plan_url: Optional[str] = None
    width: Optional[Decimal] = None
    length: Optional[Decimal] = None
    installation_hours: Optional[Decimal] = None
    boxes_per_product: Optional[int] = None
    optional_extras: Optional[List["ProductResponse"]] = None  # Nested optional extras
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True
        json_encoders = {
            Decimal: str
        }


class ProductImportPayload(BaseModel):
    """Payload for product import from production app."""

    product_id: Optional[int] = None  # Production app's product ID for sync
    name: str
    description: Optional[str] = None
    price_ex_vat: Decimal
    install_hours: Decimal
    number_of_boxes: Decimal  # Accepted as number; validated and stored as int

    @field_validator("price_ex_vat")
    @classmethod
    def price_non_negative(cls, v: Decimal) -> Decimal:
        if v < 0:
            raise ValueError("price_ex_vat must be >= 0")
        return v

    @field_validator("install_hours")
    @classmethod
    def install_hours_non_negative(cls, v: Decimal) -> Decimal:
        if v < 0:
            raise ValueError("install_hours must be >= 0")
        return v

    @field_validator("number_of_boxes")
    @classmethod
    def number_of_boxes_non_negative(cls, v: Decimal) -> Decimal:
        if v < 0:
            raise ValueError("number_of_boxes must be >= 0")
        return v


class ProductImportResponse(BaseModel):
    """Response for product import endpoint."""

    success: bool = True
    product_id: str


class CompanySettingsCreate(BaseModel):
    company_name: str
    trading_name: Optional[str] = None
    company_registration_number: Optional[str] = None
    vat_number: Optional[str] = None
    address_line1: Optional[str] = None
    address_line2: Optional[str] = None
    city: Optional[str] = None
    county: Optional[str] = None
    postcode: Optional[str] = None
    country: str = "United Kingdom"
    phone: Optional[str] = None
    email: Optional[str] = None
    website: Optional[str] = None
    logo_filename: str = "logo1.jpg"
    logo_url: Optional[str] = None
    default_terms_and_conditions: Optional[str] = None
    hourly_install_rate: Optional[Decimal] = None
    installation_lead_time: Optional[InstallationLeadTime] = None
    distance_before_overnight_miles: Optional[Decimal] = None
    cost_per_mile: Optional[Decimal] = None
    hotel_allowance_per_night: Optional[Decimal] = None
    meal_allowance_per_day: Optional[Decimal] = None
    average_speed_mph: Optional[Decimal] = None
    product_import_gross_margin_pct: Optional[Decimal] = None
    bank_name: Optional[str] = None
    bank_account_name: Optional[str] = None
    account_number: Optional[str] = None
    sort_code: Optional[str] = None


class CompanySettingsUpdate(BaseModel):
    company_name: Optional[str] = None
    trading_name: Optional[str] = None
    company_registration_number: Optional[str] = None
    vat_number: Optional[str] = None
    address_line1: Optional[str] = None
    address_line2: Optional[str] = None
    city: Optional[str] = None
    county: Optional[str] = None
    postcode: Optional[str] = None
    country: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    website: Optional[str] = None
    logo_filename: Optional[str] = None
    logo_url: Optional[str] = None
    default_terms_and_conditions: Optional[str] = None
    hourly_install_rate: Optional[Decimal] = None
    installation_lead_time: Optional[InstallationLeadTime] = None
    distance_before_overnight_miles: Optional[Decimal] = None
    cost_per_mile: Optional[Decimal] = None
    hotel_allowance_per_night: Optional[Decimal] = None
    meal_allowance_per_day: Optional[Decimal] = None
    average_speed_mph: Optional[Decimal] = None
    product_import_gross_margin_pct: Optional[Decimal] = None
    bank_name: Optional[str] = None
    bank_account_name: Optional[str] = None
    account_number: Optional[str] = None
    sort_code: Optional[str] = None


class CompanySettingsResponse(BaseModel):
    id: int
    company_name: str
    trading_name: Optional[str]
    company_registration_number: Optional[str]
    vat_number: Optional[str]
    address_line1: Optional[str]
    address_line2: Optional[str]
    city: Optional[str]
    county: Optional[str]
    postcode: Optional[str]
    country: str
    phone: Optional[str]
    email: Optional[str]
    website: Optional[str]
    logo_filename: str
    logo_url: Optional[str] = None
    default_terms_and_conditions: Optional[str]
    hourly_install_rate: Optional[Decimal] = None
    installation_lead_time: Optional[InstallationLeadTime] = None
    distance_before_overnight_miles: Optional[Decimal] = None
    cost_per_mile: Optional[Decimal] = None
    hotel_allowance_per_night: Optional[Decimal] = None
    meal_allowance_per_day: Optional[Decimal] = None
    average_speed_mph: Optional[Decimal] = None
    product_import_gross_margin_pct: Optional[Decimal] = None
    bank_name: Optional[str] = None
    bank_account_name: Optional[str] = None
    account_number: Optional[str] = None
    sort_code: Optional[str] = None
    updated_at: datetime


class DeliveryInstallEstimateRequest(BaseModel):
    customer_postcode: str
    installation_hours: float
    number_of_boxes: Optional[int] = None  # For future use


class DeliveryInstallEstimateResponse(BaseModel):
    distance_miles: float
    travel_time_hours_one_way: float
    fitting_days: int
    requires_overnight: bool
    nights_away: int
    cost_mileage: Optional[Decimal] = None
    cost_labour: Optional[Decimal] = None
    cost_hotel: Optional[Decimal] = None
    cost_meals: Optional[Decimal] = None
    cost_total: Decimal
    settings_incomplete: bool = False  # True if some costs could not be calculated


class QuoteItemCreate(BaseModel):
    product_id: Optional[int] = None
    description: str
    quantity: Decimal
    unit_price: Decimal
    is_custom: bool = False
    sort_order: int = 0
    parent_index: Optional[int] = None  # Index of parent item (0-based) when this is an optional extra; backend sets parent_quote_item_id
    line_type: Optional[QuoteItemLineType] = None  # DELIVERY or INSTALLATION; excluded from PRODUCT-scope discount


class QuoteItemResponse(BaseModel):
    id: int
    quote_id: int
    product_id: Optional[int]
    parent_quote_item_id: Optional[int] = None
    description: str
    quantity: Decimal
    unit_price: Decimal
    line_total: Decimal
    discount_amount: Decimal
    final_line_total: Decimal
    sort_order: int
    is_custom: bool
    line_type: Optional[QuoteItemLineType] = None


class QuoteCreate(BaseModel):
    customer_id: Optional[int] = None  # Can be None during migration
    quote_number: Optional[str] = None  # Auto-generated if not provided
    version: int = 1
    valid_until: Optional[datetime] = None
    terms_and_conditions: Optional[str] = None
    notes: Optional[str] = None
    deposit_amount: Optional[Decimal] = None  # Optional deposit amount inc VAT (defaults to 50% of total inc VAT if not provided)
    items: List[QuoteItemCreate]
    discount_template_ids: Optional[List[int]] = None  # List of discount template IDs to apply
    temperature: Optional[QuoteTemperature] = None
    include_spec_sheets: bool = True  # Include product spec sheets when generating quote PDF


class QuoteDraftUpdate(BaseModel):
    """Update draft quote: items, metadata, and discounts. Only allowed when status is DRAFT."""
    valid_until: Optional[datetime] = None
    terms_and_conditions: Optional[str] = None
    notes: Optional[str] = None
    deposit_amount: Optional[Decimal] = None  # inc VAT
    items: List[QuoteItemCreate]
    discount_template_ids: Optional[List[int]] = None
    temperature: Optional[QuoteTemperature] = None
    include_spec_sheets: Optional[bool] = None  # Include product spec sheets when generating quote PDF


class QuoteUpdate(BaseModel):
    status: Optional["QuoteStatus"] = None
    valid_until: Optional[datetime] = None
    terms_and_conditions: Optional[str] = None
    notes: Optional[str] = None
    deposit_amount: Optional[Decimal] = None  # inc VAT
    include_spec_sheets: Optional[bool] = None  # Include product spec sheets when generating quote PDF
    # Opportunity fields
    opportunity_stage: Optional["OpportunityStage"] = None
    close_probability: Optional[Decimal] = None
    expected_close_date: Optional[datetime] = None
    next_action: Optional[str] = None
    next_action_due_date: Optional[datetime] = None
    owner_id: Optional[int] = None
    temperature: Optional[QuoteTemperature] = None


class QuoteResponse(BaseModel):
    id: int
    customer_id: int
    customer_name: Optional[str] = None
    quote_number: str
    version: int
    status: QuoteStatus
    subtotal: Decimal
    discount_total: Decimal
    total_amount: Decimal
    deposit_amount: Decimal
    balance_amount: Decimal
    currency: str
    valid_until: Optional[datetime]
    terms_and_conditions: Optional[str]
    notes: Optional[str]
    created_by_id: int
    sent_at: Optional[datetime]
    viewed_at: Optional[datetime]  # First viewed at
    last_viewed_at: Optional[datetime] = None  # Last viewed at
    accepted_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime
    # Computed VAT (all amounts above are Ex VAT @ 20%)
    vat_amount: Optional[Decimal] = None
    total_amount_inc_vat: Optional[Decimal] = None
    deposit_amount_inc_vat: Optional[Decimal] = None
    balance_amount_inc_vat: Optional[Decimal] = None
    items: List[QuoteItemResponse] = []
    discounts: List["QuoteDiscountResponse"] = []
    # Opportunity fields
    opportunity_stage: Optional["OpportunityStage"] = None
    close_probability: Optional[Decimal] = None
    expected_close_date: Optional[datetime] = None
    next_action: Optional[str] = None
    next_action_due_date: Optional[datetime] = None
    loss_reason: Optional[str] = None
    loss_category: Optional["LossCategory"] = None
    owner_id: Optional[int] = None
    temperature: Optional[QuoteTemperature] = None
    include_spec_sheets: bool = True  # Include product spec sheets when generating quote PDF
    total_open_count: int = 0  # Total times quote view link was opened (across all sends)
    order_id: Optional[int] = None  # Order ID when quote is accepted (for View order link)
    customer_last_interacted_at: Optional[datetime] = None  # Last Activity date for this customer


class QuoteEmailResponse(BaseModel):
    id: int
    quote_id: int
    to_email: str
    subject: str
    sent_at: datetime
    opened_at: Optional[datetime]
    clicked_at: Optional[datetime]
    open_count: int = 0


class PublicQuoteViewItemResponse(BaseModel):
    """Line item for public quote view (no internal IDs)."""
    description: str
    quantity: Decimal
    unit_price: Decimal
    line_total: Decimal
    final_line_total: Decimal
    sort_order: int


class PublicQuoteCompanyDisplay(BaseModel):
    """Company display info for public quote view header (logo + contact)."""
    trading_name: Optional[str] = None
    logo_url: Optional[str] = None
    address_line1: Optional[str] = None
    address_line2: Optional[str] = None
    city: Optional[str] = None
    county: Optional[str] = None
    postcode: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    website: Optional[str] = None


class PublicQuoteViewResponse(BaseModel):
    """Quote payload for public view page (no auth)."""
    quote_number: str
    customer_name: str
    currency: str
    valid_until: Optional[datetime]
    subtotal: Decimal
    discount_total: Decimal
    total_amount: Decimal
    deposit_amount: Decimal
    balance_amount: Decimal
    vat_amount: Optional[Decimal] = None
    total_amount_inc_vat: Optional[Decimal] = None
    items: List[PublicQuoteViewItemResponse]
    terms_and_conditions: Optional[str] = None
    company_display: Optional[PublicQuoteCompanyDisplay] = None


class QuoteSendRequest(BaseModel):
    to_email: str
    subject: Optional[str] = None
    message: Optional[str] = None  # Additional message in email body


class DiscountTemplateCreate(BaseModel):
    name: str
    description: Optional[str] = None
    discount_type: DiscountType
    discount_value: Decimal
    scope: DiscountScope
    is_giveaway: Optional[bool] = False


class DiscountTemplateUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    discount_type: Optional[DiscountType] = None
    discount_value: Optional[Decimal] = None
    scope: Optional[DiscountScope] = None
    is_active: Optional[bool] = None
    is_giveaway: Optional[bool] = None


class DiscountTemplateResponse(BaseModel):
    id: int
    name: str
    description: Optional[str]
    discount_type: DiscountType
    discount_value: Decimal
    scope: DiscountScope
    is_active: bool
    is_giveaway: bool
    created_at: datetime
    updated_at: datetime


class QuoteDiscountCreate(BaseModel):
    template_id: Optional[int] = None  # Use template or create custom
    discount_type: DiscountType
    discount_value: Decimal
    scope: DiscountScope
    description: Optional[str] = None  # Required if no template_id
    quote_item_id: Optional[int] = None  # Required if scope is PRODUCT


class QuoteDiscountResponse(BaseModel):
    id: int
    quote_id: int
    quote_item_id: Optional[int]
    template_id: Optional[int]
    discount_type: DiscountType
    discount_value: Decimal
    scope: DiscountScope
    discount_amount: Decimal
    description: str
    applied_at: datetime
    applied_by_id: int


class OrderItemResponse(BaseModel):
    id: int
    order_id: int
    quote_item_id: Optional[int] = None
    product_id: Optional[int] = None
    description: str
    quantity: Decimal
    unit_price: Decimal
    line_total: Decimal
    discount_amount: Decimal
    final_line_total: Decimal
    sort_order: int
    is_custom: bool


class OrderUpdate(BaseModel):
    deposit_paid: Optional[bool] = None
    balance_paid: Optional[bool] = None
    paid_in_full: Optional[bool] = None
    installation_booked: Optional[bool] = None
    installation_completed: Optional[bool] = None


class AccessSheetResponse(BaseModel):
    """For order page: access sheet status and completed data."""
    access_sheet_url: Optional[str] = None
    completed: bool = False
    completed_at: Optional[datetime] = None
    answers: Optional[dict] = None


class OrderResponse(BaseModel):
    id: int
    quote_id: int
    customer_id: Optional[int] = None
    customer_name: Optional[str] = None
    order_number: str
    subtotal: Decimal
    discount_total: Decimal
    total_amount: Decimal
    deposit_amount: Decimal
    balance_amount: Decimal
    currency: str
    terms_and_conditions: Optional[str] = None
    notes: Optional[str] = None
    created_by_id: int
    created_at: datetime
    deposit_paid: bool = False
    balance_paid: bool = False
    paid_in_full: bool = False
    installation_booked: bool = False
    installation_completed: bool = False
    invoice_number: Optional[str] = None
    xero_invoice_id: Optional[str] = None
    items: List[OrderItemResponse] = []
    access_sheet: Optional[AccessSheetResponse] = None


class AccessSheetContextResponse(BaseModel):
    """Public GET: form context and pre-fill for customer."""
    customer_name: str
    order_number: str
    completed: bool = False
    completed_at: Optional[datetime] = None
    answers: Optional[dict] = None  # If completed, existing answers


class AccessSheetSubmitRequest(BaseModel):
    """Public POST: form submission from customer."""
    access_4x4_trailer: Optional[str] = None  # yes | no
    access_4x4_notes: Optional[str] = None
    drive_near_build: Optional[str] = None
    drive_near_build_notes: Optional[str] = None
    permission_drive_land: Optional[str] = None
    permission_drive_land_notes: Optional[str] = None
    balances_paid_before: Optional[str] = None
    balances_paid_before_notes: Optional[str] = None
    horses_contained: Optional[str] = None
    horses_contained_notes: Optional[str] = None
    site_level: Optional[str] = None
    site_level_notes: Optional[str] = None
    area_clear: Optional[str] = None
    area_clear_notes: Optional[str] = None
    ground_type: Optional[str] = None  # NEW_CONCRETE | OLD_CONCRETE | GRASS_FIELD | HARDCORE
    brickwork_if_concrete: Optional[str] = None
    brickwork_notes: Optional[str] = None
    electricity_available: Optional[str] = None
    electricity_notes: Optional[str] = None
    toilet_facilities: Optional[str] = None
    toilet_notes: Optional[str] = None
    customer_signature: Optional[str] = None
    notes: Optional[str] = None


class AccessSheetSendResponse(BaseModel):
    """Response from POST send: link for staff to copy or email."""
    access_sheet_url: str
    access_token: str


class DiscountRequestCreate(BaseModel):
    discount_type: DiscountType
    discount_value: Decimal
    scope: DiscountScope
    reason: Optional[str] = None


class DiscountRequestResponse(BaseModel):
    id: int
    quote_id: int
    requested_by_id: int
    requested_by_name: Optional[str] = None
    discount_type: DiscountType
    discount_value: Decimal
    scope: DiscountScope
    reason: Optional[str]
    status: DiscountRequestStatus
    approved_by_id: Optional[int]
    responded_at: Optional[datetime]
    rejection_reason: Optional[str]
    created_at: datetime
    updated_at: datetime
    quote_number: Optional[str] = None


class DiscountRequestReject(BaseModel):
    rejection_reason: Optional[str] = None


class ReminderResponse(BaseModel):
    id: int
    reminder_type: ReminderType
    lead_id: Optional[int]
    quote_id: Optional[int]
    customer_id: Optional[int]
    assigned_to_id: int
    priority: ReminderPriority
    title: str
    message: str
    suggested_action: SuggestedAction
    days_stale: int
    created_at: datetime
    dismissed_at: Optional[datetime]
    acted_upon_at: Optional[datetime]
    lead_name: Optional[str] = None
    quote_number: Optional[str] = None
    customer_name: Optional[str] = None


class ManualReminderCreate(BaseModel):
    """Create a user-defined reminder (e.g. call back)."""
    customer_id: int
    title: str
    message: str
    reminder_date: date  # Day to be reminded


class ReminderDismissRequest(BaseModel):
    reason: Optional[str] = None


class ReminderActRequest(BaseModel):
    action_taken: str
    notes: Optional[str] = None


class ReminderRuleResponse(BaseModel):
    id: int
    rule_name: str
    entity_type: str
    status: Optional[str]
    threshold_days: int
    check_type: str
    is_active: bool
    priority: ReminderPriority
    suggested_action: SuggestedAction
    created_at: datetime
    updated_at: datetime


class ReminderRuleUpdate(BaseModel):
    threshold_days: Optional[int] = None
    is_active: Optional[bool] = None
    priority: Optional[ReminderPriority] = None
    suggested_action: Optional[SuggestedAction] = None


class StaleSummaryResponse(BaseModel):
    total_reminders: int
    urgent_count: int
    high_count: int
    medium_count: int
    low_count: int
    stale_leads_count: int
    stale_quotes_count: int


class CustomerHistoryEventType(str, Enum):
    ACTIVITY = "ACTIVITY"
    LEAD_STATUS_CHANGE = "LEAD_STATUS_CHANGE"
    QUOTE_CREATED = "QUOTE_CREATED"
    QUOTE_SENT = "QUOTE_SENT"
    QUOTE_VIEWED = "QUOTE_VIEWED"
    QUOTE_ACCEPTED = "QUOTE_ACCEPTED"
    QUOTE_REJECTED = "QUOTE_REJECTED"
    QUOTE_EXPIRED = "QUOTE_EXPIRED"
    QUOTE_UPDATED = "QUOTE_UPDATED"
    EMAIL_SENT = "EMAIL_SENT"
    EMAIL_RECEIVED = "EMAIL_RECEIVED"
    CUSTOMER_CREATED = "CUSTOMER_CREATED"
    CUSTOMER_UPDATED = "CUSTOMER_UPDATED"
    LEAD_QUALIFIED = "LEAD_QUALIFIED"
    OPPORTUNITY_CREATED = "OPPORTUNITY_CREATED"


class CustomerHistoryEvent(BaseModel):
    event_type: CustomerHistoryEventType
    timestamp: datetime
    title: str
    description: Optional[str] = None
    metadata: Optional[dict] = None  # Additional context (quote number, lead status, etc.)
    created_by_name: Optional[str] = None
    created_by_id: Optional[int] = None


class CustomerHistoryResponse(BaseModel):
    events: List[CustomerHistoryEvent]
