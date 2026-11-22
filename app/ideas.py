"""Turn a Gemini JSON response into one ambient video idea."""

from __future__ import annotations

import json
from typing import Literal

from pydantic import BaseModel, Field

PURPOSES = ("sleep", "focus", "meditation", "rest")
SOUND_PROFILES = (
    "soft_rain",
    "heavy_rain",
    "ocean",
    "stream",
    "wind",
    "brown_noise",
    "pink_noise",
    "white_noise",
    "fireplace",
)
SOUND_LABELS = {
    "soft_rain": "Soft rain",
    "heavy_rain": "Heavy rain",
    "ocean": "Ocean waves",
    "stream": "A flowing stream",
    "wind": "Wind",
    "brown_noise": "Brown noise",
    "pink_noise": "Pink noise",
    "white_noise": "White noise",
    "fireplace": "Fireplace crackle",
}
TEXT_MODEL = "gemini-3.8-flash"
TITLE_LIMIT = 100
DESCRIPTION_LIMIT = 4500
TAG_LIMIT = 480

Purpose = Literal["sleep", "focus", "meditation", "rest"]
SoundProfile = Literal[
    "soft_rain",
    "heavy_rain",
    "ocean",
    "stream",
    "wind",
    "brown_noise",
    "pink_noise",
    "white_noise",
    "fireplace",
]


class VideoIdea(BaseModel):
    purpose: Purpose = Field(description="Who the video is for: sleep, focus, meditation, or rest.")
    title: str = Field(description="A calm YouTube title under 100 characters. No clickbait and no all-caps.")
    description: str = Field(
        description="Two to four sentences for the YouTube description. Invite background listening. Do not claim to cure, treat, or diagnose anything."
    )
    tags: list[str] = Field(description="Eight to fifteen short search tags.")
    scene_summary: str = Field(description="One plain sentence describing the picture.")
    scene_prompt: str = Field(
        description="A prompt for one photorealistic 16:9 still photograph. No text, logos, or people. The picture does not animate."
    )
    sound_profile: SoundProfile = Field(
        description="One sound from the allowed list. Rain, ocean, stream, wind, and fire are looped field recordings. Brown, pink, and white noise are synthesized. Do not describe music with a melody."
    )


def clean_title(title: str) -> str:
    text = " ".join(title.split())
    if len(text) <= TITLE_LIMIT:
        return text
    return text[: TITLE_LIMIT - 3].rstrip() + "..."


def clean_description(description: str) -> str:
    text = "\n".join(line.rstrip() for line in description.strip().splitlines()).strip()
    if len(text) <= DESCRIPTION_LIMIT:
        return text
    return text[: DESCRIPTION_LIMIT - 3].rstrip() + "..."


def normalize_tags(tags: list[str]) -> list[str]:
    cleaned: list[str] = []
    seen: set[str] = set()
    total = 0
    for tag in tags:
        item = " ".join(str(tag).replace(",", " ").split())[:30]
        key = item.lower()
        if not item or key in seen:
            continue
        if total + len(item) > TAG_LIMIT or len(cleaned) >= 15:
            break
        cleaned.append(item)
        seen.add(key)
        total += len(item)
    return cleaned


def append_length(description: str, hours: int) -> str:
    line = f"Length: {hours} {'hour' if hours == 1 else 'hours'}."
    combined = f"{description.rstrip()}\n\n{line}"
    if len(combined) <= 5000:
        return combined
    room = 5000 - len(line) - 2
    return f"{description.rstrip()[:room].rstrip()}\n\n{line}"


def parse_idea(payload: str | dict) -> VideoIdea:
    if isinstance(payload, str):
        text = payload.strip()
        if text.startswith("```"):
            lines = [line for line in text.splitlines() if not line.strip().startswith("```")]
            text = "\n".join(lines).strip()
        data = json.loads(text)
    else:
        data = payload
    idea = VideoIdea.model_validate(data)
    summary = " ".join(idea.scene_summary.split()) or " ".join(idea.scene_prompt.split())
    cleaned = idea.model_copy(
        update={
            "title": clean_title(idea.title),
            "description": clean_description(idea.description),
            "tags": normalize_tags(idea.tags),
            "scene_summary": summary,
            "scene_prompt": " ".join(idea.scene_prompt.split()),
        }
    )
    if not cleaned.title or not cleaned.scene_prompt:
        raise ValueError("The idea was missing a title or a scene.")
    return cleaned


def idea_prompt(avoid_titles: list[str] | None = None) -> str:
    avoided = ", ".join(avoid_titles[:12]) if avoid_titles else "none"
    profiles = ", ".join(SOUND_PROFILES)
    return f"""
Propose one original long-form YouTube ambient video that a person would leave playing for hours.
The picture is a single nearly still photograph. The sound is a short field recording looped for the whole video, except brown, pink, and white noise, which are synthesized. Do not describe animation, lyrics, or a melody.
Choose a purpose that is in demand for long listening: sleep, focus, meditation, or rest.
Choose sound_profile from exactly this list: {profiles}.
The scene should be something people actually play in the background, such as rain, water, wind, a quiet room, or a fire.
Do not claim the video cures, treats, or diagnoses insomnia, anxiety, or any condition. Describe it as background listening.
Avoid these titles: {avoided}.
""".strip()


class ShortBatch(BaseModel):
    ideas: list[VideoIdea] = Field(description="Exactly ten different Shorts.")


SHORT_COUNT = 10
CALM_PURPOSES = ("focus", "meditation", "rest")


def as_short(idea: VideoIdea) -> VideoIdea:
    """Mark a calm or focus idea as a YouTube Short without dropping the label."""
    suffix = " #Shorts"
    title = " ".join(idea.title.split())
    if "#shorts" not in title.lower():
        room = TITLE_LIMIT - len(suffix)
        title = title[:room].rstrip() + suffix
    title = clean_title(title)
    tags = list(idea.tags)
    if not any(tag.lower() == "shorts" for tag in tags):
        tags.append("Shorts")
    description = idea.description.strip()
    if "#shorts" not in description.lower():
        description = f"{description}\n\n#Shorts"
    return idea.model_copy(
        update={
            "title": title,
            "tags": normalize_tags(tags),
            "description": clean_description(description),
        }
    )


def shorts_prompt(avoid_titles: list[str] | None = None) -> str:
    avoided = ", ".join(avoid_titles[:20]) if avoid_titles else "none"
    profiles = "soft_rain, ocean, stream, wind, brown_noise, pink_noise, fireplace"
    return f"""
Propose exactly {SHORT_COUNT} different YouTube Shorts for calm and focus.
Each Short is one nearly still vertical photograph plus a seamless ambient sound. No animation, lyrics, or melody.
purpose must be one of: focus, meditation, rest.
sound_profile must be one of: {profiles}.
Every title must be distinct and about calm focus, quiet work, or restful concentration.
scene_prompt must describe one photorealistic vertical 9:16 photograph with no text, logos, or people.
Do not claim the video cures, treats, or diagnoses anything.
Avoid these titles: {avoided}.
""".strip()


def parse_short_batch(payload: str | dict | list) -> list[VideoIdea]:
    if isinstance(payload, str):
        text = payload.strip()
        if text.startswith("```"):
            lines = [line for line in text.splitlines() if not line.strip().startswith("```")]
            text = "\n".join(lines).strip()
        data = json.loads(text)
    else:
        data = payload
    raw_ideas = data if isinstance(data, list) else data.get("ideas", [])
    ideas = [as_short(parse_idea(item)) for item in raw_ideas]
    unique: list[VideoIdea] = []
    seen: set[str] = set()
    for idea in ideas:
        key = idea.title.lower()
        if key in seen:
            continue
        if idea.purpose not in CALM_PURPOSES:
            continue
        seen.add(key)
        unique.append(idea)
    if len(unique) < SHORT_COUNT:
        raise ValueError(f"Expected {SHORT_COUNT} calm and focus Shorts, got {len(unique)}.")
    return unique[:SHORT_COUNT]


def generate_short_ideas(client=None, avoid_titles: list[str] | None = None) -> list[VideoIdea]:
    from app.config import preview_mode

    if preview_mode():
        from app.preview import preview_shorts

        return parse_short_batch([idea.model_dump() for idea in preview_shorts()])
    if client is None:
        from app.config import gemini_api_key

        if not gemini_api_key():
            raise RuntimeError("Set GEMINI_API_KEY in a .env file. Create a key in Google AI Studio.")
        from google import genai

        client = genai.Client(api_key=gemini_api_key())
    interaction = client.interactions.create(
        model=TEXT_MODEL,
        input=shorts_prompt(avoid_titles),
        response_format={
            "type": "text",
            "mime_type": "application/json",
            "schema": ShortBatch.model_json_schema(),
        },
    )
    text = interaction.output_text or ""
    if not text.strip():
        raise RuntimeError("Gemini returned no Shorts.")
    return parse_short_batch(text)


def to_public(idea: VideoIdea) -> dict:
    data = idea.model_dump()
    data["sound_label"] = SOUND_LABELS[idea.sound_profile]
    return data


def generate_idea(client=None, avoid_titles: list[str] | None = None) -> VideoIdea:
    from app.config import preview_mode

    if preview_mode():
        from app.preview import next_preview_idea

        return next_preview_idea(avoid_titles)
    if client is None:
        from app.config import gemini_api_key

        if not gemini_api_key():
            raise RuntimeError("Set GEMINI_API_KEY in a .env file. Create a key in Google AI Studio.")
        from google import genai

        client = genai.Client(api_key=gemini_api_key())
    interaction = client.interactions.create(
        model=TEXT_MODEL,
        input=idea_prompt(avoid_titles),
        response_format={
            "type": "text",
            "mime_type": "application/json",
            "schema": VideoIdea.model_json_schema(),
        },
    )
    text = interaction.output_text or ""
    if not text.strip():
        raise RuntimeError("Gemini returned an empty idea.")
    return parse_idea(text)
