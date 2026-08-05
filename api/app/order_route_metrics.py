"""Resolve one-way distance / travel time for an order (for production payload)."""
from __future__ import annotations

import logging
from decimal import Decimal
from typing import Optional, Tuple

from sqlmodel import Session, select

from app.delivery_install_service import compute_delivery_install_estimate
from app.models import CompanySettings

logger = logging.getLogger(__name__)


def _positive_float(value) -> Optional[float]:
    if value is None:
        return None
    try:
        n = float(value)
    except (TypeError, ValueError):
        return None
    return n if n > 0 else None


def resolve_order_route_metrics(
    *,
    factory_postcode: Optional[str],
    customer_postcode: Optional[str],
    travel_time_hours_one_way: Optional[Decimal] = None,
    distance_miles_one_way: Optional[Decimal] = None,
    average_speed_mph: Optional[Decimal] = None,
    session: Optional[Session] = None,
) -> Tuple[Optional[float], Optional[float]]:
    """
    Return (distance_miles_one_way, travel_time_hours_one_way).

    Preference:
    1) Stored distance (+ travel if present, else derived from speed)
    2) Live road/haversine estimate from factory + customer postcodes
    3) Stored travel time × average speed → distance
    """
    dist = _positive_float(distance_miles_one_way)
    travel = _positive_float(travel_time_hours_one_way)
    speed = _positive_float(average_speed_mph)
    if speed is None and session is not None:
        settings = session.exec(select(CompanySettings).limit(1)).first()
        if settings is not None:
            speed = _positive_float(getattr(settings, "average_speed_mph", None))
            if not (factory_postcode or "").strip():
                factory_postcode = getattr(settings, "postcode", None)
    if speed is None:
        speed = 45.0

    if dist is not None:
        if travel is None:
            travel = dist / speed
        return round(dist, 2), round(travel, 4)

    factory = (factory_postcode or "").strip()
    customer = (customer_postcode or "").strip()
    if factory and customer:
        try:
            estimate = compute_delivery_install_estimate(
                factory_postcode=factory,
                customer_postcode=customer,
                installation_hours=0,
                average_speed_mph=Decimal(str(speed)),
                delivery_only=True,
            )
            est_dist = _positive_float(estimate.distance_miles)
            est_travel = _positive_float(estimate.travel_time_hours_one_way)
            if est_dist is not None:
                return round(est_dist, 2), round(est_travel or (est_dist / speed), 4)
        except Exception:
            logger.exception(
                "Failed to resolve delivery distance for %s -> %s",
                factory,
                customer,
            )

    if travel is not None:
        return round(travel * speed, 2), round(travel, 4)

    return None, None
