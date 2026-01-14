from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select
from app.database import get_session
from app.models import CompanySettings, User
from app.auth import get_current_user, require_role
from app.schemas import CompanySettingsCreate, CompanySettingsUpdate, CompanySettingsResponse
from app.models import UserRole
from datetime import datetime

router = APIRouter(prefix="/api/settings", tags=["settings"])


def get_company_settings(session: Session) -> CompanySettings:
    """Get or create the singleton company settings."""
    statement = select(CompanySettings)
    settings = session.exec(statement).first()
    return settings


@router.get("/company", response_model=CompanySettingsResponse)
async def get_company_settings_endpoint(
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """Get company settings. All authenticated users can view."""
    settings = get_company_settings(session)
    
    if not settings:
        raise HTTPException(status_code=404, detail="Company settings not found. Please create them first.")
    
    return CompanySettingsResponse(**settings.dict())


@router.post("/company", response_model=CompanySettingsResponse)
async def create_company_settings(
    settings_data: CompanySettingsCreate,
    session: Session = Depends(get_session),
    current_user: User = Depends(require_role([UserRole.DIRECTOR]))
):
    """Create company settings. DIRECTOR only. Only works if none exist."""
    existing = get_company_settings(session)
    if existing:
        raise HTTPException(status_code=400, detail="Company settings already exist. Use PUT to update.")
    
    settings = CompanySettings(**settings_data.dict(), updated_by_id=current_user.id)
    session.add(settings)
    session.commit()
    session.refresh(settings)
    
    return CompanySettingsResponse(**settings.dict())


@router.put("/company", response_model=CompanySettingsResponse)
async def update_company_settings(
    settings_data: CompanySettingsUpdate,
    session: Session = Depends(get_session),
    current_user: User = Depends(require_role([UserRole.DIRECTOR]))
):
    """Update company settings. DIRECTOR only."""
    settings = get_company_settings(session)
    
    if not settings:
        raise HTTPException(status_code=404, detail="Company settings not found. Use POST to create them first.")
    
    update_data = settings_data.dict(exclude_unset=True)
    for field, value in update_data.items():
        setattr(settings, field, value)
    
    settings.updated_by_id = current_user.id
    settings.updated_at = datetime.utcnow()
    session.add(settings)
    session.commit()
    session.refresh(settings)
    
    return CompanySettingsResponse(**settings.dict())
