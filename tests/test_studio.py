"""Studio helpers that do not open a browser."""

from app.studio import _already_english


def test_english_detection_accepts_only_plain_english():
    assert _already_english("Video language\nEnglish")
    assert _already_english("English (United States)")
    assert not _already_english("English (United Kingdom)")
    assert not _already_english("Video language\nSelect")
