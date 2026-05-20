from fastapi import APIRouter, Depends
from sqlmodel import Session, select

from app.auth import require_configurator_access
from app.configurator_service import build_configurator_preview
from app.database import get_session
from app.models import ConfiguratorConnectionProfile, ConfiguratorFrontFace, Product, ProductCategory, User
from app.schemas import (
    ConfiguratorAccessResponse,
    ConfiguratorCatalogResponse,
    ConfiguratorPreviewRequest,
    ConfiguratorPreviewResponse,
    ProductResponse,
)

router = APIRouter(prefix="/api/configurator", tags=["configurator"])


def _build_product_response(product: Product) -> ProductResponse:
    payload = {
        **product.dict(),
        "configurator_front_face": (
            ConfiguratorFrontFace(product.configurator_front_face)
            if isinstance(product.configurator_front_face, str) and product.configurator_front_face
            else product.configurator_front_face
        ),
        "configurator_connection_profile": (
            ConfiguratorConnectionProfile(product.configurator_connection_profile)
            if isinstance(product.configurator_connection_profile, str) and product.configurator_connection_profile
            else product.configurator_connection_profile
        ),
        "is_production_synced": product.production_product_id is not None,
        "optional_extras": None,
    }
    return ProductResponse(**payload)


@router.get("/access", response_model=ConfiguratorAccessResponse)
async def get_configurator_access_status(
    current_user: User = Depends(require_configurator_access),
):
    del current_user  # access guard only
    return ConfiguratorAccessResponse(
        enabled=True,
        mode="env-allowlist",
    )


@router.get("/catalog", response_model=ConfiguratorCatalogResponse)
async def get_configurator_catalog(
    session: Session = Depends(get_session),
    current_user: User = Depends(require_configurator_access),
):
    del current_user
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
    return ConfiguratorCatalogResponse(
        items=[_build_product_response(product) for product in items],
        extras=[_build_product_response(product) for product in extras],
    )


@router.post("/preview", response_model=ConfiguratorPreviewResponse)
async def preview_configurator_configuration(
    body: ConfiguratorPreviewRequest,
    session: Session = Depends(get_session),
    current_user: User = Depends(require_configurator_access),
):
    del current_user
    return build_configurator_preview(
        body.configuration,
        session,
        customer_postcode=body.customer_postcode,
    )
