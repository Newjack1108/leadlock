"""Tests for order route distance / travel resolution."""
from decimal import Decimal

from app.order_route_metrics import resolve_order_route_metrics


def test_uses_stored_distance():
    dist, travel = resolve_order_route_metrics(
        factory_postcode="CW1 1AA",
        customer_postcode="CH1 1AA",
        distance_miles_one_way=Decimal("42.5"),
        travel_time_hours_one_way=None,
        average_speed_mph=Decimal("45"),
    )
    assert dist == 42.5
    assert travel == round(42.5 / 45, 4)


def test_derives_distance_from_travel_when_no_postcode_lookup_needed():
    dist, travel = resolve_order_route_metrics(
        factory_postcode="",
        customer_postcode="",
        distance_miles_one_way=None,
        travel_time_hours_one_way=Decimal("1.5"),
        average_speed_mph=Decimal("40"),
    )
    assert travel == 1.5
    assert dist == 60.0
