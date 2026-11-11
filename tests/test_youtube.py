"""Upload metadata and the resumable chunk loop. No real YouTube call."""

from app.youtube import MUSIC_CATEGORY, build_insert_body, resumable_upload


def test_upload_body_defaults_to_private_music():
    body = build_insert_body("Rain", "Listen while you rest.", ["rain", "sleep"], "private")
    assert body["status"]["privacyStatus"] == "private"
    assert body["status"]["selfDeclaredMadeForKids"] is False
    assert body["snippet"]["categoryId"] == MUSIC_CATEGORY
    assert body["snippet"]["title"] == "Rain"


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
