"""Upload metadata and the resumable chunk loop. No real YouTube call."""

from datetime import datetime
from zoneinfo import ZoneInfo

from app.youtube import (
    INSERT_PARTS,
    MUSIC_CATEGORY,
    build_audio_language_body,
    build_insert_body,
    resumable_upload,
)


def test_upload_body_defaults_to_private_music():
    when = datetime(2026, 11, 23, 14, 5, tzinfo=ZoneInfo("America/Chicago"))
    body = build_insert_body("Rain", "Listen while you rest.", ["rain", "sleep"], "private", recorded_at=when)
    assert body["status"]["privacyStatus"] == "private"
    assert body["status"]["selfDeclaredMadeForKids"] is False
    assert body["status"]["containsSyntheticMedia"] is True
    assert body["paidProductPlacementDetails"]["hasPaidProductPlacement"] is False
    assert "contentRating" not in body
    assert body["snippet"]["categoryId"] == MUSIC_CATEGORY
    assert body["snippet"]["defaultLanguage"] == "en"
    assert body["snippet"]["title"] == "Rain"
    assert body["recordingDetails"]["recordingDate"] == "2026-11-23T06:00:00.000Z"
    assert "location" not in body["recordingDetails"]
    assert "locationDescription" not in body["recordingDetails"]
    assert INSERT_PARTS == "snippet,status,recordingDetails,paidProductPlacementDetails"


def test_resumable_loop_returns_the_video_id():
    class Request:
        def __init__(self):
            self.calls = 0

        def next_chunk(self):
            self.calls += 1
            if self.calls == 1:
                return ({"progress": 0.4}, None)
            return (None, {"id": "vid123"})

    request = Request()
    assert resumable_upload(request)["id"] == "vid123"
    assert request.calls == 2


def test_public_privacy_is_explicit():
    body = build_insert_body("Wind", "A wind bed.", ["wind"], "public")
    assert body["status"]["privacyStatus"] == "public"


def test_studio_failure_keeps_the_upload(monkeypatch, tmp_path):
    video = tmp_path / "video.mp4"
    video.write_bytes(b"not a real video")

    class Request:
        def next_chunk(self):
            return (None, {"id": "vid123"})

    class Call:
        def execute(self):
            return {}

    class Videos:
        def insert(self, part, body, media_body):
            assert part == INSERT_PARTS
            assert body["status"]["containsSyntheticMedia"] is True
            return Request()

        def update(self, part, body):
            assert body["snippet"]["defaultAudioLanguage"] == "en"
            return Call()

    class Service:
        def videos(self):
            return Videos()

    monkeypatch.setattr("app.youtube._service", lambda: Service())

    def boom(video_id):
        raise RuntimeError("studio signed out")

    monkeypatch.setattr("app.studio.apply_studio_settings", boom)
    from app.youtube import STUDIO_WARNING, upload_files

    video_id, warning = upload_files(str(video), None, "Rain", "Listen.", ["rain"], "private")
    assert video_id == "vid123"
    assert warning == STUDIO_WARNING


def test_audio_language_update_keeps_the_snippet():
    body = build_audio_language_body("vid123", "Rain", "Listen.", ["rain"], MUSIC_CATEGORY)
    assert body["id"] == "vid123"
    assert body["snippet"]["defaultAudioLanguage"] == "en"
    assert body["snippet"]["defaultLanguage"] == "en"
    assert body["snippet"]["title"] == "Rain"
    assert body["snippet"]["categoryId"] == MUSIC_CATEGORY
    assert body["snippet"]["tags"] == ["rain"]
