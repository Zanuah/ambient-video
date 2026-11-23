"""Build a short zooming clip and loop it to the requested length."""

from __future__ import annotations

import math
import subprocess
from pathlib import Path

from app.config import find_ffmpeg

CLIP_SECONDS = 24
WIDTH = 1920
HEIGHT = 1080
ZOOM_AMOUNT = 0.04
SHORT_WIDTH = 1080
SHORT_HEIGHT = 1920
SHORT_SECONDS = 30
SHORT_FPS = 15
SUBSCRIBE_TEXT = "#Click SUBSCRIBE PLEASE!"
SUBSCRIBE_FONT = "C:/Windows/Fonts/arialbd.ttf"
SHORT_CARD_TAIL = 3
LONG_CARD_TAIL = 4
LOOPS_PER_CARD = 12


def subscribe_drawtext(start_second: int, fontsize: int) -> str:
    """Centered subscribe card. The comma in gte() is escaped so it stays one filter."""
    font = SUBSCRIBE_FONT.replace("\\", "/").replace(":", "\\:")
    start = max(0, start_second)
    return (
        "drawtext="
        f"fontfile='{font}':"
        f"text='{SUBSCRIBE_TEXT}':"
        f"enable='gte(t\\,{start})':"
        f"fontsize={fontsize}:fontcolor=white:borderw=3:bordercolor=black:"
        "box=1:boxcolor=black@0.55:boxborderw=16:"
        "x=(w-text_w)/2:y=(h-text_h)/2"
    )


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


def short_command(
    ffmpeg: str,
    image: Path,
    wav: Path,
    output: Path,
    seconds: int = SHORT_SECONDS,
    fps: int = SHORT_FPS,
) -> list[str]:
    frames = int(seconds * fps)
    zoom = f"1+{ZOOM_AMOUNT}*sin(PI*on/{frames - 1})"
    video_filter = (
        f"scale={SHORT_WIDTH}:{SHORT_HEIGHT}:force_original_aspect_ratio=increase,"
        f"crop={SHORT_WIDTH}:{SHORT_HEIGHT},"
        f"zoompan=z='{zoom}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={frames}:s={SHORT_WIDTH}x{SHORT_HEIGHT}:fps={fps},"
        + subscribe_drawtext(seconds - SHORT_CARD_TAIL, fontsize=48)
    )
    return [
        ffmpeg,
        "-y",
        "-i",
        str(image),
        "-i",
        str(wav),
        "-vf",
        video_filter,
        "-frames:v",
        str(frames),
        "-t",
        f"{seconds:.3f}",
        "-c:v",
        "libx264",
        "-tune",
        "stillimage",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        "-b:a",
        "160k",
        "-shortest",
        "-movflags",
        "+faststart",
        str(output),
    ]


def render_short(
    image: Path,
    wav: Path,
    output: Path,
    ffmpeg: str | None = None,
    seconds: int = SHORT_SECONDS,
) -> Path:
    executable = ffmpeg or require_ffmpeg()
    output.parent.mkdir(parents=True, exist_ok=True)
    run_ffmpeg(short_command(executable, image, wav, output, seconds))
    return output


def subscribe_clip_command(ffmpeg: str, clip: Path, output: Path, seconds: int = CLIP_SECONDS) -> list[str]:
    return [
        ffmpeg,
        "-y",
        "-i",
        str(clip),
        "-vf",
        subscribe_drawtext(seconds - LONG_CARD_TAIL, fontsize=64),
        "-an",
        "-r",
        "1",
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
        str(output),
    ]


def concat_entries(
    clip: Path,
    subscribe_clip: Path,
    duration_seconds: float,
    clip_seconds: int = CLIP_SECONDS,
) -> list[Path]:
    """Eleven plain loops, then the subscribe twin. Twelve loops is 288 seconds."""
    count = max(1, math.ceil(duration_seconds / clip_seconds))
    entries: list[Path] = []
    for index in range(1, count + 1):
        if index % LOOPS_PER_CARD == 0:
            entries.append(subscribe_clip)
        else:
            entries.append(clip)
    return entries


def write_concat_file(path: Path, entries: list[Path]) -> Path:
    lines = []
    for entry in entries:
        text = str(entry.resolve()).replace("\\", "/").replace("'", "'\\''")
        lines.append(f"file '{text}'")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def assemble_command(ffmpeg: str, concat_file: Path, wav: Path, output: Path, duration_seconds: float) -> list[str]:
    return [
        ffmpeg,
        "-y",
        "-f",
        "concat",
        "-safe",
        "0",
        "-i",
        str(concat_file),
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
    subscribe = clip.with_name(f"{clip.stem}-subscribe{clip.suffix}")
    run_ffmpeg(subscribe_clip_command(executable, clip, subscribe))
    listing = output.with_name(f"{output.stem}-concat.txt")
    write_concat_file(listing, concat_entries(clip, subscribe, duration_seconds))
    run_ffmpeg(assemble_command(executable, listing, wav, output, duration_seconds))
    return output
