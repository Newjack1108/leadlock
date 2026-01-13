from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlmodel import Session, select, or_
from typing import Optional, List
from app.database import get_session
from app.models import Lead, User, Activity, StatusHistory, LeadStatus, ActivityType
from app.auth import get_current_user
from app.schemas import (
    LeadCreate, LeadUpdate, LeadResponse, StatusTransitionRequest,
    ActivityCreate, ActivityResponse, StatusHistoryResponse
)
from app.workflow import can_transition, check_quote_prerequisites, check_sla_overdue
from datetime import datetime

router = APIRouter(prefix="/api/leads", tags=["leads"])


def enrich_lead_response(lead: Lead, session: Session, current_user: User) -> LeadResponse:
    """Enrich lead with SLA badge and quote lock info."""
    sla_badge = check_sla_overdue(lead, session)
    
    quote_locked = False
    quote_lock_reason = None
    if lead.status == LeadStatus.QUALIFIED:
        can_quote, error = check_quote_prerequisites(lead, session)
        if not can_quote:
            quote_locked = True
            quote_lock_reason = error
    
    return LeadResponse(
        id=lead.id,
        name=lead.name,
        email=lead.email,
        phone=lead.phone,
        postcode=lead.postcode,
        status=lead.status,
        timeframe=lead.timeframe,
        scope_notes=lead.scope_notes,
        product_interest=lead.product_interest,
        assigned_to_id=lead.assigned_to_id,
        created_at=lead.created_at,
        updated_at=lead.updated_at,
        sla_badge=sla_badge,
        quote_locked=quote_locked,
        quote_lock_reason=quote_lock_reason,
    )


@router.get("", response_model=List[LeadResponse])
async def get_leads(
    status_filter: Optional[LeadStatus] = Query(None, alias="status"),
    search: Optional[str] = Query(None),
    my_leads_only: bool = Query(False, alias="myLeads"),
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    statement = select(Lead)
    
    if status_filter:
        statement = statement.where(Lead.status == status_filter)
    
    if my_leads_only:
        statement = statement.where(Lead.assigned_to_id == current_user.id)
    
    if search:
        search_term = f"%{search}%"
        statement = statement.where(
            or_(
                Lead.name.ilike(search_term),
                Lead.email.ilike(search_term),
                Lead.phone.ilike(search_term),
                Lead.postcode.ilike(search_term)
            )
        )
    
    statement = statement.order_by(Lead.created_at.desc())
    leads = session.exec(statement).all()
    
    return [enrich_lead_response(lead, session, current_user) for lead in leads]


@router.get("/{lead_id}", response_model=LeadResponse)
async def get_lead(
    lead_id: int,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    statement = select(Lead).where(Lead.id == lead_id)
    lead = session.exec(statement).first()
    
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    
    return enrich_lead_response(lead, session, current_user)


@router.post("", response_model=LeadResponse)
async def create_lead(
    lead_data: LeadCreate,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    lead = Lead(**lead_data.dict())
    lead.assigned_to_id = current_user.id
    session.add(lead)
    session.commit()
    session.refresh(lead)
    
    # Create initial status history
    status_history = StatusHistory(
        lead_id=lead.id,
        new_status=lead.status,
        changed_by_id=current_user.id
    )
    session.add(status_history)
    session.commit()
    
    return enrich_lead_response(lead, session, current_user)


@router.patch("/{lead_id}", response_model=LeadResponse)
async def update_lead(
    lead_id: int,
    lead_data: LeadUpdate,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    statement = select(Lead).where(Lead.id == lead_id)
    lead = session.exec(statement).first()
    
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    
    update_data = lead_data.dict(exclude_unset=True)
    for field, value in update_data.items():
        setattr(lead, field, value)
    
    lead.updated_at = datetime.utcnow()
    session.add(lead)
    session.commit()
    session.refresh(lead)
    
    return enrich_lead_response(lead, session, current_user)


@router.post("/{lead_id}/transition", response_model=LeadResponse)
async def transition_lead_status(
    lead_id: int,
    transition: StatusTransitionRequest,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    statement = select(Lead).where(Lead.id == lead_id)
    lead = session.exec(statement).first()
    
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    
    is_override = transition.override_reason is not None and transition.override_reason.strip() != ""
    allowed, error = can_transition(
        current_user.role,
        lead.status,
        transition.new_status,
        lead,
        session,
        is_override=is_override
    )
    
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error
        )
    
    old_status = lead.status
    lead.status = transition.new_status
    lead.updated_at = datetime.utcnow()
    session.add(lead)
    
    # Log status change
    status_history = StatusHistory(
        lead_id=lead.id,
        old_status=old_status,
        new_status=transition.new_status,
        changed_by_id=current_user.id,
        override_reason=transition.override_reason if is_override else None
    )
    session.add(status_history)
    session.commit()
    session.refresh(lead)
    
    return enrich_lead_response(lead, session, current_user)


@router.get("/{lead_id}/allowed-transitions")
async def get_allowed_transitions(
    lead_id: int,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    from app.workflow import get_allowed_transitions
    
    statement = select(Lead).where(Lead.id == lead_id)
    lead = session.exec(statement).first()
    
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    
    allowed = get_allowed_transitions(current_user.role, lead.status)
    
    # Director can override, so return all statuses except current
    if current_user.role.value == "DIRECTOR":
        all_statuses = [s for s in LeadStatus if s != lead.status]
        return {"allowed_transitions": [s.value for s in all_statuses], "can_override": True}
    
    return {"allowed_transitions": [s.value for s in allowed], "can_override": False}


@router.post("/{lead_id}/activities", response_model=ActivityResponse)
async def create_activity(
    lead_id: int,
    activity_data: ActivityCreate,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    statement = select(Lead).where(Lead.id == lead_id)
    lead = session.exec(statement).first()
    
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    
    activity = Activity(
        lead_id=lead_id,
        activity_type=activity_data.activity_type,
        notes=activity_data.notes,
        created_by_id=current_user.id
    )
    session.add(activity)
    session.commit()
    session.refresh(activity)
    
    # Auto-transition to ENGAGED if we have engagement proof
    from app.workflow import ENGAGEMENT_PROOF_TYPES
    if activity.activity_type in ENGAGEMENT_PROOF_TYPES and lead.status == LeadStatus.CONTACT_ATTEMPTED:
        allowed, error = can_transition(
            current_user.role,
            lead.status,
            LeadStatus.ENGAGED,
            lead,
            session
        )
        if allowed:
            old_status = lead.status
            lead.status = LeadStatus.ENGAGED
            lead.updated_at = datetime.utcnow()
            session.add(lead)
            
            status_history = StatusHistory(
                lead_id=lead.id,
                old_status=old_status,
                new_status=LeadStatus.ENGAGED,
                changed_by_id=current_user.id
            )
            session.add(status_history)
            session.commit()
            session.refresh(lead)
    
    return ActivityResponse(
        id=activity.id,
        lead_id=activity.lead_id,
        activity_type=activity.activity_type,
        notes=activity.notes,
        created_by_id=activity.created_by_id,
        created_at=activity.created_at,
        created_by_name=current_user.full_name
    )


@router.get("/{lead_id}/activities", response_model=List[ActivityResponse])
async def get_lead_activities(
    lead_id: int,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    statement = select(Activity, User).join(User, Activity.created_by_id == User.id).where(
        Activity.lead_id == lead_id
    ).order_by(Activity.created_at.desc())
    
    results = session.exec(statement).all()
    activities = []
    for activity, user in results:
        activities.append(ActivityResponse(
            id=activity.id,
            lead_id=activity.lead_id,
            activity_type=activity.activity_type,
            notes=activity.notes,
            created_by_id=activity.created_by_id,
            created_at=activity.created_at,
            created_by_name=user.full_name
        ))
    
    return activities


@router.get("/{lead_id}/status-history", response_model=List[StatusHistoryResponse])
async def get_status_history(
    lead_id: int,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    statement = select(StatusHistory, User).join(User, StatusHistory.changed_by_id == User.id).where(
        StatusHistory.lead_id == lead_id
    ).order_by(StatusHistory.created_at.desc())
    
    results = session.exec(statement).all()
    history = []
    for status_hist, user in results:
        history.append(StatusHistoryResponse(
            id=status_hist.id,
            lead_id=status_hist.lead_id,
            old_status=status_hist.old_status,
            new_status=status_hist.new_status,
            changed_by_id=status_hist.changed_by_id,
            override_reason=status_hist.override_reason,
            created_at=status_hist.created_at,
            changed_by_name=user.full_name
        ))
    
    return history
