"""
Email template router for managing email templates.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select
from typing import List
from datetime import datetime
from app.database import get_session
from app.models import EmailTemplate, Customer, User
from app.auth import get_current_user
from app.schemas import (
    EmailTemplateCreate,
    EmailTemplateUpdate,
    EmailTemplateResponse,
    EmailTemplatePreviewRequest,
    EmailTemplatePreviewResponse
)
from app.email_template_service import render_email_template, get_sample_customer_data

router = APIRouter(prefix="/api/email-templates", tags=["email-templates"])


@router.get("", response_model=List[EmailTemplateResponse])
async def get_email_templates(
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """Get all email templates."""
    statement = select(EmailTemplate, User).outerjoin(
        User, EmailTemplate.created_by_id == User.id
    ).order_by(EmailTemplate.created_at.desc())
    
    results = session.exec(statement).all()
    templates = []
    
    for template, user in results:
        templates.append(EmailTemplateResponse(
            id=template.id,
            name=template.name,
            description=template.description,
            subject_template=template.subject_template,
            body_template=template.body_template,
            is_default=template.is_default,
            created_by_id=template.created_by_id,
            created_at=template.created_at,
            updated_at=template.updated_at,
            created_by_name=user.full_name if user else None
        ))
    
    return templates


@router.get("/{template_id}", response_model=EmailTemplateResponse)
async def get_email_template(
    template_id: int,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """Get a single email template by ID."""
    statement = select(EmailTemplate, User).outerjoin(
        User, EmailTemplate.created_by_id == User.id
    ).where(EmailTemplate.id == template_id)
    
    result = session.exec(statement).first()
    
    if not result:
        raise HTTPException(status_code=404, detail="Email template not found")
    
    template, user = result
    
    return EmailTemplateResponse(
        id=template.id,
        name=template.name,
        description=template.description,
        subject_template=template.subject_template,
        body_template=template.body_template,
        is_default=template.is_default,
        created_by_id=template.created_by_id,
        created_at=template.created_at,
        updated_at=template.updated_at,
        created_by_name=user.full_name if user else None
    )


@router.post("", response_model=EmailTemplateResponse)
async def create_email_template(
    template_data: EmailTemplateCreate,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """Create a new email template."""
    # If setting as default, unset other defaults
    if template_data.is_default:
        statement = select(EmailTemplate).where(EmailTemplate.is_default == True)
        existing_defaults = session.exec(statement).all()
        for default_template in existing_defaults:
            default_template.is_default = False
            session.add(default_template)
    
    template = EmailTemplate(
        name=template_data.name,
        description=template_data.description,
        subject_template=template_data.subject_template,
        body_template=template_data.body_template,
        is_default=template_data.is_default or False,
        created_by_id=current_user.id
    )
    
    session.add(template)
    session.commit()
    session.refresh(template)
    
    return EmailTemplateResponse(
        id=template.id,
        name=template.name,
        description=template.description,
        subject_template=template.subject_template,
        body_template=template.body_template,
        is_default=template.is_default,
        created_by_id=template.created_by_id,
        created_at=template.created_at,
        updated_at=template.updated_at,
        created_by_name=current_user.full_name
    )


@router.put("/{template_id}", response_model=EmailTemplateResponse)
async def update_email_template(
    template_id: int,
    template_data: EmailTemplateUpdate,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """Update an email template."""
    statement = select(EmailTemplate).where(EmailTemplate.id == template_id)
    template = session.exec(statement).first()
    
    if not template:
        raise HTTPException(status_code=404, detail="Email template not found")
    
    # Update fields if provided
    if template_data.name is not None:
        template.name = template_data.name
    if template_data.description is not None:
        template.description = template_data.description
    if template_data.subject_template is not None:
        template.subject_template = template_data.subject_template
    if template_data.body_template is not None:
        template.body_template = template_data.body_template
    if template_data.is_default is not None:
        # If setting as default, unset other defaults
        if template_data.is_default:
            statement = select(EmailTemplate).where(
                EmailTemplate.is_default == True,
                EmailTemplate.id != template_id
            )
            existing_defaults = session.exec(statement).all()
            for default_template in existing_defaults:
                default_template.is_default = False
                session.add(default_template)
        template.is_default = template_data.is_default
    
    template.updated_at = datetime.utcnow()
    session.add(template)
    session.commit()
    session.refresh(template)
    
    # Get user for created_by_name
    statement = select(User).where(User.id == template.created_by_id)
    user = session.exec(statement).first()
    
    return EmailTemplateResponse(
        id=template.id,
        name=template.name,
        description=template.description,
        subject_template=template.subject_template,
        body_template=template.body_template,
        is_default=template.is_default,
        created_by_id=template.created_by_id,
        created_at=template.created_at,
        updated_at=template.updated_at,
        created_by_name=user.full_name if user else None
    )


@router.delete("/{template_id}")
async def delete_email_template(
    template_id: int,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """Delete an email template."""
    statement = select(EmailTemplate).where(EmailTemplate.id == template_id)
    template = session.exec(statement).first()
    
    if not template:
        raise HTTPException(status_code=404, detail="Email template not found")
    
    session.delete(template)
    session.commit()
    
    return {"message": "Email template deleted successfully"}


@router.post("/{template_id}/preview", response_model=EmailTemplatePreviewResponse)
async def preview_email_template(
    template_id: int,
    preview_data: EmailTemplatePreviewRequest,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """Preview an email template with customer data."""
    statement = select(EmailTemplate).where(EmailTemplate.id == template_id)
    template = session.exec(statement).first()
    
    if not template:
        raise HTTPException(status_code=404, detail="Email template not found")
    
    # Get customer data (real or sample)
    if preview_data.customer_id:
        statement = select(Customer).where(Customer.id == preview_data.customer_id)
        customer = session.exec(statement).first()
        if not customer:
            raise HTTPException(status_code=404, detail="Customer not found")
        
        subject, body_html = render_email_template(template, customer)
    else:
        # Use sample data
        from jinja2 import Template
        subject_template = Template(template.subject_template)
        body_template = Template(template.body_template)
        sample_data = get_sample_customer_data()
        
        subject = subject_template.render(**sample_data)
        body_html = body_template.render(**sample_data)
    
    return EmailTemplatePreviewResponse(
        subject=subject,
        body_html=body_html
    )
