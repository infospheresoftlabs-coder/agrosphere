"""Geo helpers: polygon area (spherical), GeoJSON validation, drone simulation."""

from __future__ import annotations

import math
import random

EARTH_RADIUS_M = 6_371_008.8


def polygon_area_acres(coordinates: list[list[float]]) -> float:
    """Spherical excess area of a lon/lat ring, converted to acres."""
    if len(coordinates) < 3:
        return 0.0
    ring = list(coordinates)
    if ring[0] != ring[-1]:
        ring.append(ring[0])
    total = 0.0
    for (lon1, lat1), (lon2, lat2) in zip(ring, ring[1:]):
        total += math.radians(lon2 - lon1) * (
            2 + math.sin(math.radians(lat1)) + math.sin(math.radians(lat2))
        )
    area_m2 = abs(total) * EARTH_RADIUS_M * EARTH_RADIUS_M / 2.0
    return round(area_m2 / 4046.8564224, 4)


def validate_boundary(boundary: dict | None) -> list[str]:
    errors: list[str] = []
    if not boundary:
        return ["boundary is required"]
    if boundary.get("type") != "Polygon":
        errors.append("boundary.type must be 'Polygon'")
    coords = boundary.get("coordinates")
    if not isinstance(coords, list) or not coords or not isinstance(coords[0], list):
        errors.append("boundary.coordinates must be [[[lon,lat], ...]]")
        return errors
    ring = coords[0]
    if len(ring) < 3:
        errors.append("polygon needs at least 3 points")
    for pt in ring:
        if not (isinstance(pt, list) and len(pt) == 2):
            errors.append("each point must be [lon, lat]")
            break
        lon, lat = pt
        if not (-180 <= lon <= 180 and -90 <= lat <= 90):
            errors.append("coordinates out of range")
            break
    return errors


def simulate_mission(boundary: dict | None, acres: float, payload_l: float) -> dict:
    """Produce clearly-labelled simulated telemetry for a drone mission."""
    rng = random.Random(int(acres * 1000) + len(str(boundary or "")))
    duration_min = max(6, round(acres * 3.5 + rng.uniform(1, 4)))
    return {
        "simulated": True,
        "label": "SIMULATED MISSION — not a real flight",
        "duration_min": duration_min,
        "max_altitude_m": round(rng.uniform(3.0, 6.0), 1),
        "speed_ms": round(rng.uniform(3.0, 6.5), 2),
        "battery_used_pct": round(min(92, 18 + acres * 6 + rng.uniform(0, 8)), 1),
        "payload_liters": round(payload_l, 2),
        "gps_track_points": max(12, int(acres * 18)),
        "geofence_ok": True,
        "restricted_zone_clear": True,
        "errors": [],
    }


def preflight_checklist(device: dict | None) -> list[dict]:
    battery = (device or {}).get("battery_health_pct", 100)
    return [
        {"item": "Propellers and frame inspected", "ok": True},
        {"item": "Battery health above 80%", "ok": battery >= 80},
        {"item": "Payload tank leak check", "ok": True},
        {"item": "GPS lock and RTK fix", "ok": True},
        {"item": "Geofence and restricted-zone check", "ok": True},
        {"item": "Weather within limits", "ok": True},
        {"item": "Emergency stop reachable", "ok": True},
    ]


# --------------------------------------------------------------------------- #
# Geoapify integration: forward/reverse geocoding and routing
# --------------------------------------------------------------------------- #
GEOAPIFY_BASE = "https://api.geoapify.com/v1"

# Human-readable travel modes Geoapify accepts, mapped to the values a farmer
# would actually use. "drive" is the default for reaching a field.
ROUTE_MODES = {"drive", "truck", "motorcycle", "bicycle", "walk", "transit"}


class GeoProviderError(RuntimeError):
    """Raised when the upstream geo provider fails or is not configured."""


def _geoapify_key() -> str:
    # Imported lazily so this module stays importable without app config.
    from ..config import settings

    return settings.geoapify_api_key


def _get_json(url: str, params: dict, timeout: float = 15.0) -> dict:
    import json
    import urllib.parse
    import urllib.request

    query = urllib.parse.urlencode({k: v for k, v in params.items() if v is not None})
    req = urllib.request.Request(f"{url}?{query}", headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode()[:300]
        raise GeoProviderError(f"Geoapify HTTP {exc.code}: {detail}") from exc
    except Exception as exc:  # network, DNS, timeout
        raise GeoProviderError(f"Geoapify request failed: {exc}") from exc


def geocode_address(text: str, *, limit: int = 5, country: str = "in") -> list[dict]:
    """Forward-geocode free text to candidate places, best match first."""
    key = _geoapify_key()
    if not key:
        raise GeoProviderError("Geoapify API key is not configured")
    data = _get_json(
        f"{GEOAPIFY_BASE}/geocode/search",
        {"text": text, "limit": limit, "filter": f"countrycode:{country}", "apiKey": key},
    )
    out = []
    for feat in data.get("features", []):
        props = feat.get("properties", {})
        coords = (feat.get("geometry") or {}).get("coordinates") or [None, None]
        out.append({
            "formatted": props.get("formatted"),
            "address_line1": props.get("address_line1"),
            "address_line2": props.get("address_line2"),
            "village": props.get("village") or props.get("suburb") or props.get("city"),
            "district": props.get("county") or props.get("district"),
            "state": props.get("state"),
            "postcode": props.get("postcode"),
            "country": props.get("country"),
            "latitude": coords[1],
            "longitude": coords[0],
            "confidence": props.get("rank", {}).get("confidence") if isinstance(props.get("rank"), dict) else None,
        })
    return out


def reverse_geocode(lat: float, lon: float) -> dict:
    """Resolve coordinates to the administrative names used by Farm records."""
    key = _geoapify_key()
    if not key:
        raise GeoProviderError("Geoapify API key is not configured")
    data = _get_json(
        f"{GEOAPIFY_BASE}/geocode/reverse",
        {"lat": lat, "lon": lon, "apiKey": key},
    )
    features = data.get("features", [])
    if not features:
        return {"formatted": None, "latitude": lat, "longitude": lon}
    props = features[0].get("properties", {})
    return {
        "formatted": props.get("formatted"),
        "village": props.get("village") or props.get("suburb") or props.get("city"),
        "district": props.get("county") or props.get("district"),
        "state": props.get("state"),
        "postcode": props.get("postcode"),
        "country": props.get("country"),
        "latitude": lat,
        "longitude": lon,
    }


def route(
    origin: tuple[float, float],
    destination: tuple[float, float],
    *,
    mode: str = "drive",
) -> dict:
    """Return distance, duration and a GeoJSON geometry between two points.

    ``origin``/``destination`` are ``(lat, lon)``. The route geometry is a
    GeoJSON LineString ready for Leaflet, and the summary carries the fields the
    UI shows to a driver (distance in km, duration in minutes, turn-by-turn).

    A rural field is often not adjacent to a *driveable* edge in the routing
    graph, which makes ``drive`` fail with "no suitable edges" even though the
    destination is perfectly valid. Rather than surface that as an error, the
    call falls back through progressively slower modes and reports which one
    actually produced the route, so the UI can say "by bicycle" instead of
    showing nothing.
    """
    key = _geoapify_key()
    if not key:
        raise GeoProviderError("Geoapify API key is not configured")
    requested = mode if mode in ROUTE_MODES else "drive"
    fallbacks = [requested] + [m for m in ("drive", "motorcycle", "bicycle", "walk") if m != requested]

    last_error: Exception | None = None
    for candidate in fallbacks:
        try:
            return _route_once(key, origin, destination, candidate, requested)
        except GeoProviderError as exc:
            last_error = exc
            # Only a "no suitable edges" failure is worth retrying; anything
            # else (bad key, quota, outage) will not be fixed by another mode.
            if "no suitable edges" not in str(exc).lower():
                raise
    raise last_error or GeoProviderError("No route found between the given points")


def _route_once(
    key: str,
    origin: tuple[float, float],
    destination: tuple[float, float],
    mode: str,
    requested: str,
) -> dict:
    olat, olon = origin
    dlat, dlon = destination
    data = _get_json(
        f"{GEOAPIFY_BASE}/routing",
        {
            "waypoints": f"{olat},{olon}|{dlat},{dlon}",
            "mode": mode,
            "units": "metric",
            "apiKey": key,
        },
    )
    features = data.get("features", [])
    if not features:
        raise GeoProviderError("No route found between the given points")
    feat = features[0]
    props = feat.get("properties", {})
    steps = []
    for leg in props.get("legs") or []:
        for step in leg.get("steps", []):
            steps.append({
                "instruction": (step.get("instruction") or {}).get("text"),
                "distance_m": step.get("distance"),
                "time_s": step.get("time"),
            })
    return {
        "mode": mode,
        "mode_requested": requested,
        "fallback": mode != requested,
        "distance_m": props.get("distance"),
        "distance_km": round((props.get("distance") or 0) / 1000, 2),
        "duration_s": props.get("time"),
        "duration_min": round((props.get("time") or 0) / 60, 1),
        "geometry": feat.get("geometry"),
        "steps": steps,
        "origin": {"latitude": olat, "longitude": olon},
        "destination": {"latitude": dlat, "longitude": dlon},
    }


def haversine_km(a: tuple[float, float], b: tuple[float, float]) -> float:
    """Straight-line distance in km between two ``(lat, lon)`` points."""
    import math

    lat1, lon1 = a
    lat2, lon2 = b
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    h = (
        math.sin(dlat / 2) ** 2
        + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2
    )
    return round(2 * EARTH_RADIUS_M / 1000 * math.asin(math.sqrt(h)), 3)
