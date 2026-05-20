"""Public configurator invite lifecycle: mint, register, save layout, submit."""
from __future__ import annotations

import os
import secrets
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Optional, Tuple

from fastapi import HTTPException
from sqlmodel import Session, select

from app.configurator_service import build_configurator_preview, resolve_quote_customer_postcode
from app.models import (
    Activity,
    ActivityType,
    ConfiguratorInvite,
    ConfiguratorInviteStatus,
    Customer,
    Lead,
    LeadSource,
    LeadStatus,
    Quote,
    QuoteConfiguration,
    QuoteItem,
    QuoteStatus,
    StatusHistory,
    User,
    UserRole,
)
from app.routers.leads import find_or_create_customer
from app.routers.quotes import generate_quote_number
from app.schemas import (
    ConfiguratorInviteResponse,
    PublicConfiguratorContextResponse,
    PublicConfiguratorRegisterRequest,
    QuoteConfigurationPayload,
)

DRAFT_PLACEHOLDER_DESCRIPTION = "Draft — in progress"
INVITE_VALIDITY_DAYS = 30


def _frontend_base_url() -> str:
    base = (
        os.getenv("FRONTEND_URL")
        or os.getenv("PUBLIC_FRONTEND_URL")
        or os.getenv("FRONTEND_BASE_URL")
        or ""
    ).strip()
    if not base or not (base.startswith("http://") or base.startswith("https://")):
        return "https://leadlock-frontend-production.up.railway.app"
    return base.rstrip("/")


def configure_url_for_token(access_token: str) -> str:
    return f"{_frontend_base_url()}/configure/{access_token}"


def _default_expires_at() -> datetime:
    return datetime.utcnow() + timedelta(days=INVITE_VALIDITY_DAYS)


def resolve_owner_user_id(session: Session, invite: ConfiguratorInvite) -> int:
    if invite.created_by_id:
        user = session.get(User, invite.created_by_id)
        if user:
            return user.id
    env_id = os.getenv("CONFIGURATOR_PUBLIC_OWNER_USER_ID", "").strip()
    if env_id.isdigit():
        user = session.get(User, int(env_id))
        if user:
            return user.id
    director = session.exec(
        select(User).where(User.role == UserRole.DIRECTOR).order_by(User.id).limit(1)
    ).first()
    if director:
        return director.id
    any_user = session.exec(select(User).order_by(User.id).limit(1)).first()
    if not any_user:
        raise HTTPException(status_code=500, detail="No user available to own configurator records")
    return any_user.id


def _invite_is_expired(invite: ConfiguratorInvite) -> bool:
    if invite.status == ConfiguratorInviteStatus.EXPIRED:
        return True
    if invite.expires_at and invite.expires_at < datetime.utcnow():
        return True
    return False


def get_invite_by_token(session: Session, token: str) -> ConfiguratorInvite:
    invite = session.exec(
        select(ConfiguratorInvite).where(ConfiguratorInvite.access_token == token.strip())
    ).first()
    if not invite:
        raise HTTPException(status_code=404, detail="Configurator link not found")
    if _invite_is_expired(invite):
        if invite.status != ConfiguratorInviteStatus.EXPIRED:
            invite.status = ConfiguratorInviteStatus.EXPIRED
            session.add(invite)
            session.commit()
        raise HTTPException(status_code=410, detail="Configurator link has expired")
    return invite


def _create_placeholder_quote_items(quote_id: int) -> QuoteItem:
    return QuoteItem(
        quote_id=quote_id,
        description=DRAFT_PLACEHOLDER_DESCRIPTION,
        quantity=Decimal("1"),
        unit_price=Decimal("0"),
        line_total=Decimal("0"),
        discount_amount=Decimal("0"),
        final_line_total=Decimal("0"),
        sort_order=0,
        is_custom=True,
    )


def _create_draft_quote_bundle(
    session: Session,
    *,
    customer_id: int,
    lead_id: int,
    owner_user_id: int,
    notes: Optional[str] = None,
) -> Tuple[Quote, QuoteConfiguration]:
    quote_number = generate_quote_number(session)
    quote = Quote(
        customer_id=customer_id,
        lead_id=lead_id,
        quote_number=quote_number,
        version=1,
        status=QuoteStatus.DRAFT,
        subtotal=Decimal("0"),
        discount_total=Decimal("0"),
        total_amount=Decimal("0"),
        deposit_amount=Decimal("0"),
        balance_amount=Decimal("0"),
        currency="GBP",
        notes=notes,
        created_by_id=owner_user_id,
        include_spec_sheets=False,
        include_available_optional_extras=False,
    )
    session.add(quote)
    session.commit()
    session.refresh(quote)

    session.add(_create_placeholder_quote_items(quote.id))
    total_inc_vat = Decimal("0")
    quote.deposit_amount = total_inc_vat
    quote.balance_amount = total_inc_vat
    session.add(quote)

    empty_config = QuoteConfigurationPayload(schema_version=1, name=quote_number, boxes=[], extras=[])
    config_record = QuoteConfiguration(
        quote_id=quote.id,
        version=1,
        configuration_json=empty_config.model_dump(mode="json"),
        created_by_id=owner_user_id,
    )
    session.add(config_record)
    session.commit()
    session.refresh(quote)
    session.refresh(config_record)
    return quote, config_record


def invite_to_response(invite: ConfiguratorInvite, session: Session) -> ConfiguratorInviteResponse:
    customer_name = None
    if invite.customer_id:
        customer = session.get(Customer, invite.customer_id)
        if customer:
            customer_name = customer.name
    status = invite.status.value if isinstance(invite.status, ConfiguratorInviteStatus) else str(invite.status)
    return ConfiguratorInviteResponse(
        id=invite.id,
        access_token=invite.access_token,
        configure_url=configure_url_for_token(invite.access_token),
        status=status,
        quote_id=invite.quote_id,
        lead_id=invite.lead_id,
        customer_id=invite.customer_id,
        customer_name=customer_name,
        created_by_id=invite.created_by_id,
        assigned_to_id=invite.assigned_to_id,
        campaign_slug=invite.campaign_slug,
        submitted_at=invite.submitted_at,
        staff_viewed_at=invite.staff_viewed_at,
        expires_at=invite.expires_at,
        created_at=invite.created_at,
    )


def count_unread_submitted_invites(session: Session) -> int:
    rows = session.exec(
        select(ConfiguratorInvite).where(
            ConfiguratorInvite.status == ConfiguratorInviteStatus.SUBMITTED,
            ConfiguratorInvite.staff_viewed_at.is_(None),
        )
    ).all()
    return len(rows)


def mark_invite_viewed_by_staff(session: Session, invite_id: int) -> ConfiguratorInvite:
    invite = session.get(ConfiguratorInvite, invite_id)
    if not invite:
        raise HTTPException(status_code=404, detail="Configurator invite not found")
    if invite.status == ConfiguratorInviteStatus.SUBMITTED and invite.staff_viewed_at is None:
        now = datetime.utcnow()
        invite.staff_viewed_at = now
        invite.updated_at = now
        session.add(invite)
        session.commit()
        session.refresh(invite)
    return invite


def start_organic_invite(session: Session, campaign_slug: Optional[str] = None) -> ConfiguratorInvite:
    token = secrets.token_urlsafe(32)
    invite = ConfiguratorInvite(
        access_token=token,
        status=ConfiguratorInviteStatus.PENDING_DETAILS,
        campaign_slug=(campaign_slug or "configure").strip() or "configure",
        expires_at=_default_expires_at(),
    )
    session.add(invite)
    session.commit()
    session.refresh(invite)
    return invite


def _ensure_lead_for_customer(
    session: Session,
    customer: Customer,
    *,
    assigned_to_id: Optional[int],
    owner_user_id: int,
) -> Lead:
    existing = session.exec(
        select(Lead)
        .where(Lead.customer_id == customer.id)
        .order_by(Lead.created_at.desc())
        .limit(1)
    ).first()
    if existing:
        return existing

    lead = Lead(
        name=customer.name,
        email=customer.email,
        phone=customer.phone,
        postcode=customer.postcode,
        status=LeadStatus.QUALIFIED,
        lead_source=LeadSource.CONFIGURATOR,
        customer_id=customer.id,
        assigned_to_id=assigned_to_id,
    )
    session.add(lead)
    session.commit()
    session.refresh(lead)
    session.add(
        StatusHistory(
            lead_id=lead.id,
            new_status=lead.status,
            changed_by_id=owner_user_id,
        )
    )
    session.commit()
    return lead


def mint_staff_invite(
    session: Session,
    *,
    created_by_id: int,
    customer_id: Optional[int] = None,
    lead_id: Optional[int] = None,
    campaign_slug: Optional[str] = None,
) -> ConfiguratorInvite:
    token = secrets.token_urlsafe(32)
    invite = ConfiguratorInvite(
        access_token=token,
        status=ConfiguratorInviteStatus.PENDING_DETAILS,
        created_by_id=created_by_id,
        assigned_to_id=created_by_id,
        campaign_slug=campaign_slug,
        expires_at=_default_expires_at(),
    )

    if lead_id:
        lead = session.get(Lead, lead_id)
        if not lead:
            raise HTTPException(status_code=404, detail="Lead not found")
        invite.lead_id = lead.id
        if lead.customer_id:
            invite.customer_id = lead.customer_id
            customer = session.get(Customer, lead.customer_id)
            if customer:
                quote, _ = _create_draft_quote_bundle(
                    session,
                    customer_id=customer.id,
                    lead_id=lead.id,
                    owner_user_id=created_by_id,
                )
                invite.quote_id = quote.id
                invite.status = ConfiguratorInviteStatus.ACTIVE
        elif customer_id:
            raise HTTPException(status_code=400, detail="Lead has no customer; provide customer_id")

    elif customer_id:
        customer = session.get(Customer, customer_id)
        if not customer:
            raise HTTPException(status_code=404, detail="Customer not found")
        invite.customer_id = customer.id
        lead = _ensure_lead_for_customer(
            session, customer, assigned_to_id=created_by_id, owner_user_id=created_by_id
        )
        invite.lead_id = lead.id
        quote, _ = _create_draft_quote_bundle(
            session,
            customer_id=customer.id,
            lead_id=lead.id,
            owner_user_id=created_by_id,
        )
        invite.quote_id = quote.id
        invite.status = ConfiguratorInviteStatus.ACTIVE

    session.add(invite)
    session.commit()
    session.refresh(invite)
    return invite


def register_invite_customer(
    session: Session,
    invite: ConfiguratorInvite,
    body: PublicConfiguratorRegisterRequest,
) -> ConfiguratorInvite:
    if invite.status not in (
        ConfiguratorInviteStatus.PENDING_DETAILS,
        ConfiguratorInviteStatus.ACTIVE,
    ):
        raise HTTPException(status_code=400, detail="Registration is not available for this link")
    if invite.quote_id and invite.status == ConfiguratorInviteStatus.ACTIVE:
        return invite

    owner_user_id = resolve_owner_user_id(session, invite)
    assigned_to_id = invite.assigned_to_id or invite.created_by_id

    lead = Lead(
        name=body.name.strip(),
        email=(body.email or "").strip() or None,
        phone=(body.phone or "").strip() or None,
        postcode=(body.postcode or "").strip() or None,
        status=LeadStatus.QUALIFIED,
        lead_source=LeadSource.CONFIGURATOR,
        assigned_to_id=assigned_to_id,
        description="Customer self-service configurator",
    )
    session.add(lead)
    session.commit()
    session.refresh(lead)

    customer = find_or_create_customer(lead, session)
    lead.customer_id = customer.id
    session.add(lead)
    session.commit()
    session.refresh(lead)

    from app.workflow import auto_create_opportunity

    try:
        auto_create_opportunity(customer.id, lead.id, session, owner_user_id)
    except Exception:
        pass

    session.add(
        StatusHistory(
            lead_id=lead.id,
            new_status=lead.status,
            changed_by_id=owner_user_id,
        )
    )

    quote, _ = _create_draft_quote_bundle(
        session,
        customer_id=customer.id,
        lead_id=lead.id,
        owner_user_id=owner_user_id,
        notes="Customer layout in progress (public configurator).",
    )

    invite.lead_id = lead.id
    invite.customer_id = customer.id
    invite.quote_id = quote.id
    invite.status = ConfiguratorInviteStatus.ACTIVE
    invite.updated_at = datetime.utcnow()
    session.add(invite)
    session.commit()
    session.refresh(invite)
    return invite


def build_public_context(session: Session, invite: ConfiguratorInvite) -> PublicConfiguratorContextResponse:
    status = invite.status.value if isinstance(invite.status, ConfiguratorInviteStatus) else str(invite.status)
    customer_name = None
    customer_postcode = None
    configuration = None

    if invite.customer_id:
        customer = session.get(Customer, invite.customer_id)
        if customer:
            customer_name = customer.name
            customer_postcode = customer.postcode

    if invite.quote_id and invite.status in (
        ConfiguratorInviteStatus.ACTIVE,
        ConfiguratorInviteStatus.SUBMITTED,
    ):
        record = session.exec(
            select(QuoteConfiguration).where(QuoteConfiguration.quote_id == invite.quote_id)
        ).first()
        if record:
            configuration = QuoteConfigurationPayload.model_validate(record.configuration_json or {})

    return PublicConfiguratorContextResponse(
        status=status,
        customer_name=customer_name,
        quote_id=invite.quote_id,
        lead_id=invite.lead_id,
        submitted_at=invite.submitted_at,
        configuration=configuration,
        customer_postcode=customer_postcode,
    )


def save_invite_configuration(
    session: Session,
    invite: ConfiguratorInvite,
    payload: QuoteConfigurationPayload,
) -> QuoteConfiguration:
    if invite.status != ConfiguratorInviteStatus.ACTIVE:
        raise HTTPException(status_code=400, detail="Layout can only be saved while the session is active")
    if not invite.quote_id:
        raise HTTPException(status_code=400, detail="No quote linked to this configurator session")

    quote = session.get(Quote, invite.quote_id)
    if not quote or quote.status != QuoteStatus.DRAFT:
        raise HTTPException(status_code=400, detail="Quote is not editable")

    record = session.exec(
        select(QuoteConfiguration).where(QuoteConfiguration.quote_id == invite.quote_id)
    ).first()
    if record:
        record.version += 1
        record.configuration_json = payload.model_dump(mode="json")
        record.updated_at = datetime.utcnow()
    else:
        owner_user_id = resolve_owner_user_id(session, invite)
        record = QuoteConfiguration(
            quote_id=invite.quote_id,
            version=1,
            configuration_json=payload.model_dump(mode="json"),
            created_by_id=owner_user_id,
        )
    session.add(record)
    invite.updated_at = datetime.utcnow()
    session.add(invite)
    session.commit()
    session.refresh(record)
    return record


def submit_invite_layout(session: Session, invite: ConfiguratorInvite) -> ConfiguratorInvite:
    if invite.status != ConfiguratorInviteStatus.ACTIVE:
        raise HTTPException(status_code=400, detail="Layout has already been submitted or is not ready")
    if not invite.quote_id:
        raise HTTPException(status_code=400, detail="No layout to submit")

    quote = session.get(Quote, invite.quote_id)
    if not quote:
        raise HTTPException(status_code=404, detail="Quote not found")

    record = session.exec(
        select(QuoteConfiguration).where(QuoteConfiguration.quote_id == invite.quote_id)
    ).first()
    if not record:
        raise HTTPException(status_code=400, detail="Save your layout before submitting")

    payload = QuoteConfigurationPayload.model_validate(record.configuration_json or {})
    preview = build_configurator_preview(
        payload,
        session,
        customer_postcode=resolve_quote_customer_postcode(quote, session),
    )
    if not preview.valid:
        raise HTTPException(
            status_code=422,
            detail={
                "message": "Layout has validation errors",
                "issues": [issue.model_dump(mode="json") for issue in preview.issues],
            },
        )
    if not preview.items:
        raise HTTPException(status_code=422, detail="Add at least one item to your layout before submitting")

    now = datetime.utcnow()
    invite.status = ConfiguratorInviteStatus.SUBMITTED
    invite.submitted_at = now
    invite.updated_at = now

    note_line = f"Customer submitted configurator layout on {now.strftime('%Y-%m-%d %H:%M')} UTC."
    if quote.notes:
        quote.notes = f"{quote.notes.strip()}\n\n{note_line}"
    else:
        quote.notes = note_line
    quote.updated_at = now
    session.add(quote)

    owner_user_id = resolve_owner_user_id(session, invite)
    if invite.lead_id:
        activity = Activity(
            customer_id=invite.customer_id,
            lead_id=invite.lead_id,
            activity_type=ActivityType.NOTE,
            notes=f"Customer submitted configurator layout for quote {quote.quote_number}.",
            created_by_id=owner_user_id,
        )
        session.add(activity)

    session.add(invite)
    session.commit()
    session.refresh(invite)
    return invite
