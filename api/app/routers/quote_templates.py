"""
Quote template router for managing quote email templates.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select
from typing import List, Optional
from jinja2 import Template
from app.database import get_session
from app.models import (
    QuoteTemplate,
    QuoteTemplateSalesDocument,
    SalesDocument,
    Quote,
    Customer,
    CompanySettings,
    User,
)
from app.auth import get_current_user
from app.schemas import (
    QuoteTemplateCreate,
    QuoteTemplateUpdate,
    QuoteTemplateResponse,
    QuoteTemplateAttachedDocument,
    QuoteTemplatePreviewRequest,
    QuoteTemplatePreviewResponse,
)
from app.quote_email_service import get_sample_quote_preview_data

router = APIRouter(prefix="/api/quote-templates", tags=["quote-templates"])


def _dedupe_sales_document_ids(ids: List[int]) -> List[int]:
    seen = set()
    out: List[int] = []
    for i in ids:
        if i not in seen:
            seen.add(i)
            out.append(i)
    return out


def _fetch_attached_documents(
    session: Session, template_id: int
) -> List[QuoteTemplateAttachedDocument]:
    statement = (
        select(QuoteTemplateSalesDocument, SalesDocument)
        .join(SalesDocument, QuoteTemplateSalesDocument.sales_document_id == SalesDocument.id)
        .where(QuoteTemplateSalesDocument.quote_template_id == template_id)
        .order_by(QuoteTemplateSalesDocument.sort_order)
    )
    rows = session.exec(statement).all()
    return [
        QuoteTemplateAttachedDocument(
            id=doc.id,
            name=doc.name,
            filename=doc.filename,
            sort_order=link.sort_order,
        )
        for link, doc in rows
    ]


def _set_template_sales_documents(
    session: Session,
    template_id: int,
    sales_document_ids: List[int],
) -> None:
    ids = _dedupe_sales_document_ids(sales_document_ids)
    for sid in ids:
        if session.get(SalesDocument, sid) is None:
            raise HTTPException(
                status_code=400,
                detail=f"Sales document not found (id={sid})",
            )
    existing = session.exec(
        select(QuoteTemplateSalesDocument).where(
            QuoteTemplateSalesDocument.quote_template_id == template_id
        )
    ).all()
    for row in existing:
        session.delete(row)
    for order, sid in enumerate(ids):
        session.add(
            QuoteTemplateSalesDocument(
                quote_template_id=template_id,
                sales_document_id=sid,
                sort_order=order,
            )
        )


def _quote_template_response(
    session: Session,
    template: QuoteTemplate,
    created_by_name: Optional[str],
) -> QuoteTemplateResponse:
    return QuoteTemplateResponse(
        id=template.id,
        name=template.name,
        description=template.description,
        email_subject_template=template.email_subject_template,
        email_body_template=template.email_body_template,
        is_default=template.is_default,
        created_by_id=template.created_by_id,
        created_at=template.created_at,
        created_by_name=created_by_name,
        attached_documents=_fetch_attached_documents(session, template.id),
    )


@router.get("", response_model=List[QuoteTemplateResponse])
async def get_quote_templates(
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """Get all quote templates."""
    statement = select(QuoteTemplate, User).outerjoin(
        User, QuoteTemplate.created_by_id == User.id
    ).order_by(QuoteTemplate.created_at.desc())

    results = session.exec(statement).all()
    templates = []

    for template, user in results:
        templates.append(
            _quote_template_response(
                session,
                template,
                user.full_name if user else None,
            )
        )

    return templates


@router.get("/{template_id}", response_model=QuoteTemplateResponse)
async def get_quote_template(
    template_id: int,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """Get a single quote template by ID."""
    statement = select(QuoteTemplate, User).outerjoin(
        User, QuoteTemplate.created_by_id == User.id
    ).where(QuoteTemplate.id == template_id)

    result = session.exec(statement).first()

    if not result:
        raise HTTPException(status_code=404, detail="Quote template not found")

    template, user = result

    return _quote_template_response(
        session,
        template,
        user.full_name if user else None,
    )


@router.post("", response_model=QuoteTemplateResponse)
async def create_quote_template(
    template_data: QuoteTemplateCreate,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """Create a new quote template."""
    if template_data.is_default:
        statement = select(QuoteTemplate).where(QuoteTemplate.is_default == True)
        existing_defaults = session.exec(statement).all()
        for default_template in existing_defaults:
            default_template.is_default = False
            session.add(default_template)

    template = QuoteTemplate(
        name=template_data.name,
        description=template_data.description,
        email_subject_template=template_data.email_subject_template,
        email_body_template=template_data.email_body_template,
        is_default=template_data.is_default or False,
        created_by_id=current_user.id
    )

    session.add(template)
    session.flush()
    if template_data.sales_document_ids is not None:
        _set_template_sales_documents(session, template.id, template_data.sales_document_ids)
    session.commit()
    session.refresh(template)

    return _quote_template_response(session, template, current_user.full_name)


@router.put("/{template_id}", response_model=QuoteTemplateResponse)
async def update_quote_template(
    template_id: int,
    template_data: QuoteTemplateUpdate,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """Update a quote template."""
    statement = select(QuoteTemplate).where(QuoteTemplate.id == template_id)
    template = session.exec(statement).first()

    if not template:
        raise HTTPException(status_code=404, detail="Quote template not found")

    if template_data.name is not None:
        template.name = template_data.name
    if template_data.description is not None:
        template.description = template_data.description
    if template_data.email_subject_template is not None:
        template.email_subject_template = template_data.email_subject_template
    if template_data.email_body_template is not None:
        template.email_body_template = template_data.email_body_template
    if template_data.is_default is not None:
        if template_data.is_default:
            statement = select(QuoteTemplate).where(
                QuoteTemplate.is_default == True,
                QuoteTemplate.id != template_id
            )
            existing_defaults = session.exec(statement).all()
            for default_template in existing_defaults:
                default_template.is_default = False
                session.add(default_template)
        template.is_default = template_data.is_default

    if template_data.sales_document_ids is not None:
        _set_template_sales_documents(session, template.id, template_data.sales_document_ids)

    session.add(template)
    session.commit()
    session.refresh(template)

    statement = select(User).where(User.id == template.created_by_id)
    user = session.exec(statement).first()

    return _quote_template_response(
        session,
        template,
        user.full_name if user else None,
    )


@router.delete("/{template_id}")
async def delete_quote_template(
    template_id: int,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """Delete a quote template."""
    statement = select(QuoteTemplate).where(QuoteTemplate.id == template_id)
    template = session.exec(statement).first()

    if not template:
        raise HTTPException(status_code=404, detail="Quote template not found")

    session.delete(template)
    session.commit()

    return {"message": "Quote template deleted successfully"}


@router.post("/{template_id}/preview", response_model=QuoteTemplatePreviewResponse)
async def preview_quote_template(
    template_id: int,
    preview_data: QuoteTemplatePreviewRequest,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """Preview a quote template with quote/customer data."""
    statement = select(QuoteTemplate).where(QuoteTemplate.id == template_id)
    template = session.exec(statement).first()

    if not template:
        raise HTTPException(status_code=404, detail="Quote template not found")

    if preview_data.quote_id:
        statement = select(Quote).where(Quote.id == preview_data.quote_id)
        quote = session.exec(statement).first()
        if not quote or not quote.customer_id:
            raise HTTPException(status_code=404, detail="Quote not found")

        customer = session.get(Customer, quote.customer_id)
        if not customer:
            raise HTTPException(status_code=404, detail="Customer not found")

        company_settings = session.exec(select(CompanySettings).limit(1)).first()
        from app.quote_email_service import render_email_template
        subject_template = Template(template.email_subject_template)
        body_template = Template(template.email_body_template)
        subject = render_email_template(subject_template, quote, customer, company_settings, "Your custom message here.")
        body_html = render_email_template(body_template, quote, customer, company_settings, "Your custom message here.")
    else:
        sample_data = get_sample_quote_preview_data()
        subject_template = Template(template.email_subject_template)
        body_template = Template(template.email_body_template)
        subject = subject_template.render(**sample_data)
        body_html = body_template.render(**sample_data)

    return QuoteTemplatePreviewResponse(
        subject=subject,
        body_html=body_html
    )
