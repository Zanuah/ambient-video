"""Seamless ambient loops. Rain, water, wind, and fire come from short recordings."""

from __future__ import annotations

import wave
from pathlib import Path

import numpy as np

from app.ideas import SOUND_PROFILES

SAMPLE_RATE = 48000
LOOP_SECONDS = 60
TARGET_PEAK = 0.45
SOUNDS_DIR = Path(__file__).resolve().parents[1] / "assets" / "sounds"
# Real 10–20 second bites. Brown, pink, and white noise stay synthesized.
FIELD_RECORDINGS = frozenset({"soft_rain", "heavy_rain", "ocean", "stream", "wind", "fireplace"})


def seamless_loop(raw: np.ndarray, fade_samples: int) -> np.ndarray:
    """Blend the tail into the head so the first and last samples are neighbors."""
    if fade_samples < 1:
        return raw.copy()
    if fade_samples >= len(raw):
        raise ValueError("Crossfade is longer than the audio.")
    length = len(raw) - fade_samples
    loop = raw[:length].copy()
    angle = np.linspace(0, np.pi / 2, fade_samples, endpoint=True)
    tail = raw[length : length + fade_samples]
    head = raw[:fade_samples]
    loop[:fade_samples] = tail * np.cos(angle) + head * np.sin(angle)
    return loop


def _colored(sample_count: int, rng: np.random.Generator, slope: float) -> np.ndarray:
    white = rng.standard_normal(sample_count)
    spectrum = np.fft.rfft(white)
    freqs = np.fft.rfftfreq(sample_count)
    freqs[0] = freqs[1] if sample_count > 1 else 1.0
    spectrum /= freqs ** (slope / 2.0)
    spectrum[0] = 0
    audio = np.fft.irfft(spectrum, n=sample_count)
    peak = np.max(np.abs(audio)) or 1.0
    return audio / peak


def _swell(sample_count: int, rng: np.random.Generator, sample_rate: int, speed_hz: float) -> np.ndarray:
    controls = max(8, int(sample_count / sample_rate * speed_hz * 8))
    points = rng.random(controls)
    kernel = np.array([1, 2, 3, 2, 1], dtype=np.float64)
    kernel /= kernel.sum()
    smooth = np.convolve(points, kernel, mode="same")
    envelope = np.interp(np.linspace(0, controls - 1, sample_count), np.arange(controls), smooth)
    envelope -= envelope.min()
    envelope /= envelope.max() or 1.0
    return 0.4 + 0.6 * envelope


def _droplets(
    sample_count: int,
    rng: np.random.Generator,
    sample_rate: int,
    per_second: float,
    decay_seconds: float,
    amplitude: float,
) -> np.ndarray:
    audio = np.zeros(sample_count, dtype=np.float64)
    decay = max(8, int(decay_seconds * sample_rate))
    if sample_count <= decay:
        return audio
    curve = np.exp(-np.linspace(0, 6, decay))
    count = max(1, int(sample_count / sample_rate * per_second))
    positions = rng.integers(0, sample_count - decay, size=count)
    for position in positions:
        burst = rng.standard_normal(decay) * curve * amplitude
        audio[position : position + decay] += burst
    return audio


def render_profile(profile: str, sample_count: int, rng: np.random.Generator, sample_rate: int) -> np.ndarray:
    if profile == "soft_rain":
        bed = _colored(sample_count, rng, 1.15) * 0.25
        drops = _droplets(sample_count, rng, sample_rate, 8, 0.05, 0.35)
        return bed + drops
    if profile == "heavy_rain":
        bed = _colored(sample_count, rng, 0.9) * 0.4
        drops = _droplets(sample_count, rng, sample_rate, 22, 0.04, 0.45)
        return bed + drops
    if profile == "ocean":
        bed = _colored(sample_count, rng, 1.8)
        return bed * _swell(sample_count, rng, sample_rate, 0.08)
    if profile == "stream":
        bed = _colored(sample_count, rng, 0.7) * 0.7
        hiss = _colored(sample_count, rng, 0.2) * 0.25
        return (bed + hiss) * _swell(sample_count, rng, sample_rate, 0.4)
    if profile == "wind":
        bed = _colored(sample_count, rng, 1.4)
        return bed * _swell(sample_count, rng, sample_rate, 0.12)
    if profile == "brown_noise":
        return _colored(sample_count, rng, 2.0)
    if profile == "pink_noise":
        return _colored(sample_count, rng, 1.0)
    if profile == "white_noise":
        return _colored(sample_count, rng, 0.0)
    if profile == "fireplace":
        bed = _colored(sample_count, rng, 1.7) * 0.18
        crackle = _droplets(sample_count, rng, sample_rate, 3.5, 0.03, 0.9)
        return bed + crackle
    raise ValueError(f"Unknown sound profile: {profile}")


def normalize(audio: np.ndarray, peak: float = TARGET_PEAK) -> np.ndarray:
    centered = audio - np.mean(audio)
    loudest = np.max(np.abs(centered)) or 1.0
    return centered * (peak / loudest)


def read_wav(path: Path) -> tuple[np.ndarray, int]:
    with wave.open(str(path), "rb") as handle:
        channels = handle.getnchannels()
        rate = handle.getframerate()
        frames = handle.readframes(handle.getnframes())
    audio = np.frombuffer(frames, dtype=np.int16).astype(np.float64) / 32768.0
    if channels > 1:
        audio = audio.reshape(-1, channels).mean(axis=1)
    return audio, rate


def resample(audio: np.ndarray, source_rate: int, target_rate: int) -> np.ndarray:
    if source_rate == target_rate:
        return audio
    if source_rate < 1 or target_rate < 1 or len(audio) < 2:
        raise ValueError("Cannot resample this recording.")
    target_length = int(round(len(audio) * target_rate / source_rate))
    source_x = np.linspace(0.0, 1.0, len(audio), endpoint=False)
    target_x = np.linspace(0.0, 1.0, target_length, endpoint=False)
    return np.interp(target_x, source_x, audio)


def load_bite(profile: str) -> tuple[np.ndarray, int]:
    path = SOUNDS_DIR / f"{profile}.wav"
    if not path.is_file():
        raise FileNotFoundError(f"Missing sound bite: {path.name}")
    audio, rate = read_wav(path)
    if len(audio) < 2:
        raise ValueError(f"Sound bite is empty: {path.name}")
    return audio, rate


def loop_recording(profile: str, seconds: float, sample_rate: int) -> np.ndarray:
    """Repeat a 10–20 second bite to the requested length, with a seamless join."""
    bite, rate = load_bite(profile)
    bite = resample(bite, rate, sample_rate)
    sample_count = int(seconds * sample_rate)
    fade = int(min(0.35, seconds / 4) * sample_rate)
    fade = min(fade, max(1, len(bite) // 8), max(1, sample_count // 4))
    copies = int(np.ceil((sample_count + fade) / len(bite)))
    raw = np.tile(bite, copies)[: sample_count + fade]
    return normalize(seamless_loop(raw, fade))


def synthesize(
    profile: str,
    seconds: float = LOOP_SECONDS,
    sample_rate: int = SAMPLE_RATE,
    seed: int | None = None,
) -> np.ndarray:
    if profile not in SOUND_PROFILES:
        raise ValueError(f"Unknown sound profile: {profile}")
    if seconds <= 0:
        raise ValueError("Loop length must be positive.")
    if profile in FIELD_RECORDINGS:
        return loop_recording(profile, seconds, sample_rate).astype(np.float32)
    sample_count = int(seconds * sample_rate)
    fade = int(min(0.5, seconds / 4) * sample_rate)
    rng = np.random.default_rng(seed)
    raw = render_profile(profile, sample_count + fade, rng, sample_rate)
    looped = normalize(seamless_loop(raw, fade))
    return looped.astype(np.float32)


def write_wav(path: Path, samples: np.ndarray, sample_rate: int = SAMPLE_RATE) -> Path:
    clipped = np.clip(samples, -1, 1)
    pcm = (clipped * 32767).astype(np.int16)
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(sample_rate)
        handle.writeframes(pcm.tobytes())
    return path
