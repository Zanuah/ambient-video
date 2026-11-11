"""Idea parsing, prompts, and tag limits. No live Gemini call."""

import json
from pathlib import Path

import pytest

from app.ideas import (
    append_length,
    clean_title,
    idea_prompt,
    normalize_tags,
    parse_idea,
)

FIXTURE = Path(__file__).parent / "fixtures" / "idea.json"


def test_fixture_parses_without_calling_gemini():
    idea = parse_idea(FIXTURE.read_text(encoding="utf-8"))
    assert idea.purpose == "sleep"
    assert idea.sound_profile == "soft_rain"
    assert idea.title.startswith("Soft rain")
    assert "beach" in idea.scene_summary.lower()


def test_prompt_forbids_medical_claims_and_lists_sounds():
    prompt = idea_prompt(["Rain on a quiet beach for sleep"])
    assert "Do not claim" in prompt
    assert "soft_rain" in prompt
    assert "Rain on a quiet beach for sleep" in prompt


def test_unknown_sound_is_rejected():
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    payload["sound_profile"] = "bagpipes"
    with pytest.raises(ValueError):
        parse_idea(payload)


def test_tags_stay_within_youtube_limits():
    tags = normalize_tags(["Rain, night"] + [f"tag {index}" for index in range(40)] + ["rain night"])
    assert len(tags) <= 15
    assert sum(len(tag) for tag in tags) <= 480
    assert all("," not in tag for tag in tags)
    assert tags[0] == "Rain night"


def test_long_title_is_shortened():
    assert len(clean_title("a" * 180)) == 100


def test_length_line_fits_in_youtube_description():
    text = append_length("Listen while you rest.", 3)
    assert text.endswith("Length: 3 hours.")
    assert len(append_length("x" * 6000, 10)) <= 5000
