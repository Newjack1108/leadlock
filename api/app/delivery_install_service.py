"""
Delivery & installation estimate: distance from factory, travel time, 8hr fitting days,
overnight threshold, and cost breakdown (mileage, labour, hotel, meals) for a 2-man team.
"""
import math
from decimal import Decimal
from typing import Optional

from app.distance_service import get_postcode_coordinates, haversine_miles
from app.schemas import DeliveryInstallEstimateResponse


def compute_delivery_install_estimate(
    factory_postcode: str,
    customer_postcode: str,
    installation_hours: float,
    distance_before_overnight_miles: Optional[Decimal] = None,
    cost_per_mile: Optional[Decimal] = None,
    hourly_install_rate: Optional[Decimal] = None,
    hotel_allowance_per_night: Optional[Decimal] = None,
    meal_allowance_per_day: Optional[Decimal] = None,
    average_speed_mph: Optional[Decimal] = None,
) -> DeliveryInstallEstimateResponse:
    """
    Compute distance, travel time, fitting days, overnight stay, and cost breakdown.
    Uses company postcode as factory; all monetary/rate settings optional.
    """
    lat1, lon1 = get_postcode_coordinates(factory_postcode)
    lat2, lon2 = get_postcode_coordinates(customer_postcode)
    distance_miles = haversine_miles(lat1, lon1, lat2, lon2)

    speed = float(average_speed_mph) if average_speed_mph is not None and average_speed_mph > 0 else 45.0
    travel_time_hours_one_way = distance_miles / speed

    fitting_days = max(1, math.ceil(installation_hours / 8))
    threshold = float(distance_before_overnight_miles) if distance_before_overnight_miles is not None else None
    requires_overnight = threshold is not None and distance_miles > threshold
    nights_away = (fitting_days - 1) if requires_overnight else 0

    def _dec(v: Optional[Decimal]) -> Decimal:
        return v if v is not None else Decimal("0")

    cost_mileage: Optional[Decimal] = None
    if cost_per_mile is not None and cost_per_mile > 0:
        cost_mileage = cost_per_mile * Decimal(str(distance_miles)) * 2  # return trip

    cost_labour: Optional[Decimal] = None
    if hourly_install_rate is not None and hourly_install_rate > 0:
        cost_labour = hourly_install_rate * Decimal(str(installation_hours))

    cost_hotel: Optional[Decimal] = None
    if hotel_allowance_per_night is not None and hotel_allowance_per_night > 0 and nights_away > 0:
        cost_hotel = hotel_allowance_per_night * 2 * nights_away  # 2 men

    cost_meals: Optional[Decimal] = None
    if meal_allowance_per_day is not None and meal_allowance_per_day > 0 and requires_overnight:
        cost_meals = meal_allowance_per_day * 2 * max(fitting_days, 1)  # 2 men, per day away

    total = _dec(cost_mileage) + _dec(cost_labour) + _dec(cost_hotel) + _dec(cost_meals)
    settings_incomplete = (
        (distance_miles > 0 and cost_per_mile is None)
        or (installation_hours > 0 and hourly_install_rate is None)
        or (requires_overnight and (hotel_allowance_per_night is None or meal_allowance_per_day is None))
    )

    return DeliveryInstallEstimateResponse(
        distance_miles=round(distance_miles, 2),
        travel_time_hours_one_way=round(travel_time_hours_one_way, 2),
        fitting_days=fitting_days,
        requires_overnight=requires_overnight,
        nights_away=nights_away,
        cost_mileage=cost_mileage,
        cost_labour=cost_labour,
        cost_hotel=cost_hotel,
        cost_meals=cost_meals,
        cost_total=total,
        settings_incomplete=settings_incomplete,
    )
