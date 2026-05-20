"""Tests for delivery-only trailer trip scaling."""
from decimal import Decimal
from unittest.mock import patch

import pytest

from app.delivery_install_service import (
    compute_delivery_install_estimate,
    delivery_only_trip_count,
)


@pytest.mark.parametrize(
    "boxes,expected",
    [
        (None, 1),
        (0, 1),
        (1, 1),
        (3, 1),
        (4, 2),
        (6, 2),
        (7, 3),
    ],
)
def test_delivery_only_trip_count(boxes, expected):
    assert delivery_only_trip_count(boxes) == expected


@patch("app.delivery_install_service.get_road_distance_and_duration", return_value=(50.0, 1.0))
@patch("app.delivery_install_service.get_postcode_coordinates", return_value=(0.0, 0.0))
def test_delivery_only_single_trip_for_three_boxes(_coords, _road):
    est = compute_delivery_install_estimate(
        factory_postcode="SW1A 1AA",
        customer_postcode="M1 1AA",
        installation_hours=0.0,
        cost_per_mile=Decimal("1.00"),
        hourly_install_rate=Decimal("50.00"),
        delivery_only=True,
        number_of_boxes=3,
    )
    assert est.delivery_trips == 1
    assert est.cost_total == Decimal("195.00")  # (100 mileage + 50 labour) * 1.3 margin


@patch("app.delivery_install_service.get_road_distance_and_duration", return_value=(50.0, 1.0))
@patch("app.delivery_install_service.get_postcode_coordinates", return_value=(0.0, 0.0))
def test_delivery_only_doubles_cost_for_four_boxes(_coords, _road):
    est_one = compute_delivery_install_estimate(
        factory_postcode="SW1A 1AA",
        customer_postcode="M1 1AA",
        installation_hours=0.0,
        cost_per_mile=Decimal("1.00"),
        hourly_install_rate=Decimal("50.00"),
        delivery_only=True,
        number_of_boxes=3,
    )
    est_two = compute_delivery_install_estimate(
        factory_postcode="SW1A 1AA",
        customer_postcode="M1 1AA",
        installation_hours=0.0,
        cost_per_mile=Decimal("1.00"),
        hourly_install_rate=Decimal("50.00"),
        delivery_only=True,
        number_of_boxes=4,
    )
    assert est_two.delivery_trips == 2
    assert est_two.cost_total == est_one.cost_total * 2


@patch("app.delivery_install_service.get_road_distance_and_duration", return_value=(50.0, 1.0))
@patch("app.delivery_install_service.get_postcode_coordinates", return_value=(0.0, 0.0))
def test_full_install_ignores_box_count(_coords, _road):
    est = compute_delivery_install_estimate(
        factory_postcode="SW1A 1AA",
        customer_postcode="M1 1AA",
        installation_hours=8.0,
        cost_per_mile=Decimal("1.00"),
        hourly_install_rate=Decimal("50.00"),
        delivery_only=False,
        number_of_boxes=10,
    )
    assert est.delivery_trips == 1
    assert est.delivery_only is False
