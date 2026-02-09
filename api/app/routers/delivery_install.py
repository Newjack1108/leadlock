from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from app.database import get_session
from app.models import CompanySettings, User
from app.auth import get_current_user
from app.schemas import (
    DeliveryInstallEstimateRequest,
    DeliveryInstallEstimateResponse,
)
from app.delivery_install_service import compute_delivery_install_estimate

router = APIRouter(prefix="/api/delivery-install", tags=["delivery-install"])


@router.post("/estimate", response_model=DeliveryInstallEstimateResponse)
async def estimate_delivery_install(
    body: DeliveryInstallEstimateRequest,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """
    Estimate delivery & installation: distance from factory, travel time, fitting days,
    overnight stay, and cost breakdown (mileage, labour, hotel, meals). Auth required.
    """
    settings = session.exec(select(CompanySettings).limit(1)).first()
    if not settings:
        raise HTTPException(
            status_code=400,
            detail="Configure factory postcode and installation & travel settings in Company settings.",
        )
    factory_postcode = (settings.postcode or "").strip()
    if not factory_postcode:
        raise HTTPException(
            status_code=400,
            detail="Configure factory postcode and installation & travel settings in Company settings.",
        )
    try:
        return compute_delivery_install_estimate(
            factory_postcode=factory_postcode,
            customer_postcode=body.customer_postcode,
            installation_hours=body.installation_hours,
            distance_before_overnight_miles=settings.distance_before_overnight_miles,
            cost_per_mile=settings.cost_per_mile,
            hourly_install_rate=settings.hourly_install_rate,
            hotel_allowance_per_night=settings.hotel_allowance_per_night,
            meal_allowance_per_day=settings.meal_allowance_per_day,
            average_speed_mph=settings.average_speed_mph,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
