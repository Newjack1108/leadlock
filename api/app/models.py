from sqlmodel import SQLModel, Field, Relationship
from typing import Optional, List
from datetime import datetime
from enum import Enum


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


class User(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    email: str = Field(unique=True, index=True)
    hashed_password: str
    full_name: str
    role: UserRole
    created_at: datetime = Field(default_factory=datetime.utcnow)
    
    # Relationships
    assigned_leads: List["Lead"] = Relationship(back_populates="assigned_to_user")


class Lead(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    email: Optional[str] = None
    phone: Optional[str] = None
    postcode: Optional[str] = None
    status: LeadStatus = Field(default=LeadStatus.NEW)
    timeframe: Timeframe = Field(default=Timeframe.UNKNOWN)
    scope_notes: Optional[str] = None
    product_interest: Optional[str] = None
    assigned_to_id: Optional[int] = Field(default=None, foreign_key="user.id")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    
    # Relationships
    assigned_to_user: Optional[User] = Relationship(back_populates="assigned_leads")
    activities: List["Activity"] = Relationship(back_populates="lead")
    status_history: List["StatusHistory"] = Relationship(back_populates="lead")


class Activity(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    lead_id: int = Field(foreign_key="lead.id")
    activity_type: ActivityType
    notes: Optional[str] = None
    created_by_id: int = Field(foreign_key="user.id")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    
    # Relationships
    lead: Lead = Relationship(back_populates="activities")
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
