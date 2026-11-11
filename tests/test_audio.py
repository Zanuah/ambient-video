"""Loop joins and sound profiles."""

import wave

import numpy as np
import pytest

from app.audio import seamless_loop, synthesize, write_wav
from app.ideas import SOUND_PROFILES


def test_boundary_samples_are_neighbors_of_the_source():
    raw = np.random.default_rng(0).standard_normal(5000)
    fade = 200
    loop = seamless_loop(raw, fade)
    length = len(raw) - fade
    assert len(loop) == length
    assert loop[-1] == pytest.approx(raw[length - 1])
    assert loop[0] == pytest.approx(raw[length])


@pytest.mark.parametrize("profile", SOUND_PROFILES)
def test_each_profile_loops_without_a_click(profile):
    audio = synthesize(profile, seconds=3, sample_rate=16000, seed=2)
    assert len(audio) == 3 * 16000
    assert np.isfinite(audio).all()
    assert float(np.max(np.abs(audio))) <= 0.451
    assert float(np.std(audio)) > 0.01
    jump = abs(float(audio[0] - audio[-1]))
    largest_step = float(np.max(np.abs(np.diff(audio))))
    assert jump <= largest_step + 1e-5


def test_unknown_profile_is_rejected():
    with pytest.raises(ValueError):
        synthesize("bagpipes", seconds=1, sample_rate=8000, seed=1)


def test_wav_round_trip(tmp_path):
    audio = synthesize("brown_noise", seconds=1, sample_rate=8000, seed=3)
    path = write_wav(tmp_path / "loop.wav", audio, 8000)
    with wave.open(str(path), "rb") as handle:
        assert handle.getframerate() == 8000
        assert handle.getnframes() == len(audio)
        assert handle.getnchannels() == 1
