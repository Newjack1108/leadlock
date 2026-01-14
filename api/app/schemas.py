from pydantic import BaseModel, EmailStr
from typing import Optional, List
from datetime import datetime
from decimal import Decimal
from app.models import (
    LeadStatus, ActivityType, Timeframe, UserRole, ProductCategory,
    QuoteStatus, DiscountType, DiscountScope, LeadType, LeadSource
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


class LeadCreate(BaseModel):
    name: str
    email: Optional[str] = None
    phone: Optional[str] = None
    postcode: Optional[str] = None
    description: Optional[str] = None
    company_name: Optional[str] = None
    address_line1: Optional[str] = None
    address_line2: Optional[str] = None
    city: Optional[str] = None
    county: Optional[str] = None
    country: Optional[str] = "United Kingdom"
    lead_type: Optional[LeadType] = None
    lead_source: Optional[LeadSource] = None


class LeadUpdate(BaseModel):
    name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    postcode: Optional[str] = None
    description: Optional[str] = None
    company_name: Optional[str] = None
    address_line1: Optional[str] = None
    address_line2: Optional[str] = None
    city: Optional[str] = None
    county: Optional[str] = None
    country: Optional[str] = None
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
    company_name: Optional[str] = None
    address_line1: Optional[str] = None
    address_line2: Optional[str] = None
    city: Optional[str] = None
    county: Optional[str] = None
    country: Optional[str] = "United Kingdom"
    customer_since: Optional[datetime] = None
    customer_number: Optional[str] = None
    status: LeadStatus
    timeframe: Timeframe
    scope_notes: Optional[str]
    product_interest: Optional[str]
    lead_type: LeadType
    lead_source: LeadSource
    assigned_to_id: Optional[int]
    created_at: datetime
    updated_at: datetime
    sla_badge: Optional[str] = None
    quote_locked: bool = False
    quote_lock_reason: Optional[dict] = None


class StatusTransitionRequest(BaseModel):
    new_status: LeadStatus
    override_reason: Optional[str] = None


class ActivityCreate(BaseModel):
    activity_type: ActivityType
    notes: Optional[str] = None


class ActivityResponse(BaseModel):
    id: int
    lead_id: int
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
    logo_filename: str = "logo1.png"


class CompanySettingsUpdate(BaseModel):
    company_name: Optional[str] = None
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
    lead_id: int
    quote_number: Optional[str] = None  # Auto-generated if not provided
    version: int = 1
    valid_until: Optional[datetime] = None
    terms_and_conditions: Optional[str] = None
    notes: Optional[str] = None
    items: List[QuoteItemCreate]


class QuoteUpdate(BaseModel):
    valid_until: Optional[datetime] = None
    terms_and_conditions: Optional[str] = None
    notes: Optional[str] = None


class QuoteResponse(BaseModel):
    id: int
    lead_id: int
    quote_number: str
    version: int
    status: QuoteStatus
    subtotal: Decimal
    discount_total: Decimal
    total_amount: Decimal
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
