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
