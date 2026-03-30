from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select
from typing import Optional, List
from app.database import get_session
from app.models import DiscountTemplate, User
from app.auth import get_current_user, require_role
from app.schemas import (
    DiscountTemplateCreate,
    DiscountTemplateUpdate,
    DiscountTemplateResponse
)
from app.models import UserRole
from datetime import datetime
from app.discount_limits import redemption_counts_by_template

router = APIRouter(prefix="/api/discounts", tags=["discounts"])


def _template_to_response(template: DiscountTemplate, counts: dict[int, int]) -> DiscountTemplateResponse:
    usage_count = counts.get(template.id, 0)
    remaining_uses = None
    if template.max_uses is not None:
        remaining_uses = max(0, template.max_uses - usage_count)
    data = template.dict()
    return DiscountTemplateResponse(
        **data,
        usage_count=usage_count,
        remaining_uses=remaining_uses,
    )


@router.get("", response_model=List[DiscountTemplateResponse])
async def get_discount_templates(
    is_active: Optional[bool] = None,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """Get list of discount templates with optional filters."""
    statement = select(DiscountTemplate)
    
    if is_active is not None:
        statement = statement.where(DiscountTemplate.is_active == is_active)
    
    statement = statement.order_by(DiscountTemplate.created_at.desc())
    templates = session.exec(statement).all()
    counts = redemption_counts_by_template(session)
    return [_template_to_response(t, counts) for t in templates]


@router.get("/{discount_id}", response_model=DiscountTemplateResponse)
async def get_discount_template(
    discount_id: int,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """Get discount template details."""
    statement = select(DiscountTemplate).where(DiscountTemplate.id == discount_id)
    template = session.exec(statement).first()
    
    if not template:
        raise HTTPException(status_code=404, detail="Discount template not found")
    counts = redemption_counts_by_template(session)
    return _template_to_response(template, counts)


@router.post("", response_model=DiscountTemplateResponse)
async def create_discount_template(
    template_data: DiscountTemplateCreate,
    session: Session = Depends(get_session),
    current_user: User = Depends(require_role([UserRole.DIRECTOR]))
):
    """Create a new discount template. DIRECTOR only."""
    template = DiscountTemplate(
        **template_data.dict(),
        created_by_id=current_user.id
    )
    session.add(template)
    session.commit()
    session.refresh(template)
    counts = redemption_counts_by_template(session)
    return _template_to_response(template, counts)


@router.patch("/{discount_id}", response_model=DiscountTemplateResponse)
async def update_discount_template(
    discount_id: int,
    template_data: DiscountTemplateUpdate,
    session: Session = Depends(get_session),
    current_user: User = Depends(require_role([UserRole.DIRECTOR]))
):
    """Update a discount template. DIRECTOR only."""
    statement = select(DiscountTemplate).where(DiscountTemplate.id == discount_id)
    template = session.exec(statement).first()
    
    if not template:
        raise HTTPException(status_code=404, detail="Discount template not found")
    
    update_data = template_data.dict(exclude_unset=True)
    for field, value in update_data.items():
        setattr(template, field, value)
    
    template.updated_at = datetime.utcnow()
    session.add(template)
    session.commit()
    session.refresh(template)
    
    counts = redemption_counts_by_template(session)
    return _template_to_response(template, counts)


@router.delete("/{discount_id}")
async def delete_discount_template(
    discount_id: int,
    session: Session = Depends(get_session),
    current_user: User = Depends(require_role([UserRole.DIRECTOR]))
):
    """Deactivate a discount template (soft delete). DIRECTOR only."""
    statement = select(DiscountTemplate).where(DiscountTemplate.id == discount_id)
    template = session.exec(statement).first()
    
    if not template:
        raise HTTPException(status_code=404, detail="Discount template not found")
    
    template.is_active = False
    template.updated_at = datetime.utcnow()
    session.add(template)
    session.commit()
    
    return {"message": "Discount template deactivated successfully"}
