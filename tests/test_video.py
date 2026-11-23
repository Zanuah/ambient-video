"""ffmpeg command shape and a short render."""

import math
import subprocess

import pytest
from PIL import Image

from app.audio import synthesize, write_wav
from app.config import find_ffmpeg, find_ffprobe
from app.images import fit_frame, image_prompt
from app.video import (
    SUBSCRIBE_TEXT,
    ZOOM_AMOUNT,
    assemble,
    assemble_command,
    base_clip_command,
    concat_entries,
    render_base_clip,
    subscribe_clip_command,
    zoom_at,
)


def test_zoom_starts_and_ends_at_one():
    assert zoom_at(0) == 1
    assert zoom_at(23) == pytest.approx(1)
    peak = max(zoom_at(frame) for frame in range(24))
    assert peak == pytest.approx(1 + ZOOM_AMOUNT, abs=0.001)


def test_base_clip_uses_stillimage_and_matching_zoom():
    command = base_clip_command("ffmpeg", "frame.png", "clip.mp4")
    video_filter = command[command.index("-vf") + 1]
    assert f"1+{ZOOM_AMOUNT}*sin(PI*on/23)" in video_filter
    assert "zoompan" in video_filter
    assert "-tune" in command and "stillimage" in command
    assert "-g" in command


def test_image_prompt_asks_for_a_still_without_people():
    prompt = image_prompt("Rain on the sand.")
    assert "No text" in prompt
    assert "no people" in prompt
    assert "Rain on the sand." in prompt


def test_assemble_copies_video_and_encodes_audio(tmp_path):
    listing = tmp_path / "concat.txt"
    command = assemble_command("ffmpeg", listing, "loop.wav", tmp_path / "out.mp4", 15)
    assert command[command.index("-c:v") + 1] == "copy"
    assert command[command.index("-c:a") + 1] == "aac"
    assert command[command.index("-t") + 1] == "15.000"
    assert command[command.index("-f") + 1] == "concat"
    assert "-stream_loop" in command


def test_subscribe_card_lands_on_every_twelfth_loop(tmp_path):
    clip = tmp_path / "clip.mp4"
    card = tmp_path / "clip-subscribe.mp4"
    entries = concat_entries(clip, card, 288)
    assert len(entries) == 12
    assert entries[:-1] == [clip] * 11
    assert entries[-1] == card
    short = concat_entries(clip, card, 15)
    assert short == [clip]


def test_subscribe_clip_shows_the_card_at_the_end(tmp_path):
    command = subscribe_clip_command("ffmpeg", tmp_path / "clip.mp4", tmp_path / "card.mp4")
    video_filter = command[command.index("-vf") + 1]
    assert SUBSCRIBE_TEXT in video_filter
    assert r"gte(t\,20)" in video_filter
    assert command[command.index("-c:v") + 1] == "libx264"


def test_smoke_renders_15_seconds(tmp_path):
    ffmpeg = find_ffmpeg()
    ffprobe = find_ffprobe()
    if not ffmpeg or not ffprobe:
        pytest.skip("ffmpeg is not installed")
    source = tmp_path / "still.png"
    Image.new("RGB", (960, 540), (24, 48, 72)).save(source)
    frame = fit_frame(source, tmp_path / "frame.png")
    clip = render_base_clip(frame, tmp_path / "clip.mp4", ffmpeg=ffmpeg)
    wav = write_wav(
        tmp_path / "loop.wav",
        synthesize("soft_rain", seconds=2, sample_rate=16000, seed=1),
        16000,
    )
    output = assemble(clip, wav, tmp_path / "video.mp4", 15, ffmpeg=ffmpeg)
    probe = subprocess.run(
        [ffprobe, "-v", "error", "-show_entries", "format=duration", "-of", "default=nw=1:nk=1", str(output)],
        capture_output=True,
        text=True,
        check=True,
    )
    duration = float(probe.stdout.strip())
    assert 14 <= duration <= 16
    assert output.stat().st_size > 1000
    assert math.isfinite(duration)
