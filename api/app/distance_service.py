"""
UK postcode geocoding via postcodes.io; Haversine (straight-line) and OpenRouteService (road) distance.

Crown Dependencies (Isle of Man IM*, Guernsey GY*, Jersey JE*) are recognised by
postcodes.io but often return null latitude/longitude; we fall back to outcode centroids.
"""
import math
import os
import re
from typing import List, Optional, Tuple

import httpx

POSTCODES_IO_BASE = "https://api.postcodes.io"
ORS_DIRECTIONS_BASE = "https://api.openrouteservice.org/v2/directions/driving-car"
METRES_PER_MILE = 1609.344
SECONDS_PER_HOUR = 3600.0

# Approximate outcode centroids — postcodes.io returns null coords for these territories.
_CROWN_DEPENDENCY_OUTCODE_COORDS: dict[str, Tuple[float, float]] = {
    # Isle of Man
    "IM1": (54.1508, -4.4839),  # Douglas
    "IM2": (54.1667, -4.5167),  # Douglas west / Braddan
    "IM3": (54.1736, -4.4519),  # Onchan
    "IM4": (54.2000, -4.5500),  # Central island
    "IM5": (54.2222, -4.6917),  # Peel
    "IM6": (54.2833, -4.5833),  # Kirk Michael / north-west
    "IM7": (54.3167, -4.3833),  # North (Ramsey area)
    "IM8": (54.3225, -4.3853),  # Ramsey
    "IM9": (54.0833, -4.6500),  # Castletown / Port Erin / south
    "IM86": (54.1508, -4.4839),
    "IM87": (54.1508, -4.4839),
    "IM99": (54.1508, -4.4839),
    # Guernsey
    "GY1": (49.4550, -2.5360),
    "GY2": (49.4650, -2.5550),
    "GY3": (49.4800, -2.5400),
    "GY4": (49.4300, -2.5600),
    "GY5": (49.4500, -2.6000),
    "GY6": (49.4800, -2.5800),
    "GY7": (49.4400, -2.6000),
    "GY8": (49.4300, -2.5300),
    "GY9": (49.7200, -2.2000),  # Alderney
    "GY10": (49.7200, -2.2000),
    # Jersey
    "JE1": (49.1840, -2.1070),  # St Helier
    "JE2": (49.1900, -2.1200),
    "JE3": (49.2100, -2.1500),
    "JE4": (49.1840, -2.1070),
    "JE5": (49.2200, -2.0800),
}

_CROWN_DEPENDENCY_DEFAULTS: dict[str, Tuple[float, float]] = {
    "IM": (54.2361, -4.5481),  # Isle of Man centre
    "GY": (49.4650, -2.5850),  # Guernsey
    "JE": (49.2144, -2.1312),  # Jersey
}

_CROWN_OUTCODE_RE = re.compile(r"^(IM|GY|JE)(\d+[A-Z]?)", re.IGNORECASE)


def _normalise_postcode(postcode: str) -> str:
    """Strip and uppercase. Returns compact form (no space) for validation."""
    return (postcode or "").strip().upper().replace(" ", "")


def _format_postcode_for_api(postcode: str) -> str:
    """Format as OUTCODE INCODE (e.g. M1 1AA) for postcodes.io URL."""
    compact = _normalise_postcode(postcode)
    if len(compact) >= 4 and compact[-3:].isdigit() is False:
        return f"{compact[:-3]} {compact[-3:]}"
    return compact


def _crown_dependency_fallback_coords(postcode: str) -> Optional[Tuple[float, float]]:
    """
    Approximate coords for Isle of Man / Channel Islands postcodes.
    postcodes.io often returns null lat/lng for these even when the postcode is valid.
    """
    compact = _normalise_postcode(postcode)
    if not compact:
        return None
    match = _CROWN_OUTCODE_RE.match(compact)
    if not match:
        return None
    territory = match.group(1).upper()
    # Prefer longest matching outcode key (e.g. IM86 before IM8)
    for outcode, coords in sorted(
        _CROWN_DEPENDENCY_OUTCODE_COORDS.items(),
        key=lambda item: len(item[0]),
        reverse=True,
    ):
        if compact.startswith(outcode):
            return coords
    return _CROWN_DEPENDENCY_DEFAULTS.get(territory)


def get_postcode_coordinates(postcode: str) -> Tuple[float, float]:
    """
    Resolve UK postcode to (latitude, longitude) via postcodes.io.
    Falls back to Crown Dependency outcode centroids when lat/lng are missing.
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
        # postcodes.io may reject some crown-dependency forms; still try fallback
        fallback = _crown_dependency_fallback_coords(postcode)
        if fallback is not None:
            return fallback
        data = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {}
        if data.get("error") == "Invalid postcode":
            raise ValueError("Postcode not found")
        raise ValueError(data.get("error", "Postcode not found"))

    data = resp.json()
    result = data.get("result")
    if not result:
        fallback = _crown_dependency_fallback_coords(postcode)
        if fallback is not None:
            return fallback
        raise ValueError("Postcode not found")
    lat = result.get("latitude")
    lon = result.get("longitude")
    if lat is None or lon is None:
        fallback = _crown_dependency_fallback_coords(postcode)
        if fallback is not None:
            return fallback
        raise ValueError("Postcode not found")
    return (float(lat), float(lon))


BULK_BATCH_SIZE = 100


def bulk_geocode_postcodes(postcodes: List[str]) -> List[Optional[Tuple[float, float]]]:
    """
    Bulk geocode UK postcodes via postcodes.io.
    Returns list of (lat, lng) or None for each input postcode (same order).
    Batches requests (max 100 per request).
    Applies Crown Dependency outcode fallbacks when postcodes.io returns null coords.
    """
    if not postcodes:
        return []
    formatted = []
    for pc in postcodes:
        if not _normalise_postcode(pc):
            formatted.append(None)
        else:
            formatted.append(_format_postcode_for_api(pc))
    valid_with_idx = [(i, f) for i, f in enumerate(formatted) if f is not None]
    if not valid_with_idx:
        return [None] * len(postcodes)

    results: List[Optional[Tuple[float, float]]] = [None] * len(postcodes)
    for batch_start in range(0, len(valid_with_idx), BULK_BATCH_SIZE):
        batch = valid_with_idx[batch_start : batch_start + BULK_BATCH_SIZE]
        to_lookup = [f for _, f in batch]
        url = f"{POSTCODES_IO_BASE}/postcodes"
        try:
            with httpx.Client(timeout=15.0) as client:
                resp = client.post(url, json={"postcodes": to_lookup})
        except (httpx.TimeoutException, httpx.RequestError):
            continue
        if resp.status_code != 200:
            continue
        try:
            data = resp.json()
        except Exception:
            continue
        api_results = data.get("result") or []
        for k, (orig_idx, _) in enumerate(batch):
            item = api_results[k] if k < len(api_results) else None
            if item and isinstance(item, dict):
                inner = item.get("result")
                if inner and isinstance(inner, dict):
                    lat = inner.get("latitude")
                    lon = inner.get("longitude")
                    if lat is not None and lon is not None:
                        results[orig_idx] = (float(lat), float(lon))

    # Fill gaps for Isle of Man / Channel Islands (and any failed lookups that match)
    for i, pc in enumerate(postcodes):
        if results[i] is None:
            results[i] = _crown_dependency_fallback_coords(pc)
    return results


def get_road_distance_and_duration(
    origin_lat: float,
    origin_lon: float,
    dest_lat: float,
    dest_lon: float,
) -> Optional[Tuple[float, float]]:
    """
    Get road distance (miles) and drive duration (hours) via OpenRouteService.
    Returns (distance_miles, duration_hours) or None if no API key, request fails, or no route.
    ORS expects coordinates as [longitude, latitude] per point.
    """
    api_key = (os.getenv("OPENROUTE_SERVICE_API_KEY") or "").strip()
    if not api_key:
        return None
    body = {
        "coordinates": [[origin_lon, origin_lat], [dest_lon, dest_lat]],
    }
    try:
        with httpx.Client(timeout=15.0) as client:
            resp = client.post(
                ORS_DIRECTIONS_BASE,
                json=body,
                headers={"Authorization": api_key},
            )
    except (httpx.TimeoutException, httpx.RequestError):
        return None
    if resp.status_code != 200:
        return None
    try:
        data = resp.json()
    except Exception:
        return None
    routes = data.get("routes") if isinstance(data, dict) else None
    if not routes or not isinstance(routes, list):
        return None
    summary = routes[0].get("summary") if isinstance(routes[0], dict) else None
    if not summary or not isinstance(summary, dict):
        return None
    dist_m = summary.get("distance")
    dur_s = summary.get("duration")
    if dist_m is None or dur_s is None:
        return None
    try:
        distance_miles = float(dist_m) / METRES_PER_MILE
        duration_hours = float(dur_s) / SECONDS_PER_HOUR
    except (TypeError, ValueError):
        return None
    if distance_miles < 0 or duration_hours < 0:
        return None
    return (distance_miles, duration_hours)


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
