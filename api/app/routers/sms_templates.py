"""
SMS template router for managing SMS templates.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select
from typing import List
from datetime import datetime
from jinja2 import Template as JinjaTemplate

from app.database import get_session
from app.models import SmsTemplate, Customer, User
from app.auth import get_current_user
from app.schemas import (
    SmsTemplateCreate,
    SmsTemplateUpdate,
    SmsTemplateResponse,
    SmsTemplatePreviewRequest,
    SmsTemplatePreviewResponse,
)
from app.sms_template_service import render_sms_template, get_sample_customer_data

router = APIRouter(prefix="/api/sms-templates", tags=["sms-templates"])


@router.get("", response_model=List[SmsTemplateResponse])
async def get_sms_templates(
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """Get all SMS templates."""
    statement = (
        select(SmsTemplate, User)
        .outerjoin(User, SmsTemplate.created_by_id == User.id)
        .order_by(SmsTemplate.created_at.desc())
    )
    results = session.exec(statement).all()
    return [
        SmsTemplateResponse(
            id=t.id,
            name=t.name,
            description=t.description,
            body_template=t.body_template,
            is_default=t.is_default,
            created_by_id=t.created_by_id,
            created_at=t.created_at,
            updated_at=t.updated_at,
            created_by_name=u.full_name if u else None,
        )
        for t, u in results
    ]


@router.get("/{template_id}", response_model=SmsTemplateResponse)
async def get_sms_template(
    template_id: int,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """Get a single SMS template by ID."""
    statement = (
        select(SmsTemplate, User)
        .outerjoin(User, SmsTemplate.created_by_id == User.id)
        .where(SmsTemplate.id == template_id)
    )
    result = session.exec(statement).first()
    if not result:
        raise HTTPException(status_code=404, detail="SMS template not found")
    t, u = result
    return SmsTemplateResponse(
        id=t.id,
        name=t.name,
        description=t.description,
        body_template=t.body_template,
        is_default=t.is_default,
        created_by_id=t.created_by_id,
        created_at=t.created_at,
        updated_at=t.updated_at,
        created_by_name=u.full_name if u else None,
    )


@router.post("", response_model=SmsTemplateResponse)
async def create_sms_template(
    template_data: SmsTemplateCreate,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """Create a new SMS template."""
    if template_data.is_default:
        statement = select(SmsTemplate).where(SmsTemplate.is_default == True)
        for existing in session.exec(statement).all():
            existing.is_default = False
            session.add(existing)
    template = SmsTemplate(
        name=template_data.name,
        description=template_data.description,
        body_template=template_data.body_template,
        is_default=template_data.is_default or False,
        created_by_id=current_user.id,
    )
    session.add(template)
    session.commit()
    session.refresh(template)
    return SmsTemplateResponse(
        id=template.id,
        name=template.name,
        description=template.description,
        body_template=template.body_template,
        is_default=template.is_default,
        created_by_id=template.created_by_id,
        created_at=template.created_at,
        updated_at=template.updated_at,
        created_by_name=current_user.full_name,
    )


@router.put("/{template_id}", response_model=SmsTemplateResponse)
async def update_sms_template(
    template_id: int,
    template_data: SmsTemplateUpdate,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """Update an SMS template."""
    template = session.get(SmsTemplate, template_id)
    if not template:
        raise HTTPException(status_code=404, detail="SMS template not found")
    if template_data.name is not None:
        template.name = template_data.name
    if template_data.description is not None:
        template.description = template_data.description
    if template_data.body_template is not None:
        template.body_template = template_data.body_template
    if template_data.is_default is not None:
        if template_data.is_default:
            statement = select(SmsTemplate).where(
                SmsTemplate.is_default == True,
                SmsTemplate.id != template_id,
            )
            for existing in session.exec(statement).all():
                existing.is_default = False
                session.add(existing)
        template.is_default = template_data.is_default
    template.updated_at = datetime.utcnow()
    session.add(template)
    session.commit()
    session.refresh(template)
    user = session.get(User, template.created_by_id)
    return SmsTemplateResponse(
        id=template.id,
        name=template.name,
        description=template.description,
        body_template=template.body_template,
        is_default=template.is_default,
        created_by_id=template.created_by_id,
        created_at=template.created_at,
        updated_at=template.updated_at,
        created_by_name=user.full_name if user else None,
    )


@router.delete("/{template_id}")
async def delete_sms_template(
    template_id: int,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """Delete an SMS template."""
    template = session.get(SmsTemplate, template_id)
    if not template:
        raise HTTPException(status_code=404, detail="SMS template not found")
    session.delete(template)
    session.commit()
    return {"message": "SMS template deleted successfully"}


@router.post("/{template_id}/preview", response_model=SmsTemplatePreviewResponse)
async def preview_sms_template(
    template_id: int,
    preview_data: SmsTemplatePreviewRequest,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """Preview an SMS template with customer or sample data."""
    template = session.get(SmsTemplate, template_id)
    if not template:
        raise HTTPException(status_code=404, detail="SMS template not found")
    if preview_data.customer_id:
        customer = session.get(Customer, preview_data.customer_id)
        if not customer:
            raise HTTPException(status_code=404, detail="Customer not found")
        body = render_sms_template(template, customer)
    else:
        sample_data = get_sample_customer_data()
        body = JinjaTemplate(template.body_template).render(**sample_data)
    return SmsTemplatePreviewResponse(body=body)
