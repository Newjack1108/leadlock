from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select
from app.database import get_session
from app.models import Lead, User, StatusHistory, LeadStatus
from app.schemas import LeadCreate, LeadResponse
from app.auth import get_webhook_api_key
from app.workflow import check_sla_overdue, check_quote_prerequisites
from app.routers.leads import enrich_lead_response
import os

router = APIRouter(prefix="/api/webhooks", tags=["webhooks"])


@router.post("/leads", response_model=LeadResponse)
async def create_lead_webhook(
    lead_data: LeadCreate,
    api_key: str = Depends(get_webhook_api_key),
    session: Session = Depends(get_session)
):
    """
    Create a lead via webhook (e.g., from Make.com).
    Requires X-API-Key header for authentication.
    """
    # Get default user ID from environment variable (optional)
    default_user_id = os.getenv("WEBHOOK_DEFAULT_USER_ID")
    
    # Create lead
    lead = Lead(**lead_data.dict())
    
    # Assign to default user if configured, otherwise leave unassigned
    if default_user_id:
        try:
            user_id = int(default_user_id)
            # Verify user exists
            statement = select(User).where(User.id == user_id)
            user = session.exec(statement).first()
            if user:
                lead.assigned_to_id = user_id
        except (ValueError, TypeError):
            # Invalid user ID, leave unassigned
            pass
    
    session.add(lead)
    session.commit()
    session.refresh(lead)
    
    # Create initial status history
    # Use default user ID for status history if available, otherwise use None
    changed_by_id = lead.assigned_to_id if lead.assigned_to_id else None
    
    if changed_by_id:
        status_history = StatusHistory(
            lead_id=lead.id,
            new_status=lead.status,
            changed_by_id=changed_by_id
        )
        session.add(status_history)
        session.commit()
    
    # For webhook responses, we need to create a minimal user object for enrich_lead_response
    # Since we don't have a current_user, we'll pass None and handle it in enrich_lead_response
    # Actually, let's get the user if assigned, otherwise create a dummy response
    if lead.assigned_to_id:
        statement = select(User).where(User.id == lead.assigned_to_id)
        current_user = session.exec(statement).first()
    else:
        # Create a minimal user-like object for the response
        # We'll just return the lead without enrichment if no user
        current_user = None
    
    if current_user:
        return enrich_lead_response(lead, session, current_user)
    else:
        # Return basic response without enrichment if no user assigned
        # Still check SLA and quote lock status
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
            description=lead.description,
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
