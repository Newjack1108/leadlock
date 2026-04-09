from datetime import datetime
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from app.auth import get_current_user, require_role
from app.database import get_session
from app.models import FacebookAdvertProfile, User, UserRole
from app.schemas import (
    FacebookAdvertProfileCreate,
    FacebookAdvertProfileResponse,
    FacebookAdvertProfileUpdate,
)

router = APIRouter(prefix="/api/settings/facebook-adverts", tags=["facebook-adverts"])


@router.get("", response_model=List[FacebookAdvertProfileResponse])
async def list_facebook_adverts(
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    statement = select(FacebookAdvertProfile).order_by(
        FacebookAdvertProfile.is_active.desc(),
        FacebookAdvertProfile.name.asc(),
    )
    adverts = session.exec(statement).all()
    return [FacebookAdvertProfileResponse(**advert.dict()) for advert in adverts]


@router.post("", response_model=FacebookAdvertProfileResponse)
async def create_facebook_advert(
    advert_data: FacebookAdvertProfileCreate,
    session: Session = Depends(get_session),
    current_user: User = Depends(require_role([UserRole.DIRECTOR])),
):
    advert = FacebookAdvertProfile(**advert_data.dict())
    session.add(advert)
    session.commit()
    session.refresh(advert)
    return FacebookAdvertProfileResponse(**advert.dict())


@router.patch("/{advert_id}", response_model=FacebookAdvertProfileResponse)
async def update_facebook_advert(
    advert_id: int,
    advert_data: FacebookAdvertProfileUpdate,
    session: Session = Depends(get_session),
    current_user: User = Depends(require_role([UserRole.DIRECTOR])),
):
    statement = select(FacebookAdvertProfile).where(FacebookAdvertProfile.id == advert_id)
    advert = session.exec(statement).first()
    if not advert:
        raise HTTPException(status_code=404, detail="Facebook advert profile not found")

    update_data = advert_data.dict(exclude_unset=True)
    for field, value in update_data.items():
        setattr(advert, field, value)

    advert.updated_at = datetime.utcnow()
    session.add(advert)
    session.commit()
    session.refresh(advert)
    return FacebookAdvertProfileResponse(**advert.dict())
