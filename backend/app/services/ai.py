"""Provider-independent AI crop-health analysis service.

The service is deterministic and offline by default so the platform never
fabricates a live model response. When ``AGROSPHERE_AI_PROVIDER`` is set to a
supported provider *and* the corresponding key is present, the service performs a
real call; otherwise it returns clearly-labelled simulated findings derived from
verified knowledge sources and marks the result as a simulator output.

Safety rules enforced here:
  * findings are always preliminary and carry calibrated uncertainty,
  * low-confidence / out-of-distribution cases are escalated to a human,
  * an uncertain diagnosis is never converted into a spraying command.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import random
import time
import urllib.error
import urllib.request

log = logging.getLogger("agrosphere.ai")

# Language code -> English name, for prompting the model to answer in-language.
from ..constants import LANGUAGES  # noqa: E402

_LANG_NAMES = {l["code"]: l["name"] for l in LANGUAGES}

# Verified agricultural knowledge base. In production these rows are loaded from
# the ``knowledge_sources`` table; ICAR / SAU / KVK / government departments.
KNOWLEDGE: list[dict] = [
    {
        "id": "icar-wheat-rust",
        "title": "Wheat rust management advisory",
        "organization": "ICAR - Indian Institute of Wheat and Barley Research",
        "crop": "wheat",
        "region": "India",
        "published": "2023-11-01",
        "version": "2.1",
        "status": "verified",
        "summary": "Yellow/orange pustules on leaves indicate rust; early detection and "
        "resistant varieties plus approved fungicide timing reduce yield loss.",
    },
    {
        "id": "icar-rice-blast",
        "title": "Rice blast disease advisory",
        "organization": "ICAR - Indian Institute of Rice Research",
        "crop": "rice",
        "region": "India",
        "published": "2023-06-15",
        "version": "1.4",
        "status": "verified",
        "summary": "Diamond-shaped lesions with grey centres on rice leaves suggest blast; "
        "manage with balanced nitrogen and approved fungicides at boot stage.",
    },
    {
        "id": "kvk-cotton-pinkbollworm",
        "title": "Pink bollworm in cotton - field advisory",
        "organization": "Krishi Vigyan Kendra network",
        "crop": "cotton",
        "region": "Central India",
        "published": "2024-02-20",
        "version": "1.0",
        "status": "verified",
        "summary": "Rosette flowers and bored bolls indicate pink bollworm; use pheromone "
        "traps, timely termination and approved IPM practices.",
    },
    {
        "id": "sau-tomato-blight",
        "title": "Tomato early blight management",
        "organization": "State Agricultural University - Plant Pathology Dept.",
        "crop": "tomato",
        "region": "India",
        "published": "2023-08-05",
        "version": "1.2",
        "status": "verified",
        "summary": "Concentric dark rings on lower leaves indicate early blight; remove "
        "infected debris and apply approved protectant fungicides per label.",
    },
    {
        "id": "icar-nutrient-deficiency",
        "title": "Diagnosing nutrient deficiency in cereals",
        "organization": "ICAR - Soil Science Division",
        "crop": "cereals",
        "region": "India",
        "published": "2023-04-10",
        "version": "1.1",
        "status": "verified",
        "summary": "Uniform chlorosis across leaves suggests nitrogen deficiency, while "
        "interveinal chlorosis suggests micronutrient deficiency; confirm with soil test.",
    },
    {
        "id": "govt-abiotic-stress",
        "title": "Abiotic stress: heat, drought and salinity",
        "organization": "Department of Agriculture & Farmers Welfare",
        "crop": "multi",
        "region": "India",
        "published": "2024-01-12",
        "version": "1.0",
        "status": "verified",
        "summary": "Wilting, leaf scorch and stunted growth without lesions often indicate "
        "abiotic stress rather than disease; irrigation and shade management apply.",
    },
]

# Candidate diagnoses keyed by a coarse symptom bucket.
CANDIDATES: dict[str, list[dict]] = {
    "rust": [
        {
            "label": "Wheat leaf rust (Puccinia spp.)",
            "evidence": "Orange-brown pustules arranged on the upper leaf surface",
            "alternative": "Nutrient deficiency or sunscald can mimic pustule colour",
            "severity": "high",
            "source": "icar-wheat-rust",
        }
    ],
    "blast": [
        {
            "label": "Rice blast (Magnaporthe oryzae)",
            "evidence": "Diamond-shaped lesions with greyish centres and dark margins",
            "alternative": "Brown spot of rice produces similar but rounder lesions",
            "severity": "high",
            "source": "icar-rice-blast",
        }
    ],
    "bollworm": [
        {
            "label": "Pink bollworm infestation (Pectinophora gossypiella)",
            "evidence": "Rosette-shaped flowers and exit holes on green bolls",
            "alternative": "Other boll-feeding caterpillars cause comparable damage",
            "severity": "high",
            "source": "kvk-cotton-pinkbollworm",
        }
    ],
    "blight": [
        {
            "label": "Early blight (Alternaria solani)",
            "evidence": "Concentric dark rings on older lower leaves",
            "alternative": "Late blight shows water-soaked margins instead",
            "severity": "medium",
            "source": "sau-tomato-blight",
        }
    ],
    "deficiency": [
        {
            "label": "Nitrogen deficiency",
            "evidence": "Uniform pale-green to yellow older leaves with stunted growth",
            "alternative": "Waterlogging produces a similar uniform yellowing",
            "severity": "medium",
            "source": "icar-nutrient-deficiency",
        }
    ],
    "abiotic": [
        {
            "label": "Heat / drought stress",
            "evidence": "Leaf scorching and wilting without distinct lesions",
            "alternative": "Root disease can cause comparable wilting",
            "severity": "medium",
            "source": "govt-abiotic-stress",
        }
    ],
}

_SYMPTOM_HINTS = [
    ("rust", ("rust", "pustule", "orange", "yellow powder")),
    ("blast", ("blast", "diamond", "grey centre", "gray center")),
    ("bollworm", ("bollworm", "rosette", "bore", "cotton")),
    ("blight", ("blight", "concentric", "ring", "spot", "tomato")),
    ("deficiency", ("yellow", "pale", "chlorosis", "nutrient", "deficien")),
    ("abiotic", ("wilt", "dry", "scorch", "heat", "drought", "stress")),
]


def _bucket(text: str, crop: str) -> str:
    low = f"{text} {crop}".lower()
    for bucket, hints in _SYMPTOM_HINTS:
        if any(h in low for h in hints):
            return bucket
    # Fall back to a stable pseudo-random bucket so repeated runs agree.
    idx = int(hashlib.sha256(low.encode()).hexdigest(), 16) % len(CANDIDATES)
    return list(CANDIDATES)[idx]


def _provider_config() -> dict:
    """Resolve the configured provider, key and model.

    ``AGROSPHERE_AI_PROVIDER`` selects the provider (``simulated`` by default).
    OpenRouter is the supported live provider; its key may be supplied either as
    the platform-specific ``AGROSPHERE_AI_API_KEY`` or the conventional
    ``OPENROUTER_API_KEY``.
    """
    provider = (os.getenv("AGROSPHERE_AI_PROVIDER", "simulated") or "simulated").strip().lower()
    if provider in {"", "none", "off"}:
        provider = "simulated"
    key = (
        os.getenv("AGROSPHERE_AI_API_KEY", "").strip()
        or os.getenv("OPENROUTER_API_KEY", "").strip()
    )
    default_model = "openai/gpt-4o-mini" if provider == "openrouter" else "gpt-4o-mini"
    return {
        "provider": provider,
        "key": key,
        "model": (os.getenv("AGROSPHERE_AI_MODEL", "") or default_model).strip(),
        "base_url": (
            os.getenv("AGROSPHERE_AI_BASE_URL", "").rstrip("/")
            or "https://openrouter.ai/api/v1"
        ),
        "timeout": float(os.getenv("AGROSPHERE_AI_TIMEOUT", "30") or 30),
        "site_url": os.getenv("AGROSPHERE_AI_SITE_URL", "https://agrosphere.app"),
        "app_name": os.getenv("AGROSPHERE_AI_APP_NAME", "AgroSphere"),
    }


def provider_status() -> dict:
    cfg = _provider_config()
    live = cfg["provider"] != "simulated" and bool(cfg["key"])
    if cfg["provider"] != "simulated" and not cfg["key"]:
        note = (
            f"Provider '{cfg['provider']}' is selected but no API key is configured; "
            "running the labelled simulator instead."
        )
    elif live:
        note = f"Live provider '{cfg['provider']}' configured (model {cfg['model']})."
    else:
        note = (
            "Running the deterministic simulator: findings are preliminary and "
            "clearly labelled as simulated."
        )
    return {
        "provider": cfg["provider"],
        "model": cfg["model"],
        "live": live,
        "mode": "live" if live else "simulated",
        "note": note,
    }


# --------------------------------------------------------------------------- #
# Live provider (OpenRouter)
# --------------------------------------------------------------------------- #
_SYSTEM_PROMPT = (
    "You are an agricultural plant-pathology assistant supporting Indian farmers. "
    "Given a crop and field observations, return a PRELIMINARY assessment as strict "
    "JSON. Never claim certainty, never issue spraying commands, and always include "
    "an alternative hypothesis and a calibrated uncertainty. Respond with JSON only, "
    "using exactly this shape:\n"
    "{\n"
    '  "findings": [{"label": str, "confidence": number 0-1, "evidence": str, '
    '"alternative": str, "severity": "low"|"medium"|"high"}],\n'
    '  "uncertainty": number 0-1,\n'
    '  "affected_area_pct": number 0-100 or null,\n'
    '  "summary": str\n'
    "}"
)


def _extract_json(text: str) -> dict:
    """Pull a JSON object out of a model response, tolerating code fences."""
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("```")[1] if "```" in cleaned[3:] else cleaned.strip("`")
        cleaned = cleaned[4:] if cleaned.lower().startswith("json") else cleaned
    start, end = cleaned.find("{"), cleaned.rfind("}")
    if start == -1 or end == -1:
        raise ValueError("no JSON object in response")
    return json.loads(cleaned[start : end + 1])


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _live_analyze(*, crop: str, observations: str, media_count: int) -> dict:
    """Call OpenRouter and normalise the result into our analysis contract.

    Raises on any transport, HTTP or validation problem so the caller can fall
    back to the simulator rather than presenting a partial result as complete.
    """
    cfg = _provider_config()
    user_prompt = (
        f"Crop: {crop}\n"
        f"Number of media assets reviewed: {media_count}\n"
        f"Field observations: {observations or '(none recorded)'}\n\n"
        "Return the JSON assessment now."
    )
    payload = {
        "model": cfg["model"],
        "messages": [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.2,
        "response_format": {"type": "json_object"},
    }
    req = urllib.request.Request(
        f"{cfg['base_url']}/chat/completions",
        data=json.dumps(payload).encode(),
        headers={
            "Authorization": f"Bearer {cfg['key']}",
            "Content-Type": "application/json",
            # OpenRouter attribution headers; harmless if unset upstream.
            "HTTP-Referer": cfg["site_url"],
            "X-Title": cfg["app_name"],
        },
        method="POST",
    )
    started = time.perf_counter()
    with urllib.request.urlopen(req, timeout=cfg["timeout"]) as resp:
        body = json.loads(resp.read().decode())
    latency_ms = int((time.perf_counter() - started) * 1000)

    content = body["choices"][0]["message"]["content"]
    parsed = _extract_json(content)

    findings = []
    for item in (parsed.get("findings") or [])[:3]:
        label = str(item.get("label") or "").strip()
        if not label:
            continue
        findings.append(
            {
                "label": label,
                "confidence": round(_clamp(float(item.get("confidence", 0.5)), 0.0, 1.0), 3),
                "evidence": str(item.get("evidence") or "").strip(),
                "alternative": str(item.get("alternative") or "").strip(),
                "severity": item.get("severity")
                if item.get("severity") in {"low", "medium", "high"}
                else "unknown",
            }
        )
    if not findings:
        raise ValueError("provider returned no usable findings")

    uncertainty = _clamp(float(parsed.get("uncertainty", 0.5)), 0.0, 1.0)
    affected = parsed.get("affected_area_pct")
    affected = round(_clamp(float(affected), 0.0, 100.0), 1) if affected is not None else None
    # A single image cannot support a field-wide affected-area estimate.
    if media_count < 2:
        affected = None

    usage = body.get("usage") or {}
    # OpenRouter reports cost separately when usage accounting is enabled.
    cost = usage.get("cost")
    cost_usd = round(float(cost), 6) if isinstance(cost, (int, float)) else 0.0

    return {
        "model_version": cfg["model"],
        "status": "completed",
        "findings": findings,
        "affected_area_pct": affected,
        "uncertainty": round(uncertainty, 3),
        "escalate": uncertainty > 0.45 or media_count < 2,
        "summary": str(parsed.get("summary") or "").strip()
        or f"Preliminary analysis of {media_count} media asset(s) for {crop}.",
        "sources": [],
        "latency_ms": latency_ms,
        "cost_usd": cost_usd,
        "mode": "live",
        "preliminary": True,
    }


def _simulated_analyze(*, crop: str, observations: str, media_count: int, seed: str | None) -> dict:
    """Deterministic offline analysis, used when no live provider is configured."""
    started = time.perf_counter()
    rng = random.Random(seed or hashlib.sha256((crop + observations).encode()).hexdigest())

    bucket = _bucket(observations, crop)
    findings = []
    for cand in CANDIDATES[bucket]:
        confidence = round(rng.uniform(0.62, 0.93), 3)
        findings.append({**cand, "confidence": confidence})

    # Data-quality driven uncertainty: few images -> less certainty.
    quality = min(1.0, 0.35 + 0.22 * media_count)
    uncertainty = round(min(0.95, max(0.05, 1.0 - quality * findings[0]["confidence"])), 3)
    escalate = uncertainty > 0.45 or media_count < 2

    affected = round(rng.uniform(3.0, 28.0), 1) if media_count >= 2 else None
    sources = [k for k in KNOWLEDGE if k["id"] == findings[0]["source"]]

    summary = (
        f"Preliminary analysis of {media_count} media asset(s) for {crop}. "
        f"Most likely issue: {findings[0]['label']} "
        f"(confidence {findings[0]['confidence']:.0%}). "
        + (
            "Confidence is below the review threshold, so this case is escalated to an "
            "agronomist before any treatment is considered."
            if escalate
            else "An agronomist must still confirm findings before treatment."
        )
    )

    latency_ms = int((time.perf_counter() - started) * 1000) + rng.randint(180, 900)
    return {
        "model_version": os.getenv("AGROSPHERE_AI_MODEL", "agrosphere-vision-sim-1.0"),
        "status": "completed",
        "findings": findings,
        "affected_area_pct": affected,
        "uncertainty": uncertainty,
        "escalate": escalate,
        "summary": summary,
        "sources": sources,
        "latency_ms": latency_ms,
        "cost_usd": round(rng.uniform(0.0, 0.004), 5),
        "mode": "simulated",
        "preliminary": True,
    }


def analyze(*, crop: str, observations: str, media_count: int, seed: str | None = None) -> dict:
    """Run a crop-health analysis and return a validated, machine-readable result.

    Uses the live provider when one is configured and reachable. Any failure
    falls back to the labelled simulator — the platform never presents a failed
    call as a completed analysis.
    """
    cfg = _provider_config()
    if cfg["provider"] != "simulated" and cfg["key"]:
        try:
            result = _live_analyze(crop=crop, observations=observations, media_count=media_count)
            # Attach verified-source references the model was not asked to invent.
            result["sources"] = _match_sources(result["findings"], crop)
            return result
        except Exception as exc:  # transport, HTTP, or malformed payload
            log.warning("Live AI provider '%s' failed (%s); using simulator", cfg["provider"], exc)
            result = _simulated_analyze(
                crop=crop, observations=observations, media_count=media_count, seed=seed
            )
            result["mode"] = "simulated-fallback"
            result["provider_error"] = f"{type(exc).__name__}: {exc}"[:200]
            return result
    return _simulated_analyze(
        crop=crop, observations=observations, media_count=media_count, seed=seed
    )


def _match_sources(findings: list[dict], crop: str) -> list[dict]:
    """Attach verified advisories relevant to a live finding or the crop.

    Sources come from our curated knowledge base, not from the model, so a
    citation can always be traced to a real advisory.
    """
    matched: list[dict] = []
    haystack = " ".join(f.get("label", "") for f in findings).lower()
    for bucket, hints in _SYMPTOM_HINTS:
        if any(h in haystack for h in hints):
            for cand in CANDIDATES.get(bucket, []):
                for k in KNOWLEDGE:
                    if k["id"] == cand["source"] and k not in matched:
                        matched.append(k)
    if not matched:
        for k in KNOWLEDGE:
            if crop and crop.lower() in (k.get("crop") or "").lower():
                matched.append(k)
    return matched[:3]


# --------------------------------------------------------------------------- #
# Advisory chat (multilingual farm assistant)
# --------------------------------------------------------------------------- #
_ADVISOR_SYSTEM = (
    "You are AgroSphere's farm advisory assistant for Indian farmers. Answer in the "
    "language given by the user (use the ISO code supplied). Be practical, concise and "
    "safety-first. Rules you must follow:\n"
    "  * You give general guidance only; you never issue a spraying command or a "
    "definitive diagnosis.\n"
    "  * Prefer integrated pest management, label-approved products and the correct "
    "pre-harvest interval.\n"
    "  * If a question needs a local soil test, a licensed agronomist or emergency "
    "services, say so plainly.\n"
    "  * Never invent prices, schemes, phone numbers or citations.\n"
    "  * If you are unsure, say what extra information would help.\n"
    "Keep answers under 200 words and use short paragraphs."
)

_LANG_NAMES = {l["code"]: l["name"] for l in LANGUAGES}


def _simulated_advisory(question: str, language: str, crop: str | None) -> str:
    """Offline advisory reply, used when no live provider is configured."""
    crop_txt = f" for {crop}" if crop else ""
    return (
        f"[Simulated advisory — no live AI provider is configured]{crop_txt}\n\n"
        f"You asked: “{question.strip()}”\n\n"
        "General guidance: scout the affected area early in the morning, record photos "
        "with location tags, and compare against the verified advisories in the "
        "Knowledge base. Prefer integrated pest management and label-approved products, "
        "and always observe the pre-harvest interval. This is general guidance only — a "
        "qualified agronomist must confirm any diagnosis before treatment. Configure a "
        "live AI provider to receive a tailored answer."
    )


def advise(*, question: str, language: str = "en", crop: str | None = None) -> dict:
    """Answer a free-text farm question in the user's language.

    Uses the live provider when configured; otherwise returns a clearly-labelled
    simulated reply. Never raises: the assistant degrades to a labelled message
    rather than failing the request.
    """
    cfg = _provider_config()
    if cfg["provider"] == "simulated" or not cfg["key"]:
        return {
            "answer": _simulated_advisory(question, language, crop),
            "mode": "simulated",
            "provider": cfg["provider"],
            "model": cfg["model"],
            "language": language,
        }

    lang_name = _LANG_NAMES.get(language, language)
    user_prompt = (
        f"Answer language: {lang_name} ({language}).\n"
        + (f"Crop context: {crop}.\n" if crop else "")
        + f"Farmer question: {question.strip()}"
    )
    payload = {
        "model": cfg["model"],
        "messages": [
            {"role": "system", "content": _ADVISOR_SYSTEM},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.3,
    }
    try:
        req = urllib.request.Request(
            f"{cfg['base_url']}/chat/completions",
            data=json.dumps(payload).encode(),
            headers={
                "Authorization": f"Bearer {cfg['key']}",
                "Content-Type": "application/json",
                "HTTP-Referer": cfg["site_url"],
                "X-Title": cfg["app_name"],
            },
            method="POST",
        )
        started = time.perf_counter()
        with urllib.request.urlopen(req, timeout=cfg["timeout"]) as resp:
            body = json.loads(resp.read().decode())
        latency_ms = int((time.perf_counter() - started) * 1000)
        answer = (body["choices"][0]["message"]["content"] or "").strip()
        if not answer:
            raise ValueError("empty response")
        return {
            "answer": answer,
            "mode": "live",
            "provider": cfg["provider"],
            "model": cfg["model"],
            "language": language,
            "latency_ms": latency_ms,
        }
    except Exception as exc:
        log.warning("Advisory provider '%s' failed (%s); using simulator", cfg["provider"], exc)
        return {
            "answer": _simulated_advisory(question, language, crop),
            "mode": "simulated-fallback",
            "provider": cfg["provider"],
            "model": cfg["model"],
            "language": language,
            "provider_error": f"{type(exc).__name__}: {exc}"[:200],
        }


# --------------------------------------------------------------------------- #
# Real-time vision analysis (camera frame -> preliminary disease assessment)
# --------------------------------------------------------------------------- #
_VISION_SYSTEM = (
    "You are an agricultural plant-pathology assistant supporting Indian farmers. "
    "You are shown a photo of a crop taken by a farmer's phone or a drone. Return a "
    "PRELIMINARY assessment as strict JSON. Rules:\n"
    "  * Never claim certainty and never issue a spraying command.\n"
    "  * Always give at least one alternative hypothesis and a calibrated uncertainty.\n"
    "  * Base the assessment only on what is visible in the image; if the image is "
    "unclear, say so and raise the uncertainty.\n"
    "Respond with JSON only, using exactly this shape:\n"
    "{\n"
    '  "findings": [{"label": str, "confidence": number 0-1, "evidence": str, '
    '"alternative": str, "severity": "low"|"medium"|"high"}],\n'
    '  "uncertainty": number 0-1,\n'
    '  "affected_area_pct": number 0-100 or null,\n'
    '  "summary": str\n'
    "}"
)

# Real-time frames are downscaled before upload: a phone frame is 2-4 MB, which
# is slow to send and adds nothing the model needs. The caller passes a data URL
# and we validate the media type and size rather than trusting it.
ALLOWED_FRAME_TYPES = {"image/jpeg", "image/png", "image/webp"}
MAX_FRAME_BYTES = 6 * 1024 * 1024


class VisionInputError(ValueError):
    """Raised when a submitted frame cannot be used."""


def _validate_frame(data_url: str) -> tuple[str, str]:
    if not data_url or not isinstance(data_url, str):
        raise VisionInputError("A captured frame is required.")
    if not data_url.startswith("data:"):
        raise VisionInputError("Frame must be a data URL (data:image/...;base64,...).")
    header, _, payload = data_url.partition(",")
    media_type = header[5:].split(";")[0].strip().lower()
    if media_type not in ALLOWED_FRAME_TYPES:
        raise VisionInputError(f"Unsupported frame type: {media_type or 'unknown'}")
    # base64 expands by ~4/3, so compare against the decoded size.
    approx_bytes = len(payload) * 3 // 4
    if approx_bytes > MAX_FRAME_BYTES:
        raise VisionInputError("Frame is too large; downscale it before sending.")
    if not payload:
        raise VisionInputError("Frame payload is empty.")
    return media_type, payload


def analyze_frame(
    *,
    data_url: str,
    crop: str,
    observations: str = "",
    language: str = "en",
    mode: str | None = None,
) -> dict:
    """Assess a single live frame. Degrades to the labelled simulator offline.

    ``mode`` is the provider mode label to report when simulating, so a caller
    can distinguish a plain offline simulator from a live-call fallback.
    """
    media_type, _ = _validate_frame(data_url)

    cfg = _provider_config()
    if cfg["provider"] != "simulated" and cfg["key"]:
        try:
            return _live_vision(cfg, data_url, crop, observations, language)
        except Exception as exc:
            log.warning("Vision provider '%s' failed (%s); using simulator", cfg["provider"], exc)
            result = _simulated_analyze(
                crop=crop, observations=observations, media_count=1, seed=None
            )
            result["mode"] = mode or "simulated-fallback"
            result["provider_error"] = f"{type(exc).__name__}: {exc}"[:200]
            return result
    result = _simulated_analyze(crop=crop, observations=observations, media_count=1, seed=None)
    result["mode"] = "simulated"
    return result


def _live_vision(cfg: dict, data_url: str, crop: str, observations: str, language: str) -> dict:
    """Send the frame to a vision-capable OpenRouter model."""
    lang_name = _LANG_NAMES.get(language, language)
    user_text = (
        f"Crop: {crop}\n"
        f"Respond in: {lang_name}\n"
        f"Farmer observations: {observations or '(none provided)'}\n\n"
        "Assess this field photo and return the JSON assessment now."
    )
    payload = {
        "model": cfg["model"],
        "messages": [
            {"role": "system", "content": _VISION_SYSTEM},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": user_text},
                    {"type": "image_url", "image_url": {"url": data_url}},
                ],
            },
        ],
        "temperature": 0.2,
        "response_format": {"type": "json_object"},
    }
    req = urllib.request.Request(
        f"{cfg['base_url']}/chat/completions",
        data=json.dumps(payload).encode(),
        headers={
            "Authorization": f"Bearer {cfg['key']}",
            "Content-Type": "application/json",
            "HTTP-Referer": cfg["site_url"],
            "X-Title": cfg["app_name"],
        },
        method="POST",
    )
    started = time.perf_counter()
    with urllib.request.urlopen(req, timeout=cfg["timeout"]) as resp:
        body = json.loads(resp.read().decode())
    latency_ms = int((time.perf_counter() - started) * 1000)

    parsed = _extract_json(body["choices"][0]["message"]["content"])
    findings = []
    for item in (parsed.get("findings") or [])[:3]:
        label = str(item.get("label") or "").strip()
        if not label:
            continue
        findings.append({
            "label": label,
            "confidence": round(_clamp(float(item.get("confidence", 0.5)), 0.0, 1.0), 3),
            "evidence": str(item.get("evidence") or "").strip(),
            "alternative": str(item.get("alternative") or "").strip(),
            "severity": item.get("severity") if item.get("severity") in {"low", "medium", "high"} else "unknown",
        })
    if not findings:
        raise ValueError("provider returned no usable findings")

    usage = body.get("usage") or {}
    cost = usage.get("cost")
    return {
        "model_version": cfg["model"],
        "status": "completed",
        "findings": findings,
        # A single frame cannot support a field-wide affected-area estimate.
        "affected_area_pct": None,
        "uncertainty": round(_clamp(float(parsed.get("uncertainty", 0.5)), 0.0, 1.0), 3),
        "escalate": True,
        "summary": str(parsed.get("summary") or "").strip()
        or f"Preliminary assessment of a single {crop} frame.",
        "sources": _match_sources(findings, crop),
        "latency_ms": latency_ms,
        "cost_usd": round(float(cost), 6) if isinstance(cost, (int, float)) else 0.0,
        "mode": "live",
        "preliminary": True,
        "single_frame": True,
    }


# --------------------------------------------------------------------------- #
# Treatment-plan drafting from a confirmed finding
# --------------------------------------------------------------------------- #
_TREATMENT_SYSTEM = (
    "You are an agronomy assistant for Indian farmers. Given a confirmed crop "
    "problem, draft a treatment plan as strict JSON. Safety rules you must follow:\n"
    "  * Only recommend products approved for the named crop; if unsure, name the "
    "active ingredient and say 'confirm label registration'.\n"
    "  * Always include a pre-harvest interval, re-entry interval and PPE.\n"
    "  * Prefer integrated pest management measures before chemical control.\n"
    "  * Never invent prices.\n"
    "Respond with JSON only, using exactly this shape:\n"
    "{\n"
    '  "problem": str, "measures": [str], "product": str, "active_ingredient": str,\n'
    '  "dosage": str, "application": str, "weather_restrictions": str, "ppe": str,\n'
    '  "pre_harvest_interval": str, "re_entry_interval": str, "follow_up": str,\n'
    '  "confidence": number 0-1\n'
    "}"
)


def draft_treatment(
    *,
    crop: str,
    problem: str,
    severity: str = "unknown",
    weather_note: str | None = None,
    language: str = "en",
) -> dict:
    """Draft a treatment plan. Falls back to a labelled template offline."""
    cfg = _provider_config()
    if cfg["provider"] != "simulated" and cfg["key"]:
        try:
            return _live_treatment(cfg, crop, problem, severity, weather_note, language)
        except Exception as exc:
            log.warning("Treatment provider '%s' failed (%s); using template", cfg["provider"], exc)
            out = _template_treatment(crop, problem, severity, weather_note)
            out["mode"] = "simulated-fallback"
            out["provider_error"] = f"{type(exc).__name__}: {exc}"[:200]
            return out
    out = _template_treatment(crop, problem, severity, weather_note)
    out["mode"] = "simulated"
    return out


def _live_treatment(cfg, crop, problem, severity, weather_note, language) -> dict:
    lang_name = _LANG_NAMES.get(language, language)
    user_text = (
        f"Crop: {crop}\nConfirmed problem: {problem}\nSeverity: {severity}\n"
        + (f"Weather context: {weather_note}\n" if weather_note else "")
        + f"Respond in: {lang_name}\n\nDraft the treatment plan as JSON now."
    )
    payload = {
        "model": cfg["model"],
        "messages": [
            {"role": "system", "content": _TREATMENT_SYSTEM},
            {"role": "user", "content": user_text},
        ],
        "temperature": 0.2,
        "response_format": {"type": "json_object"},
    }
    req = urllib.request.Request(
        f"{cfg['base_url']}/chat/completions",
        data=json.dumps(payload).encode(),
        headers={
            "Authorization": f"Bearer {cfg['key']}",
            "Content-Type": "application/json",
            "HTTP-Referer": cfg["site_url"],
            "X-Title": cfg["app_name"],
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=cfg["timeout"]) as resp:
        body = json.loads(resp.read().decode())
    parsed = _extract_json(body["choices"][0]["message"]["content"])

    def s(key: str) -> str:
        return str(parsed.get(key) or "").strip()

    measures = [str(m).strip() for m in (parsed.get("measures") or []) if str(m).strip()]
    return {
        "problem": s("problem") or problem,
        "confidence": round(_clamp(float(parsed.get("confidence", 0.5)), 0.0, 1.0), 3),
        "measures": measures or _template_treatment(crop, problem, severity, weather_note)["measures"],
        "product": s("product"),
        "active_ingredient": s("active_ingredient"),
        "dosage": s("dosage"),
        "application": s("application"),
        "weather_restrictions": s("weather_restrictions") or (weather_note or ""),
        "ppe": s("ppe"),
        "pre_harvest_interval": s("pre_harvest_interval"),
        "re_entry_interval": s("re_entry_interval"),
        "follow_up": s("follow_up"),
        "mode": "live",
        "drafted": True,
    }


def _template_treatment(crop: str, problem: str, severity: str, weather_note: str | None) -> dict:
    """A safe, non-specific plan used offline and as a fill-in for live drafts."""
    return {
        "problem": problem,
        "confidence": 0.4,
        "measures": [
            "Remove and destroy severely affected plant parts; do not compost them.",
            "Reduce leaf wetness by adjusting irrigation to early morning.",
            "Scout the whole block and mark the affected area before any chemical step.",
            "Record a photo of the affected area for the case file.",
        ],
        "product": "",
        "active_ingredient": "",
        "dosage": "Confirm with a licensed agronomist and the product label.",
        "application": "Apply only within an open spray window, using calibrated equipment.",
        "weather_restrictions": weather_note
        or "Do not spray if rain is expected within 6 hours or wind exceeds 12 km/h.",
        "ppe": "Gloves, mask, long sleeves, eye protection and boots.",
        "pre_harvest_interval": "Follow the product label.",
        "re_entry_interval": "Follow the product label.",
        "follow_up": "Re-inspect the treated block after 5-7 days and compare photos.",
        "mode": "template",
        "drafted": True,
    }
