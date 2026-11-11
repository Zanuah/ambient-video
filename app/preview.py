"""Local ideas and a drawn still, used when AMBIENT_PREVIEW=1."""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

from app.ideas import parse_idea

_IDEAS = [
    parse_idea(
        {
            "purpose": "sleep",
            "title": "Rain on a quiet beach for sleep",
            "description": "Soft rain and a dim shoreline for background listening while you rest. Leave it playing and turn the picture down if you like.",
            "tags": ["rain", "sleep", "beach", "ambient", "relaxation"],
            "scene_summary": "A dark beach with rain on the wet sand.",
            "scene_prompt": "A dark wet beach at night, gentle surf in the distance, rain on the sand, no people, photorealistic.",
            "sound_profile": "soft_rain",
        }
    ),
    parse_idea(
        {
            "purpose": "focus",
            "title": "Brown noise for a deep work hour",
            "description": "A steady brown-noise bed for background listening while you concentrate. No melody and no speech.",
            "tags": ["brown noise", "focus", "study", "ambient"],
            "scene_summary": "A dim wooden desk beside a rainy window.",
            "scene_prompt": "A dim wooden desk by a rainy window, warm lamp, empty chair, photorealistic, no text.",
            "sound_profile": "brown_noise",
        }
    ),
    parse_idea(
        {
            "purpose": "meditation",
            "title": "Fireplace light for quiet sitting",
            "description": "A low fireplace crackle for background listening while you sit quietly. This is not a medical or therapeutic claim.",
            "tags": ["fireplace", "meditation", "ambient", "crackling fire"],
            "scene_summary": "A small fire in a dark stone hearth.",
            "scene_prompt": "A small fire in a dark stone hearth, warm glow, no people, photorealistic, no text.",
            "sound_profile": "fireplace",
        }
    ),
]


def next_preview_idea(avoid_titles: list[str] | None = None):
    avoided = {title.lower() for title in (avoid_titles or [])}
    for idea in _IDEAS:
        if idea.title.lower() not in avoided:
            return idea
    return _IDEAS[0]


def draw_preview_still(dest: Path, scene_prompt: str) -> Path:
    """A calm gradient so the slow zoom has something to move across."""
    width, height = 1920, 1080
    image = Image.new("RGB", (width, height))
    draw = ImageDraw.Draw(image)
    for y in range(height):
        blend = y / (height - 1)
        red = int(18 + 70 * blend)
        green = int(36 + 40 * blend)
        blue = int(62 - 20 * blend)
        draw.line([(0, y), (width, y)], fill=(red, green, blue))
    # A soft horizon so the zoom is visible in a smoke test.
    draw.ellipse((700, 620, 1220, 860), fill=(120, 96, 70))
    dest.parent.mkdir(parents=True, exist_ok=True)
    image.save(dest, "PNG")
    return dest
