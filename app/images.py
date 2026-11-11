"""Gemini stills, fitted to a 16:9 frame."""

from __future__ import annotations

import base64
from pathlib import Path

from PIL import Image

from app.config import gemini_api_key, preview_mode

IMAGE_MODEL = "gemini-nano-banana-2.1"
FRAME_SIZE = (1920, 1080)
THUMB_SIZE = (1280, 720)


def image_prompt(scene_prompt: str) -> str:
    return (
        "Create one photorealistic photograph, 16:9, calm and quiet, "
        "suitable as a nearly motionless background for a long ambient video. "
        "No text, no letters, no logos, no watermarks, no people, no faces. "
        + " ".join(scene_prompt.split())
    )


def generate_still(client, scene_prompt: str, dest: Path) -> Path:
    if preview_mode():
        from app.preview import draw_preview_still

        return draw_preview_still(dest, scene_prompt)
    if client is None:
        if not gemini_api_key():
            raise RuntimeError("Set GEMINI_API_KEY in a .env file. Create a key in Google AI Studio.")
        from google import genai

        client = genai.Client(api_key=gemini_api_key())
    interaction = client.interactions.create(
        model=IMAGE_MODEL,
        input=image_prompt(scene_prompt),
        response_format={
            "type": "image",
            "mime_type": "image/png",
            "aspect_ratio": "16:9",
            "image_size": "1K",
        },
    )
    image = getattr(interaction, "output_image", None)
    data = getattr(image, "data", None) if image is not None else None
    if not data:
        raise RuntimeError("Gemini did not return an image.")
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(base64.b64decode(data))
    return dest


def fit_frame(src: Path, dest: Path, size: tuple[int, int] = FRAME_SIZE) -> Path:
    image = Image.open(src).convert("RGB")
    target_ratio = size[0] / size[1]
    ratio = image.width / image.height
    if ratio > target_ratio:
        new_width = int(image.height * target_ratio)
        left = (image.width - new_width) // 2
        image = image.crop((left, 0, left + new_width, image.height))
    else:
        new_height = int(image.width / target_ratio)
        top = (image.height - new_height) // 2
        image = image.crop((0, top, image.width, top + new_height))
    image = image.resize(size, Image.Resampling.LANCZOS)
    dest.parent.mkdir(parents=True, exist_ok=True)
    image.save(dest, "PNG")
    return dest


def write_thumbnail(src: Path, dest: Path) -> Path:
    image = Image.open(src).convert("RGB")
    image.thumbnail(THUMB_SIZE, Image.Resampling.LANCZOS)
    canvas = Image.new("RGB", THUMB_SIZE, (0, 0, 0))
    left = (THUMB_SIZE[0] - image.width) // 2
    top = (THUMB_SIZE[1] - image.height) // 2
    canvas.paste(image, (left, top))
    dest.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(dest, "JPEG", quality=85)
    return dest
