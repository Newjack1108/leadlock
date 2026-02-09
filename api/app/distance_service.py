"""
UK postcode geocoding via postcodes.io and Haversine distance (straight-line miles).
Road mileage may be higher; optional future: routing API or multiplier.
"""
import math
from typing import Tuple

import httpx

POSTCODES_IO_BASE = "https://api.postcodes.io"


def _normalise_postcode(postcode: str) -> str:
    """Strip and uppercase. Returns compact form (no space) for validation."""
    return (postcode or "").strip().upper().replace(" ", "")


def _format_postcode_for_api(postcode: str) -> str:
    """Format as OUTCODE INCODE (e.g. M1 1AA) for postcodes.io URL."""
    compact = _normalise_postcode(postcode)
    if len(compact) >= 4 and compact[-3:].isdigit() is False:
        return f"{compact[:-3]} {compact[-3:]}"
    return compact


def get_postcode_coordinates(postcode: str) -> Tuple[float, float]:
    """
    Resolve UK postcode to (latitude, longitude) via postcodes.io.
    Raises ValueError if postcode invalid or not found.
    """
    if not _normalise_postcode(postcode):
        raise ValueError("Postcode is required")
    formatted = _format_postcode_for_api(postcode)
    url = f"{POSTCODES_IO_BASE}/postcodes/{formatted}"
    try:
        with httpx.Client(timeout=10.0) as client:
            resp = client.get(url)
    except httpx.TimeoutException:
        raise ValueError("Postcode lookup timed out. Please try again.")
    except httpx.RequestError as e:
        raise ValueError(f"Postcode lookup failed: {e!s}")

    if resp.status_code != 200:
        data = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {}
        if data.get("error") == "Invalid postcode":
            raise ValueError("Postcode not found")
        raise ValueError(data.get("error", "Postcode not found"))

    data = resp.json()
    result = data.get("result")
    if not result:
        raise ValueError("Postcode not found")
    lat = result.get("latitude")
    lon = result.get("longitude")
    if lat is None or lon is None:
        raise ValueError("Postcode not found")
    return (float(lat), float(lon))


def haversine_miles(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    Straight-line distance in miles between two WGS84 points.
    Road distance may be higher; optional future: routing API or multiplier.
    """
    R = 3959  # Earth radius in miles
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c
