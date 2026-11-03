"""Postcode lookup accepts codes Google geocodes but postcodes.io omits from the live set."""
from unittest.mock import MagicMock, patch

import httpx
import pytest

from app.distance_service import (
    _crown_dependency_fallback_coords,
    _normalise_postcode,
    bulk_geocode_postcodes,
    get_postcode_coordinates,
)


def _json_response(payload: dict) -> MagicMock:
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = payload
    return resp


def test_normalise_strips_spaces_punctuation_and_nbsp():
    assert _normalise_postcode(" sw1a\u00a01aa, ") == "SW1A1AA"
    assert _normalise_postcode("M1-1AE") == "M11AE"


def test_crown_fallback_ignores_punctuation():
    assert _crown_dependency_fallback_coords("im1-1ad") == (54.1508, -4.4839)


def test_empty_postcode_is_rejected():
    with pytest.raises(ValueError, match="Postcode is required"):
        get_postcode_coordinates("   ")


def test_live_postcode_uses_compact_url():
    with patch("app.distance_service.httpx.Client") as client_cls:
        client = client_cls.return_value.__enter__.return_value
        client.get.return_value = _json_response(
            {"result": {"latitude": 53.068232, "longitude": -2.521507}}
        )
        lat, lng = get_postcode_coordinates("CW5 5AA")
    assert (lat, lng) == (53.068232, -2.521507)
    assert client.get.call_args.args[0].endswith("/postcodes/CW55AA")


def test_terminated_postcode_uses_embedded_coordinates():
    with patch("app.distance_service.httpx.Client") as client_cls:
        client = client_cls.return_value.__enter__.return_value
        client.get.return_value = _json_response(
            {
                "status": 404,
                "error": "Postcode not found",
                "terminated": {
                    "postcode": "EH1 1AA",
                    "latitude": 55.953646,
                    "longitude": -3.188108,
                },
            }
        )
        lat, lng = get_postcode_coordinates("eh1-1aa")
    assert (lat, lng) == (55.953646, -3.188108)
    assert client.get.call_args.args[0].endswith("/postcodes/EH11AA")
    assert client.get.call_count == 1


def test_missing_unit_postcode_falls_back_to_outcode_centre():
    with patch("app.distance_service.httpx.Client") as client_cls:
        client = client_cls.return_value.__enter__.return_value
        client.get.side_effect = [
            _json_response({"status": 404, "error": "Postcode not found"}),
            _json_response({"result": {"outcode": "ZE1", "latitude": 60.15, "longitude": -1.17}}),
        ]
        lat, lng = get_postcode_coordinates("ZE1 1AA")
    assert (lat, lng) == (60.15, -1.17)
    urls = [call.args[0] for call in client.get.call_args_list]
    assert urls[0].endswith("/postcodes/ZE11AA")
    assert urls[1].endswith("/outcodes/ZE1")


def test_bare_outcode_is_resolved():
    with patch("app.distance_service.httpx.Client") as client_cls:
        client = client_cls.return_value.__enter__.return_value
        client.get.side_effect = [
            _json_response({"status": 404, "error": "Invalid postcode"}),
            _json_response({"result": {"latitude": 53.06, "longitude": -2.52}}),
        ]
        lat, lng = get_postcode_coordinates("cw5")
    assert (lat, lng) == (53.06, -2.52)
    urls = [call.args[0] for call in client.get.call_args_list]
    assert urls[0].endswith("/postcodes/CW5")
    assert urls[1].endswith("/outcodes/CW5")


def test_null_coordinates_use_outcode_from_the_record():
    with patch("app.distance_service.httpx.Client") as client_cls:
        client = client_cls.return_value.__enter__.return_value
        client.get.side_effect = [
            _json_response(
                {
                    "result": {
                        "postcode": "BX1 1LT",
                        "latitude": None,
                        "longitude": None,
                        "outcode": "BX1",
                    }
                }
            ),
            _json_response({"result": {"latitude": 51.5, "longitude": -0.1}}),
        ]
        lat, lng = get_postcode_coordinates("BX1 1LT")
    assert (lat, lng) == (51.5, -0.1)
    assert client.get.call_args_list[1].args[0].endswith("/outcodes/BX1")


def test_unknown_postcode_is_rejected():
    with patch("app.distance_service.httpx.Client") as client_cls:
        client = client_cls.return_value.__enter__.return_value
        client.get.side_effect = [
            _json_response({"status": 404, "error": "Postcode not found"}),
            _json_response({"status": 404, "error": "Outcode not found"}),
        ]
        with pytest.raises(ValueError, match="Postcode not found"):
            get_postcode_coordinates("ZZ99 9ZZ")


def test_non_postcode_does_not_guess_an_outcode():
    with patch("app.distance_service.httpx.Client") as client_cls:
        client = client_cls.return_value.__enter__.return_value
        client.get.return_value = _json_response({"status": 404, "error": "Invalid postcode"})
        with pytest.raises(ValueError, match="Postcode not found"):
            get_postcode_coordinates("hello")
    assert client.get.call_count == 1


def test_timeout_is_reported():
    with patch("app.distance_service.httpx.Client") as client_cls:
        client = client_cls.return_value.__enter__.return_value
        client.get.side_effect = httpx.TimeoutException("slow")
        with pytest.raises(ValueError, match="timed out"):
            get_postcode_coordinates("CW5 5AA")


def test_royal_mail_special_postcode_is_recognised():
    lat, lng = get_postcode_coordinates("GX11 1AA")
    assert (lat, lng) == (36.1408, -5.3536)
    lat, lng = get_postcode_coordinates("FIQQ 1ZZ")
    assert (lat, lng) == (-51.6977, -57.8516)


def test_bulk_does_not_fan_out_when_the_batch_fails():
    with patch("app.distance_service.httpx.Client") as client_cls:
        client = client_cls.return_value.__enter__.return_value
        failed = _json_response({})
        failed.status_code = 500
        client.post.return_value = failed
        results = bulk_geocode_postcodes(["EH1 1AA", "CW5 5AA"])
    assert results == [None, None]
    client.get.assert_not_called()


def test_bulk_fills_special_postcode_without_a_second_request():
    with patch("app.distance_service.httpx.Client") as client_cls:
        client = client_cls.return_value.__enter__.return_value
        client.post.return_value = _json_response(
            {"result": [{"query": "GX111AA", "result": None}]}
        )
        results = bulk_geocode_postcodes(["GX11 1AA"])
    assert results == [(36.1408, -5.3536)]
    client.get.assert_not_called()


def test_bulk_geocode_resolves_terminated_postcodes():
    with patch("app.distance_service.httpx.Client") as client_cls:
        client = client_cls.return_value.__enter__.return_value
        client.post.return_value = _json_response(
            {
                "result": [
                    {"query": "EH11AA", "result": None},
                    {"query": "CW55AA", "result": {"latitude": 53.06, "longitude": -2.52}},
                ]
            }
        )
        client.get.return_value = _json_response(
            {
                "error": "Postcode not found",
                "terminated": {"latitude": 55.95, "longitude": -3.19},
            }
        )
        results = bulk_geocode_postcodes(["EH1 1AA", "CW5 5AA"])
    assert results[0] == (55.95, -3.19)
    assert results[1] == (53.06, -2.52)
