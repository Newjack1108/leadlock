from pydantic import BaseModel, EmailStr
from typing import Optional, List
from datetime import datetime
from decimal import Decimal
from app.models import (
    LeadStatus, ActivityType, Timeframe, UserRole, ProductCategory,
    QuoteStatus, DiscountType, DiscountScope, LeadType, LeadSource,
    EmailDirection, ReminderPriority, ReminderType, SuggestedAction,
    OpportunityStage, LossCategory
)


class Token(BaseModel):
    access_token: str
    token_type: str


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class UserResponse(BaseModel):
    id: int
    email: str
    full_name: str
    role: UserRole


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


class OpportunityWonRequest(BaseModel):
    confirmed_value: Optional[Decimal] = None  # Optional confirmation of final value


class OpportunityLostRequest(BaseModel):
    loss_reason: str
    loss_category: "LossCategory"


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


class DashboardStats(BaseModel):
    total_leads: int
    new_count: int
    engaged_count: int
    qualified_count: int
    quoted_count: int
    won_count: int
    lost_count: int
    engaged_percentage: float
    qualified_percentage: float


class ProductCreate(BaseModel):
    name: str
    description: Optional[str] = None
    category: ProductCategory
    subcategory: Optional[str] = None
    is_extra: bool = False
    base_price: Decimal
    unit: str = "unit"
    sku: Optional[str] = None
    image_url: Optional[str] = None
    specifications: Optional[str] = None


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
    created_at: datetime
    updated_at: datetime


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
    updated_at: datetime


class QuoteItemCreate(BaseModel):
    product_id: Optional[int] = None
    description: str
    quantity: Decimal
    unit_price: Decimal
    is_custom: bool = False
    sort_order: int = 0


class QuoteItemResponse(BaseModel):
    id: int
    quote_id: int
    product_id: Optional[int]
    description: str
    quantity: Decimal
    unit_price: Decimal
    line_total: Decimal
    discount_amount: Decimal
    final_line_total: Decimal
    sort_order: int
    is_custom: bool


class QuoteCreate(BaseModel):
    customer_id: Optional[int] = None  # Can be None during migration
    quote_number: Optional[str] = None  # Auto-generated if not provided
    version: int = 1
    valid_until: Optional[datetime] = None
    terms_and_conditions: Optional[str] = None
    notes: Optional[str] = None
    deposit_amount: Optional[Decimal] = None  # Optional deposit amount (defaults to 50% of total if not provided)
    items: List[QuoteItemCreate]


class QuoteUpdate(BaseModel):
    status: Optional["QuoteStatus"] = None
    valid_until: Optional[datetime] = None
    terms_and_conditions: Optional[str] = None
    notes: Optional[str] = None
    deposit_amount: Optional[Decimal] = None
    # Opportunity fields
    opportunity_stage: Optional["OpportunityStage"] = None
    close_probability: Optional[Decimal] = None
    expected_close_date: Optional[datetime] = None
    next_action: Optional[str] = None
    next_action_due_date: Optional[datetime] = None
    owner_id: Optional[int] = None


class QuoteResponse(BaseModel):
    id: int
    customer_id: int
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
    viewed_at: Optional[datetime]
    accepted_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime
    items: List[QuoteItemResponse] = []
    # Opportunity fields
    opportunity_stage: Optional["OpportunityStage"] = None
    close_probability: Optional[Decimal] = None
    expected_close_date: Optional[datetime] = None
    next_action: Optional[str] = None
    next_action_due_date: Optional[datetime] = None
    loss_reason: Optional[str] = None
    loss_category: Optional["LossCategory"] = None
    owner_id: Optional[int] = None


class QuoteEmailResponse(BaseModel):
    id: int
    quote_id: int
    to_email: str
    subject: str
    sent_at: datetime
    opened_at: Optional[datetime]
    clicked_at: Optional[datetime]


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


class DiscountTemplateUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    discount_type: Optional[DiscountType] = None
    discount_value: Optional[Decimal] = None
    scope: Optional[DiscountScope] = None
    is_active: Optional[bool] = None


class DiscountTemplateResponse(BaseModel):
    id: int
    name: str
    description: Optional[str]
    discount_type: DiscountType
    discount_value: Decimal
    scope: DiscountScope
    is_active: bool
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
