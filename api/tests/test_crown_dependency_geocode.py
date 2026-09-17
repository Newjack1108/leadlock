"""Crown Dependency postcode fallback when postcodes.io returns null coords."""
from unittest.mock import MagicMock, patch

from app.distance_service import (
    _crown_dependency_fallback_coords,
    bulk_geocode_postcodes,
    get_postcode_coordinates,
)


def test_isle_of_man_outcode_centroids():
    assert _crown_dependency_fallback_coords("IM1 1AD") == (54.1508, -4.4839)
    assert _crown_dependency_fallback_coords("im9 2ab") == (54.0833, -4.6500)
    assert _crown_dependency_fallback_coords("IM86 1AA") == (54.1508, -4.4839)


def test_mainland_has_no_crown_fallback():
    assert _crown_dependency_fallback_coords("CW5 5AA") is None
    assert _crown_dependency_fallback_coords("") is None


def test_get_postcode_coordinates_uses_fallback_when_lat_lng_null():
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "result": {
            "postcode": "IM1 1AD",
            "latitude": None,
            "longitude": None,
        }
    }
    with patch("app.distance_service.httpx.Client") as client_cls:
        client_cls.return_value.__enter__.return_value.get.return_value = mock_resp
        lat, lng = get_postcode_coordinates("IM1 1AD")
    assert (lat, lng) == (54.1508, -4.4839)


def test_bulk_geocode_fills_isle_of_man_when_api_returns_null():
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "result": [
            {"query": "IM1 1AD", "result": {"latitude": None, "longitude": None}},
            {"query": "CW5 5AA", "result": {"latitude": 53.06, "longitude": -2.52}},
        ]
    }
    with patch("app.distance_service.httpx.Client") as client_cls:
        client_cls.return_value.__enter__.return_value.post.return_value = mock_resp
        results = bulk_geocode_postcodes(["IM1 1AD", "CW5 5AA"])
    assert results[0] == (54.1508, -4.4839)
    assert results[1] == (53.06, -2.52)
