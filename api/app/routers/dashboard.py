from fastapi import APIRouter, Depends
from sqlmodel import Session, select, func
from app.database import get_session
from app.models import Lead, LeadStatus, Activity
from app.auth import get_current_user
from app.schemas import DashboardStats
from datetime import datetime, timedelta

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


@router.get("/stats", response_model=DashboardStats)
async def get_dashboard_stats(
    session: Session = Depends(get_session),
    current_user = Depends(get_current_user)
):
    # Count leads by status
    total_leads = session.exec(select(func.count(Lead.id))).one()
    new_count = session.exec(select(func.count(Lead.id)).where(Lead.status == LeadStatus.NEW)).one()
    engaged_count = session.exec(select(func.count(Lead.id)).where(
        Lead.status.in_([LeadStatus.ENGAGED, LeadStatus.QUALIFIED, LeadStatus.QUOTED, LeadStatus.WON])
    )).one()
    qualified_count = session.exec(select(func.count(Lead.id)).where(
        Lead.status.in_([LeadStatus.QUALIFIED, LeadStatus.QUOTED, LeadStatus.WON])
    )).one()
    quoted_count = session.exec(select(func.count(Lead.id)).where(Lead.status == LeadStatus.QUOTED)).one()
    won_count = session.exec(select(func.count(Lead.id)).where(Lead.status == LeadStatus.WON)).one()
    lost_count = session.exec(select(func.count(Lead.id)).where(Lead.status == LeadStatus.LOST)).one()
    
    engaged_percentage = (engaged_count / total_leads * 100) if total_leads > 0 else 0.0
    qualified_percentage = (qualified_count / total_leads * 100) if total_leads > 0 else 0.0
    
    return DashboardStats(
        total_leads=total_leads,
        new_count=new_count,
        engaged_count=engaged_count,
        qualified_count=qualified_count,
        quoted_count=quoted_count,
        won_count=won_count,
        lost_count=lost_count,
        engaged_percentage=round(engaged_percentage, 1),
        qualified_percentage=round(qualified_percentage, 1)
    )


@router.get("/stuck-leads")
async def get_stuck_leads(
    session: Session = Depends(get_session),
    current_user = Depends(get_current_user)
):
    """Get oldest lead per status that hasn't been updated recently."""
    stuck_leads = []
    
    for status in LeadStatus:
        statement = select(Lead).where(Lead.status == status).order_by(Lead.updated_at.asc()).limit(1)
        lead = session.exec(statement).first()
        if lead:
            days_old = (datetime.utcnow() - lead.updated_at).days
            stuck_leads.append({
                "id": lead.id,
                "name": lead.name,
                "status": lead.status.value,
                "days_old": days_old,
                "updated_at": lead.updated_at.isoformat()
            })
    
    return stuck_leads
