"""Paths and environment for the local app."""

from __future__ import annotations

import os
import shutil
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")


def output_dir() -> Path:
    return Path(os.environ.get("AMBIENT_OUTPUT", ROOT / "output"))


def data_dir() -> Path:
    return Path(os.environ.get("AMBIENT_DATA", ROOT / "data"))


def client_secret_path() -> Path:
    return Path(os.environ.get("YOUTUBE_CLIENT_SECRET", ROOT / "client_secret.json"))


def token_path() -> Path:
    return Path(os.environ.get("YOUTUBE_TOKEN", ROOT / "token.json"))


def gemini_api_key() -> str | None:
    key = os.environ.get("GEMINI_API_KEY", "").strip()
    return key or None


def preview_mode() -> bool:
    return os.environ.get("AMBIENT_PREVIEW", "").strip() == "1"


def find_ffmpeg() -> str | None:
    override = os.environ.get("FFMPEG", "").strip()
    if override and Path(override).exists():
        return override
    found = shutil.which("ffmpeg")
    if found:
        return found
    packages = Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft" / "WinGet" / "Packages"
    if not packages.exists():
        return None
    matches = sorted(packages.glob("Gyan.FFmpeg*/ffmpeg-*/bin/ffmpeg.exe"))
    if matches:
        return str(matches[-1])
    return None


def find_ffprobe() -> str | None:
    ffmpeg = find_ffmpeg()
    if not ffmpeg:
        return None
    sibling = Path(ffmpeg).with_name("ffprobe.exe" if os.name == "nt" else "ffprobe")
    if sibling.exists():
        return str(sibling)
    return shutil.which("ffprobe")
