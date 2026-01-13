from pydantic import BaseModel, EmailStr
from typing import Optional
from datetime import datetime
from app.models import LeadStatus, ActivityType, Timeframe, UserRole


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


class LeadUpdate(BaseModel):
    name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    postcode: Optional[str] = None
    timeframe: Optional[Timeframe] = None
    scope_notes: Optional[str] = None
    product_interest: Optional[str] = None
    assigned_to_id: Optional[int] = None


class LeadResponse(BaseModel):
    id: int
    name: str
    email: Optional[str]
    phone: Optional[str]
    postcode: Optional[str]
    status: LeadStatus
    timeframe: Timeframe
    scope_notes: Optional[str]
    product_interest: Optional[str]
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
