"""Build a short zooming clip and loop it to the requested length."""

from __future__ import annotations

import subprocess
from pathlib import Path

from app.config import find_ffmpeg

CLIP_SECONDS = 24
WIDTH = 1920
HEIGHT = 1080
ZOOM_AMOUNT = 0.04


def zoom_at(frame: int, frames: int = CLIP_SECONDS, amount: float = ZOOM_AMOUNT) -> float:
    """Ping-pong zoom that starts and ends at 1 so the loop has no jump."""
    import math

    if frames < 2:
        return 1.0
    return 1.0 + amount * math.sin(math.pi * frame / (frames - 1))


def base_clip_command(ffmpeg: str, image: Path, clip: Path, frames: int = CLIP_SECONDS) -> list[str]:
    zoom = f"1+{ZOOM_AMOUNT}*sin(PI*on/{frames - 1})"
    video_filter = (
        f"scale={WIDTH}:{HEIGHT}:force_original_aspect_ratio=increase,"
        f"crop={WIDTH}:{HEIGHT},"
        f"scale={WIDTH * 2}:{HEIGHT * 2},"
        f"zoompan=z='{zoom}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={frames}:s={WIDTH}x{HEIGHT}:fps=1"
    )
    return [
        ffmpeg,
        "-y",
        "-i",
        str(image),
        "-vf",
        video_filter,
        "-frames:v",
        str(frames),
        "-c:v",
        "libx264",
        "-tune",
        "stillimage",
        "-pix_fmt",
        "yuv420p",
        "-g",
        "1",
        "-movflags",
        "+faststart",
        str(clip),
    ]


def assemble_command(ffmpeg: str, clip: Path, wav: Path, output: Path, duration_seconds: float) -> list[str]:
    return [
        ffmpeg,
        "-y",
        "-stream_loop",
        "-1",
        "-i",
        str(clip),
        "-stream_loop",
        "-1",
        "-i",
        str(wav),
        "-t",
        f"{duration_seconds:.3f}",
        "-map",
        "0:v:0",
        "-map",
        "1:a:0",
        "-c:v",
        "copy",
        "-c:a",
        "aac",
        "-b:a",
        "160k",
        "-movflags",
        "+faststart",
        str(output),
    ]


def run_ffmpeg(command: list[str]) -> None:
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "ffmpeg failed").strip()
        raise RuntimeError(detail[-1500:])


def require_ffmpeg() -> str:
    ffmpeg = find_ffmpeg()
    if not ffmpeg:
        raise RuntimeError("ffmpeg is not installed. Install it with: winget install Gyan.FFmpeg")
    return ffmpeg


def render_base_clip(image: Path, clip: Path, ffmpeg: str | None = None, frames: int = CLIP_SECONDS) -> Path:
    executable = ffmpeg or require_ffmpeg()
    clip.parent.mkdir(parents=True, exist_ok=True)
    run_ffmpeg(base_clip_command(executable, image, clip, frames))
    return clip


def assemble(clip: Path, wav: Path, output: Path, duration_seconds: float, ffmpeg: str | None = None) -> Path:
    if duration_seconds <= 0:
        raise ValueError("Video length must be positive.")
    executable = ffmpeg or require_ffmpeg()
    output.parent.mkdir(parents=True, exist_ok=True)
    run_ffmpeg(assemble_command(executable, clip, wav, output, duration_seconds))
    return output
