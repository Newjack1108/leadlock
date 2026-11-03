"""
UK postcode geocoding via postcodes.io; Haversine (straight-line) and OpenRouteService (road) distance.

postcodes.io serves the ONS postcode directory, which is narrower than the set of
postcodes Google will geocode:

- Retired postcodes come back as 404, with the old coordinates under ``terminated``.
- Newer unit postcodes can be missing until the next ONS release; the outward code
  (for example CW5) is usually already there, so we use that district centre.
- Crown Dependencies often return a record with null latitude/longitude.
- A few Royal Mail special postcodes (Gibraltar, Falklands, and similar) never
  appear in postcodes.io at all.
"""
import math
import os
import re
from typing import List, Optional, Tuple
from urllib.parse import quote

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
# Inward code is always one digit then two letters. Outward code is 2–4 characters.
_INWARD_RE = re.compile(r"^\d[A-Z]{2}$")
_FULL_POSTCODE_RE = re.compile(r"^[A-Z]{1,2}\d[A-Z\d]?\d[A-Z]{2}$")
_OUTCODE_RE = re.compile(r"^[A-Z]{1,2}\d[A-Z\d]?$")

# Royal Mail special postcodes. postcodes.io rejects the format; Google still geocodes them.
_SPECIAL_OUTCODE_COORDS: dict[str, Tuple[float, float]] = {
    "GX11": (36.1408, -5.3536),  # Gibraltar
    "ASCN": (-7.9467, -14.3559),  # Ascension Island
    "BBND": (-7.3195, 72.4229),  # British Indian Ocean Territory
    "BIQQ": (-67.5684, -68.1258),  # British Antarctic Territory (Rothera)
    "FIQQ": (-51.6977, -57.8516),  # Falkland Islands
    "PCRN": (-25.0660, -130.1015),  # Pitcairn Islands
    "SIQQ": (-54.2833, -36.4937),  # South Georgia
    "STHL": (-15.9260, -5.7168),  # Saint Helena
    "TDCU": (-37.0676, -12.3116),  # Tristan da Cunha
    "TKCA": (21.4612, -71.1390),  # Turks and Caicos
}


def _normalise_postcode(postcode: str) -> str:
    """Uppercase compact form. Drops spaces, punctuation, and non-breaking spaces."""
    raw = (postcode or "").strip().upper()
    return "".join(ch for ch in raw if ch.isalnum())


def _outcode_from_compact(compact: str) -> Optional[str]:
    """Outward code from a full postcode (SW1A1AA → SW1A) or a bare outcode (CW5)."""
    if _FULL_POSTCODE_RE.match(compact):
        return compact[:-3]
    if _OUTCODE_RE.match(compact):
        return compact
    return None


def _special_coords(compact: str) -> Optional[Tuple[float, float]]:
    """Coordinates for Royal Mail special postcodes, matched on the outward code."""
    for outcode, coords in sorted(
        _SPECIAL_OUTCODE_COORDS.items(),
        key=lambda item: len(item[0]),
        reverse=True,
    ):
        if compact == outcode:
            return coords
        remainder = compact[len(outcode) :]
        if compact.startswith(outcode) and _INWARD_RE.match(remainder):
            return coords
    return None


def _coord_pair(payload: object) -> Optional[Tuple[float, float]]:
    if not isinstance(payload, dict):
        return None
    lat = payload.get("latitude")
    lon = payload.get("longitude")
    if lat is None or lon is None:
        return None
    try:
        return (float(lat), float(lon))
    except (TypeError, ValueError):
        return None


def _response_json(resp: httpx.Response) -> dict:
    try:
        data = resp.json()
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _coords_from_postcodes_payload(data: object) -> Optional[Tuple[float, float]]:
    """Live postcode coordinates, or the retired coordinates postcodes.io embeds in a 404."""
    if not isinstance(data, dict):
        return None
    live = _coord_pair(data.get("result"))
    if live is not None:
        return live
    return _coord_pair(data.get("terminated"))


def _outcode_hint(result: object, compact: str) -> Optional[str]:
    if isinstance(result, dict):
        raw = result.get("outcode")
        if isinstance(raw, str):
            cleaned = "".join(ch for ch in raw.upper() if ch.isalnum())
            if cleaned:
                return cleaned
    return _outcode_from_compact(compact)


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


def _lookup_outcode_coordinates(client: httpx.Client, outcode: str) -> Optional[Tuple[float, float]]:
    """District centre for an outward code such as CW5 or SW1A."""
    url = f"{POSTCODES_IO_BASE}/outcodes/{quote(outcode, safe='')}"
    resp = client.get(url)
    return _coord_pair(_response_json(resp).get("result"))


def _lookup_postcode_coordinates(client: httpx.Client, compact: str) -> Tuple[float, float]:
    """
    Resolve a normalised postcode.

    Order: Royal Mail specials, live postcode, retired postcode coordinates,
    Crown Dependency table, then the outward-code centre.
    """
    special = _special_coords(compact)
    if special is not None:
        return special

    resp = client.get(f"{POSTCODES_IO_BASE}/postcodes/{quote(compact, safe='')}")
    data = _response_json(resp)
    coords = _coords_from_postcodes_payload(data)
    if coords is not None:
        return coords

    crown = _crown_dependency_fallback_coords(compact)
    if crown is not None:
        return crown

    result = data.get("result")
    outcode = _outcode_hint(result, compact)
    if outcode:
        outcode_coords = _lookup_outcode_coordinates(client, outcode)
        if outcode_coords is not None:
            return outcode_coords

    raise ValueError("Postcode not found")


def get_postcode_coordinates(postcode: str) -> Tuple[float, float]:
    """
    Resolve a UK postcode to (latitude, longitude).

    Uses postcodes.io, including retired postcodes Google still recognises, and
    falls back to the outward-code centre when the full postcode is not listed yet.
    Raises ValueError if the postcode is empty or cannot be located.
    """
    compact = _normalise_postcode(postcode)
    if not compact:
        raise ValueError("Postcode is required")
    special = _special_coords(compact)
    if special is not None:
        return special
    try:
        with httpx.Client(timeout=10.0) as client:
            return _lookup_postcode_coordinates(client, compact)
    except httpx.TimeoutException:
        raise ValueError("Postcode lookup timed out. Please try again.")
    except httpx.RequestError as e:
        raise ValueError(f"Postcode lookup failed: {e!s}")


BULK_BATCH_SIZE = 100


def bulk_geocode_postcodes(postcodes: List[str]) -> List[Optional[Tuple[float, float]]]:
    """
    Bulk geocode UK postcodes via postcodes.io.
    Returns list of (lat, lng) or None for each input postcode (same order).
    Batches requests (max 100 per request).
    Fills gaps for Crown Dependencies, retired postcodes, and outward-code centres.
    """
    if not postcodes:
        return []
    formatted: List[Optional[str]] = []
    for pc in postcodes:
        compact = _normalise_postcode(pc)
        formatted.append(compact or None)
    valid_with_idx = [(i, f) for i, f in enumerate(formatted) if f is not None]
    if not valid_with_idx:
        return [None] * len(postcodes)

    results: List[Optional[Tuple[float, float]]] = [None] * len(postcodes)
    # Indexes the bulk call actually answered. A failed batch must not fan out into
    # one HTTP request per postcode.
    answered_by_bulk: set[int] = set()
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
            answered_by_bulk.add(orig_idx)
            item = api_results[k] if k < len(api_results) else None
            if item and isinstance(item, dict):
                inner = item.get("result")
                if inner and isinstance(inner, dict):
                    lat = inner.get("latitude")
                    lon = inner.get("longitude")
                    if lat is not None and lon is not None:
                        results[orig_idx] = (float(lat), float(lon))

    for i, pc in enumerate(postcodes):
        if results[i] is not None:
            continue
        compact = _normalise_postcode(pc)
        results[i] = _crown_dependency_fallback_coords(compact) or _special_coords(compact)

    # Retired and newly issued unit postcodes are absent from the bulk payload.
    # Look those up one by one; the single-postcode response includes old coordinates.
    missing_indexes = []
    for i in sorted(answered_by_bulk):
        if results[i] is not None:
            continue
        compact = _normalise_postcode(postcodes[i])
        if _outcode_from_compact(compact):
            missing_indexes.append(i)
    if missing_indexes:
        try:
            with httpx.Client(timeout=10.0) as client:
                for i in missing_indexes:
                    try:
                        results[i] = _lookup_postcode_coordinates(
                            client, _normalise_postcode(postcodes[i])
                        )
                    except (httpx.TimeoutException, httpx.RequestError, ValueError):
                        results[i] = None
        except (httpx.TimeoutException, httpx.RequestError):
            pass
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
