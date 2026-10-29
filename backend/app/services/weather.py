"""Weather intelligence for crop-health and spray decisions.

Uses Open-Meteo, which needs no API key, so the feature works on a fresh
deployment. The value the platform adds is not the forecast itself but the
*decision* on top of it: whether a spray window is open, how much disease
pressure the coming days carry, and how that changes the treatment advice.

Every judgement is returned with the reasoning attached, so an agronomist can
see why the platform said "do not spray" rather than having to trust a badge.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request

OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"

# Fields we ask Open-Meteo for. Grouped here so the response parser and the
# request stay in step.
_CURRENT = [
    "temperature_2m", "relative_humidity_2m", "precipitation", "rain",
    "weather_code", "wind_speed_10m", "wind_direction_10m", "cloud_cover",
]
_HOURLY = [
    "temperature_2m", "relative_humidity_2m", "precipitation_probability",
    "precipitation", "wind_speed_10m", "cloud_cover",
]
_DAILY = [
    "weather_code", "temperature_2m_max", "temperature_2m_min",
    "precipitation_sum", "precipitation_probability_max", "wind_speed_10m_max",
]

WMO = {
    0: "Clear sky", 1: "Mainly clear", 2: "Partly cloudy", 3: "Overcast",
    45: "Fog", 48: "Depositing rime fog", 51: "Light drizzle", 53: "Drizzle",
    55: "Dense drizzle", 56: "Light freezing drizzle", 57: "Freezing drizzle",
    61: "Slight rain", 63: "Moderate rain", 65: "Heavy rain",
    66: "Light freezing rain", 67: "Freezing rain", 71: "Slight snow",
    73: "Moderate snow", 75: "Heavy snow", 77: "Snow grains",
    80: "Slight rain showers", 81: "Moderate rain showers", 82: "Violent rain showers",
    85: "Slight snow showers", 86: "Heavy snow showers",
    95: "Thunderstorm", 96: "Thunderstorm with slight hail", 99: "Thunderstorm with heavy hail",
}

# Thresholds are the ones agronomists actually use for spraying, stated once so
# the guidance text and the badge can never disagree.
MAX_SPRAY_WIND_KMH = 12.0
MAX_SPRAY_TEMP_C = 32.0
MIN_SPRAY_HUMIDITY = 40.0
RAIN_RISK_PCT = 40


class WeatherProviderError(RuntimeError):
    pass


def _get_json(params: dict, timeout: float = 12.0) -> dict:
    query = urllib.parse.urlencode(params)
    req = urllib.request.Request(
        f"{OPEN_METEO_URL}?{query}", headers={"Accept": "application/json"}
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        raise WeatherProviderError(f"Open-Meteo HTTP {exc.code}") from exc
    except Exception as exc:
        raise WeatherProviderError(f"Weather request failed: {exc}") from exc


def fetch(lat: float, lon: float, *, days: int = 7) -> dict:
    """Raw forecast plus derived spray-window and disease-pressure judgements."""
    days = max(1, min(14, days))
    data = _get_json({
        "latitude": lat, "longitude": lon,
        "current": ",".join(_CURRENT),
        "hourly": ",".join(_HOURLY),
        "daily": ",".join(_DAILY),
        "timezone": "auto",
        "forecast_days": days,
    })
    return _shape(data, days)


def _num(value) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _shape(data: dict, days: int) -> dict:
    current_raw = data.get("current") or {}
    hourly = data.get("hourly") or {}
    daily = data.get("daily") or {}

    current = {
        "time": current_raw.get("time"),
        "temperature_c": _num(current_raw.get("temperature_2m")),
        "humidity_pct": _num(current_raw.get("relative_humidity_2m")),
        "precipitation_mm": _num(current_raw.get("precipitation")),
        "wind_kmh": _num(current_raw.get("wind_speed_10m")),
        "wind_dir_deg": _num(current_raw.get("wind_direction_10m")),
        "cloud_pct": _num(current_raw.get("cloud_cover")),
        "code": current_raw.get("weather_code"),
        "condition": WMO.get(current_raw.get("weather_code"), "Unknown"),
    }

    times = hourly.get("time") or []
    hours = []
    for i, t in enumerate(times):
        hours.append({
            "time": t,
            "temperature_c": _num((hourly.get("temperature_2m") or [None])[i] if i < len(hourly.get("temperature_2m") or []) else None),
            "humidity_pct": _num((hourly.get("relative_humidity_2m") or [None])[i] if i < len(hourly.get("relative_humidity_2m") or []) else None),
            "rain_prob_pct": _num((hourly.get("precipitation_probability") or [None])[i] if i < len(hourly.get("precipitation_probability") or []) else None),
            "precipitation_mm": _num((hourly.get("precipitation") or [None])[i] if i < len(hourly.get("precipitation") or []) else None),
            "wind_kmh": _num((hourly.get("wind_speed_10m") or [None])[i] if i < len(hourly.get("wind_speed_10m") or []) else None),
            "cloud_pct": _num((hourly.get("cloud_cover") or [None])[i] if i < len(hourly.get("cloud_cover") or []) else None),
        })

    dtimes = daily.get("time") or []
    ddays = []
    for i, t in enumerate(dtimes):
        def pick(key):
            arr = daily.get(key) or []
            return arr[i] if i < len(arr) else None
        ddays.append({
            "date": t,
            "code": pick("weather_code"),
            "condition": WMO.get(pick("weather_code"), "Unknown"),
            "temp_max_c": _num(pick("temperature_2m_max")),
            "temp_min_c": _num(pick("temperature_2m_min")),
            "rain_mm": _num(pick("precipitation_sum")),
            "rain_prob_pct": _num(pick("precipitation_probability_max")),
            "wind_max_kmh": _num(pick("wind_speed_10m_max")),
        })

    windows = _spray_windows(hours)
    pressure = _disease_pressure(current, hours, ddays)
    return {
        "provider": "open-meteo",
        "timezone": data.get("timezone"),
        "current": current,
        "hourly": hours[:72],
        "daily": ddays,
        "spray_windows": windows,
        "disease_pressure": pressure,
        "guidance": _guidance(current, windows, pressure),
        "disclaimer": (
            "Forecast-based guidance only. Confirm locally before spraying; always "
            "follow the approved product label and pre-harvest interval."
        ),
    }


def _spray_windows(hours: list[dict]) -> dict:
    """Find the next open spray window and list blocked hours with reasons."""
    best = None
    for h in hours[:48]:
        reasons = []
        if (h["wind_kmh"] or 0) > MAX_SPRAY_WIND_KMH:
            reasons.append(f"wind {h['wind_kmh']:.0f} km/h")
        if (h["rain_prob_pct"] or 0) >= RAIN_RISK_PCT:
            reasons.append(f"rain risk {h['rain_prob_pct']:.0f}%")
        if (h["temperature_c"] or 0) > MAX_SPRAY_TEMP_C:
            reasons.append(f"heat {h['temperature_c']:.0f}°C")
        if (h["humidity_pct"] or 100) < MIN_SPRAY_HUMIDITY:
            reasons.append(f"dry air {h['humidity_pct']:.0f}%")
        h["spray_ok"] = not reasons
        h["spray_blockers"] = reasons
        if not reasons and best is None:
            best = h

    blocked = [h for h in hours[:48] if not h.get("spray_ok", True)]
    return {
        "next_open": best,
        "open_hours_next_48": sum(1 for h in hours[:48] if h.get("spray_ok")),
        "blocked_hours_next_48": len(blocked),
        "thresholds": {
            "max_wind_kmh": MAX_SPRAY_WIND_KMH,
            "max_temp_c": MAX_SPRAY_TEMP_C,
            "min_humidity_pct": MIN_SPRAY_HUMIDITY,
            "rain_risk_pct": RAIN_RISK_PCT,
        },
    }


def _disease_pressure(current: dict, hours: list[dict], daily: list[dict]) -> dict:
    """A transparent 0-100 index of fungal/bacterial pressure over 3 days.

    Warm, humid, leafy conditions drive most foliar disease. The score is the
    sum of named contributions, so the number is always explainable.
    """
    next3 = hours[:72]
    if not next3:
        return {"index": 0, "band": "unknown", "drivers": [], "note": "No hourly data."}

    warm_humid = sum(
        1 for h in next3
        if (h["temperature_c"] or 0) >= 20 and (h["humidity_pct"] or 0) >= 80
    )
    leaf_wet = sum(1 for h in next3 if (h["precipitation_mm"] or 0) > 0.1)
    rain3 = sum(d.get("rain_mm") or 0 for d in daily[:3])
    humid_pct = sum((h["humidity_pct"] or 0) for h in next3) / len(next3)

    index = min(100, round(
        warm_humid / len(next3) * 55
        + leaf_wet / len(next3) * 25
        + min(20.0, rain3 * 1.5)
    ))
    drivers = []
    if warm_humid:
        drivers.append(f"{warm_humid} of the next {len(next3)} hours are warm (≥20°C) and humid (≥80%)")
    if leaf_wet:
        drivers.append(f"Leaf wetness expected in {leaf_wet} hours")
    if rain3:
        drivers.append(f"{rain3:.1f} mm rain forecast over three days")
    if humid_pct >= 75:
        drivers.append(f"Average humidity {humid_pct:.0f}%")

    band = "low" if index < 30 else "moderate" if index < 60 else "high"
    return {"index": index, "band": band, "drivers": drivers,
            "average_humidity_pct": round(humid_pct, 1)}


def _guidance(current: dict, windows: dict, pressure: dict) -> dict:
    """Turn the numbers into a short crop-health and treatment message."""
    nxt = windows.get("next_open")
    health_notes = []
    if pressure["band"] == "high":
        health_notes.append(
            "High disease pressure: scout leaf undersides and new growth daily, and "
            "prioritise any field with a history of foliar disease."
        )
    elif pressure["band"] == "moderate":
        health_notes.append(
            "Moderate disease pressure: keep a twice-weekly scouting routine on the "
            "most susceptible blocks."
        )
    else:
        health_notes.append("Low disease pressure: routine scouting is sufficient.")

    treatment_notes = []
    if nxt:
        treatment_notes.append(
            f"Next open spray window: {nxt['time'].replace('T', ' ')} "
            f"(wind {nxt['wind_kmh']:.0f} km/h, rain risk {nxt['rain_prob_pct']:.0f}%)."
        )
    else:
        treatment_notes.append(
            "No clear spray window in the next 48 hours — defer treatment rather than "
            "spraying into wind, heat or rain."
        )
    if windows["blocked_hours_next_48"]:
        treatment_notes.append(
            f"{windows['blocked_hours_next_48']} of the next 48 hours are unsuitable for spraying."
        )
    if current.get("precipitation_mm"):
        treatment_notes.append(
            "Rain is falling now; a spray would wash off before uptake."
        )
    return {"crop_health": health_notes, "treatment": treatment_notes}


def fetch_for(lat: float | None, lon: float | None, *, days: int = 7) -> dict:
    """Convenience wrapper that reports a clear error when coordinates are absent."""
    if lat is None or lon is None:
        raise WeatherProviderError("A location is required for weather data.")
    return fetch(lat, lon, days=days)
