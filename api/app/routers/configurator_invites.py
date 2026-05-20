"""Staff endpoints for minting and listing public configurator invites."""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session, select

from app.auth import get_current_user
from app.configurator_invite_service import (
    count_unread_submitted_invites,
    invite_to_response,
    mark_invite_viewed_by_staff,
    mint_staff_invite,
)
from app.database import get_session
from app.models import ConfiguratorInvite, ConfiguratorInviteStatus, Customer, User
from app.schemas import (
    ConfiguratorInviteCreateRequest,
    ConfiguratorInviteListResponse,
    ConfiguratorInviteResponse,
    ConfiguratorInviteUnreadCountResponse,
)

router = APIRouter(prefix="/api/configurator-invites", tags=["configurator-invites"])


@router.post("", response_model=ConfiguratorInviteResponse)
async def create_configurator_invite(
    body: ConfiguratorInviteCreateRequest,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    if body.customer_id and body.lead_id:
        from app.models import Lead

        lead = session.get(Lead, body.lead_id)
        if lead and lead.customer_id and lead.customer_id != body.customer_id:
            raise HTTPException(status_code=400, detail="Lead does not belong to the given customer")

    invite = mint_staff_invite(
        session,
        created_by_id=current_user.id,
        customer_id=body.customer_id,
        lead_id=body.lead_id,
        campaign_slug=body.campaign_slug,
    )
    return invite_to_response(invite, session)


@router.get("/unread-count", response_model=ConfiguratorInviteUnreadCountResponse)
async def get_unread_submitted_configurator_count(
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    del current_user
    return ConfiguratorInviteUnreadCountResponse(
        count=count_unread_submitted_invites(session)
    )


@router.get("", response_model=ConfiguratorInviteListResponse)
async def list_configurator_invites(
    status: Optional[str] = Query(None),
    assigned_to_me: bool = Query(False),
    unread_only: bool = Query(False),
    limit: int = Query(50, ge=1, le=200),
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    statement = select(ConfiguratorInvite).order_by(ConfiguratorInvite.created_at.desc())
    if status:
        try:
            status_enum = ConfiguratorInviteStatus(status)
            statement = statement.where(ConfiguratorInvite.status == status_enum)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid status filter")
    if assigned_to_me:
        statement = statement.where(
            (ConfiguratorInvite.assigned_to_id == current_user.id)
            | (ConfiguratorInvite.created_by_id == current_user.id)
        )
    if unread_only:
        statement = statement.where(
            ConfiguratorInvite.status == ConfiguratorInviteStatus.SUBMITTED,
            ConfiguratorInvite.staff_viewed_at.is_(None),
        )
    statement = statement.limit(limit)
    rows = session.exec(statement).all()
    items = [invite_to_response(row, session) for row in rows]
    return ConfiguratorInviteListResponse(items=items, total=len(items))


@router.post("/{invite_id}/mark-viewed", response_model=ConfiguratorInviteResponse)
async def mark_configurator_invite_viewed(
    invite_id: int,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    del current_user
    invite = mark_invite_viewed_by_staff(session, invite_id)
    return invite_to_response(invite, session)


@router.get("/{invite_id}", response_model=ConfiguratorInviteResponse)
async def get_configurator_invite(
    invite_id: int,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    del current_user
    invite = session.get(ConfiguratorInvite, invite_id)
    if not invite:
        raise HTTPException(status_code=404, detail="Configurator invite not found")
    return invite_to_response(invite, session)
