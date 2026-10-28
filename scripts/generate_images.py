"""Generate AgroSphere module artwork with Pollinations (free, no API key).

Every module of the platform gets a distinct, good-looking generated image.
The script is idempotent: an existing file is skipped unless --force is passed.
"""

from __future__ import annotations

import argparse
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

OUT_DIR = Path(__file__).resolve().parents[1] / "frontend" / "assets" / "images"

BASE_STYLE = (
    "professional agricultural technology editorial photograph, premium quality, "
    "soft natural golden-hour light, shallow depth of field, cinematic color grade, "
    "ultra detailed, 8k, no text, no watermark, no logo"
)

# name -> (prompt, width, height)
IMAGES: dict[str, tuple[str, int, int]] = {
    # Brand / hero
    "hero": (
        "sweeping aerial view of lush green terraced farmland in India with healthy crop rows "
        "and a drone flying above, sunrise haze, vibrant emerald and gold tones",
        1600,
        900,
    ),
    "logo_mark": (
        "minimalist emblem of a wheat sprout fused with a satellite orbit, flat vector, "
        "emerald green and gold gradient on deep charcoal, centered, clean lines",
        512,
        512,
    ),
    # Role dashboards
    "role_farmer": (
        "Indian farmer in a cotton field holding a smartphone showing a crop health app, "
        "warm sunlight, authentic documentary style, hopeful mood",
        1024,
        768,
    ),
    "role_agronomist": (
        "female agronomist in a field examining plant leaves with a magnifying loupe and a "
        "tablet, scientific yet warm, soft morning light",
        1024,
        768,
    ),
    "role_manager": (
        "farm operations manager reviewing crop reports and cost spreadsheets on a tablet in "
        "an open field office, organized and professional, warm tones",
        1024,
        768,
    ),
    "role_drone_operator": (
        "agricultural drone pilot in safety vest preparing an octocopter spray drone on a "
        "farm launch pad at golden hour, technical and heroic",
        1024,
        768,
    ),
    "role_admin": (
        "modern control room with large dashboards showing agricultural analytics maps in "
        "green and amber, sleek, futuristic yet grounded",
        1024,
        768,
    ),
    # Modules
    "module_farm_mapping": (
        "top-down satellite map aesthetic of green farm fields with glowing vector boundary "
        "polygons overlaid, precision agriculture GIS visualization, emerald and cyan",
        1200,
        800,
    ),
    "module_crop_health": (
        "macro photograph of a healthy green crop leaf next to a diseased spotted leaf, "
        "diagnostic split comparison, studio lighting, ultra detailed",
        1200,
        800,
    ),
    "module_ai_analysis": (
        "abstract visualization of an AI neural network scanning a leaf, glowing data nodes "
        "and bounding boxes over a green leaf, deep teal background",
        1200,
        800,
    ),
    "module_treatment": (
        "neatly arranged approved agricultural crop-protection products and a sprayer in a "
        "clean farm shed, safety first, soft light, editorial",
        1200,
        800,
    ),
    "module_approval": (
        "concept of a multi-step approval workflow as glowing connected nodes forming a path "
        "over a subtle field background, green and gold, minimal infographic style",
        1200,
        800,
    ),
    "module_drone_ops": (
        "agricultural spraying drone flying low over a green crop field releasing fine mist, "
        "dynamic action shot, golden hour backlight, ultra detailed",
        1200,
        800,
    ),
    "module_multilingual": (
        "colorful collage of Indian scripts and language letters flowing around a globe with "
        "farm imagery, vibrant, inclusive, artistic",
        1200,
        800,
    ),
    "module_reports": (
        "elegant printed agricultural field report with charts, maps and photos on a wooden "
        "desk beside fresh produce, top-down flat lay, warm light",
        1200,
        800,
    ),
    "module_payments": (
        "clean minimal illustration of digital payment for farm services, rupee coins and a "
        "phone with a checkmark, emerald and gold, flat 3d style",
        1200,
        800,
    ),
    "module_notifications": (
        "abstract notification bells and chat bubbles carrying farm imagery, soft gradient "
        "green background, friendly modern illustration",
        1200,
        800,
    ),
    "module_security": (
        "glowing shield over a farm landscape with subtle circuit patterns, trust and "
        "protection concept, deep green and cyan",
        1200,
        800,
    ),
    "module_analytics": (
        "rich agricultural analytics dashboard visual with line charts, bar charts and a "
        "field health heat map, emerald and amber palette, crisp",
        1200,
        800,
    ),
    "module_database": (
        "abstract glowing database cylinders and connected tables over a subtle field "
        "pattern, technical and clean, green and blue",
        1200,
        800,
    ),
    "module_workflow": (
        "isometric illustration of an end-to-end farm-to-harvest process pipeline with icons "
        "and arrows, green and gold, clean vector",
        1200,
        800,
    ),
    "module_weather": (
        "dramatic monsoon clouds over green Indian farmland with sun breaking through, "
        "weather intelligence mood, cinematic",
        1200,
        800,
    ),
    "module_knowledge": (
        "open agricultural knowledge base with books, plant specimens and a magnifier over "
        "verified sources, scholarly warm light",
        1200,
        800,
    ),
    "module_grievance": (
        "support agent with headset helping a farmer on a video call, empathetic and "
        "professional, bright office with plants",
        1200,
        800,
    ),
    "module_offline": (
        "rural Indian village with a farmer using a phone under a tree, connectivity icon "
        "glowing, warm documentary tone",
        1200,
        800,
    ),
    "module_dark_theme": (
        "moody night-time field illuminated by a drone light and phone screen glow, dark "
        "green and teal, elegant",
        1200,
        800,
    ),
    "module_light_theme": (
        "bright airy morning farm scene with fresh green crops and clear blue sky, crisp and "
        "clean, high key",
        1200,
        800,
    ),
}


def build_url(prompt: str, width: int, height: int, seed: int, model: str) -> str:
    full = f"{prompt}, {BASE_STYLE}"
    params = {
        "width": width,
        "height": height,
        "seed": seed,
        "model": model,
        "nologo": "true",
        "enhance": "false",
    }
    return (
        "https://image.pollinations.ai/prompt/"
        + urllib.parse.quote(full)
        + "?"
        + urllib.parse.urlencode(params)
    )


def fetch(url: str, dest: Path, retries: int = 4) -> bool:
    for attempt in range(1, retries + 1):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "AgroSphere/1.0"})
            with urllib.request.urlopen(req, timeout=120) as resp:
                data = resp.read()
            if len(data) < 5000:
                raise ValueError(f"suspiciously small payload: {len(data)} bytes")
            dest.write_bytes(data)
            return True
        except Exception as exc:  # noqa: BLE001
            print(f"    attempt {attempt}/{retries} failed: {exc}", file=sys.stderr)
            time.sleep(50)
    return False


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true", help="regenerate existing images")
    ap.add_argument("--model", default="flux", help="pollinations model")
    ap.add_argument("--only", nargs="*", help="subset of image names")
    args = ap.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    names = args.only or list(IMAGES)
    ok, failed = 0, []
    for i, name in enumerate(names):
        prompt, w, h = IMAGES[name]
        dest = OUT_DIR / f"{name}.jpg"
        if dest.exists() and not args.force:
            print(f"[skip] {name} ({dest.stat().st_size // 1024} KB)")
            ok += 1
            continue
        seed = 1000 + i * 17
        url = build_url(prompt, w, h, seed, args.model)
        print(f"[gen ] {name} {w}x{h}")
        if fetch(url, dest):
            print(f"       -> {dest.name} {dest.stat().st_size // 1024} KB")
            ok += 1
        else:
            failed.append(name)
        time.sleep(50)

    print(f"\nGenerated/verified {ok}/{len(names)} images in {OUT_DIR}")
    if failed:
        print("Failed:", ", ".join(failed))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
