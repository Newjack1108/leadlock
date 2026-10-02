"""Public configurator endpoints (no auth; token-based)."""
from fastapi import APIRouter, Depends, Request
from sqlmodel import Session, select

from app.configurator_invite_service import (
    build_public_context,
    configure_url_for_token,
    get_invite_by_token,
    invite_to_response,
    register_invite_customer,
    save_invite_configuration,
    start_organic_invite,
    submit_invite_layout,
)
from app.configurator_service import build_configurator_preview, resolve_quote_customer_postcode
from app.database import get_session
from app.models import (
    ConfiguratorConnectionProfile,
    ConfiguratorFrontFace,
    Product,
    ProductCategory,
    Quote,
)
from app.rate_limit import enforce_rate_limit
from app.schemas import (
    ConfiguratorPreviewRequest,
    ConfiguratorPreviewResponse,
    PublicConfiguratorCatalogResponse,
    PublicConfiguratorContextResponse,
    PublicConfiguratorProductResponse,
    PublicConfiguratorRegisterRequest,
    PublicConfiguratorStartRequest,
    PublicConfiguratorStartResponse,
    QuoteConfigurationPayload,
)

router = APIRouter(prefix="/api/public/configurator", tags=["public-configurator"])


def _build_public_product(product: Product) -> PublicConfiguratorProductResponse:
    return PublicConfiguratorProductResponse(
        id=product.id,
        name=product.name,
        description=product.description,
        category=product.category,
        is_extra=product.is_extra,
        base_price=product.base_price,
        unit=product.unit,
        image_url=product.image_url,
        size=product.size,
        height=product.height,
        width=product.width,
        length=product.length,
        configurator_width=product.configurator_width,
        configurator_length=product.configurator_length,
        configurator_front_face=(
            ConfiguratorFrontFace(product.configurator_front_face)
            if isinstance(product.configurator_front_face, str) and product.configurator_front_face
            else product.configurator_front_face
        ),
        configurator_connection_profile=(
            ConfiguratorConnectionProfile(product.configurator_connection_profile)
            if isinstance(product.configurator_connection_profile, str)
            and product.configurator_connection_profile
            else product.configurator_connection_profile
        ),
        configurator_is_corner_box=bool(product.configurator_is_corner_box),
        configurator_is_starter_box=bool(product.configurator_is_starter_box),
        allow_in_configurator=bool(product.allow_in_configurator),
        configurator_per_box=bool(product.configurator_per_box),
    )


def _get_public_catalog(session: Session) -> PublicConfiguratorCatalogResponse:
    items = session.exec(
        select(Product)
        .where(
            Product.is_active == True,
            Product.category == ProductCategory.CONFIGURATOR,
            Product.is_extra == False,
        )
        .order_by(Product.name)
    ).all()
    extras = session.exec(
        select(Product)
        .where(
            Product.is_active == True,
            Product.is_extra == True,
            Product.allow_in_configurator == True,
        )
        .order_by(Product.name)
    ).all()
    return PublicConfiguratorCatalogResponse(
        items=[_build_public_product(product) for product in items],
        extras=[_build_public_product(product) for product in extras],
    )


@router.post("/start", response_model=PublicConfiguratorStartResponse)
async def public_configurator_start(
    body: PublicConfiguratorStartRequest,
    request: Request,
    session: Session = Depends(get_session),
):
    enforce_rate_limit(request, scope="public-configurator-start", max_requests=30, window_seconds=60)
    invite = start_organic_invite(session, body.campaign_slug)
    status = invite.status.value if hasattr(invite.status, "value") else str(invite.status)
    return PublicConfiguratorStartResponse(
        access_token=invite.access_token,
        configure_url=configure_url_for_token(invite.access_token),
        status=status,
    )


@router.get("/catalog", response_model=PublicConfiguratorCatalogResponse)
async def public_configurator_catalog(session: Session = Depends(get_session)):
    return _get_public_catalog(session)


@router.get("/{token}", response_model=PublicConfiguratorContextResponse)
async def public_configurator_context(
    token: str,
    session: Session = Depends(get_session),
):
    invite = get_invite_by_token(session, token)
    return build_public_context(session, invite)


@router.post("/{token}/register", response_model=PublicConfiguratorContextResponse)
async def public_configurator_register(
    token: str,
    body: PublicConfiguratorRegisterRequest,
    session: Session = Depends(get_session),
):
    invite = get_invite_by_token(session, token)
    invite = register_invite_customer(session, invite, body)
    return build_public_context(session, invite)


@router.post("/{token}/preview", response_model=ConfiguratorPreviewResponse)
async def public_configurator_preview(
    token: str,
    body: ConfiguratorPreviewRequest,
    session: Session = Depends(get_session),
):
    invite = get_invite_by_token(session, token)
    postcode = body.customer_postcode
    if not postcode and invite.quote_id:
        quote = session.get(Quote, invite.quote_id)
        if quote:
            postcode = resolve_quote_customer_postcode(quote, session)
    return build_configurator_preview(body.configuration, session, customer_postcode=postcode)


@router.put("/{token}/configuration", response_model=PublicConfiguratorContextResponse)
async def public_configurator_save_configuration(
    token: str,
    payload: QuoteConfigurationPayload,
    session: Session = Depends(get_session),
):
    invite = get_invite_by_token(session, token)
    save_invite_configuration(session, invite, payload)
    session.refresh(invite)
    return build_public_context(session, invite)


@router.post("/{token}/submit", response_model=PublicConfiguratorContextResponse)
async def public_configurator_submit(
    token: str,
    session: Session = Depends(get_session),
):
    invite = get_invite_by_token(session, token)
    invite = submit_invite_layout(session, invite)
    return build_public_context(session, invite)
