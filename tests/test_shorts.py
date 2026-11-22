"""Ten calm and focus Shorts, without calling Gemini or ffmpeg."""

from app.ideas import as_short, parse_idea, parse_short_batch
from app.video import SHORT_HEIGHT, SHORT_SECONDS, SHORT_WIDTH, short_command


def test_short_title_keeps_the_shorts_label():
    idea = as_short(
        parse_idea(
            {
                "purpose": "focus",
                "title": "A" * 120,
                "description": "Background listening.",
                "tags": ["focus"],
                "scene_summary": "A quiet desk.",
                "scene_prompt": "A quiet desk.",
                "sound_profile": "brown_noise",
            }
        )
    )
    assert idea.title.endswith("#Shorts")
    assert len(idea.title) <= 100
    assert "Shorts" in idea.tags


def test_batch_rejects_fewer_than_ten():
    import pytest

    with pytest.raises(ValueError):
        parse_short_batch({"ideas": []})


def test_vertical_short_is_thirty_seconds():
    command = short_command("ffmpeg", "frame.png", "loop.wav", "out.mp4")
    video_filter = command[command.index("-vf") + 1]
    assert f"s={SHORT_WIDTH}x{SHORT_HEIGHT}" in video_filter
    assert command[command.index("-t") + 1] == f"{SHORT_SECONDS:.3f}"
    assert SHORT_SECONDS <= 60
    assert SHORT_HEIGHT > SHORT_WIDTH


def test_shorts_button_queues_ten_videos(monkeypatch):
    monkeypatch.setenv("AMBIENT_PREVIEW", "1")
    monkeypatch.setattr("app.main.find_ffmpeg", lambda: "ffmpeg")
    started = {}

    def fake_spawn(job_ids):
        started["ids"] = list(job_ids)

    monkeypatch.setattr("app.main.spawn_shorts", fake_spawn)
    from fastapi.testclient import TestClient
    from app.main import app

    response = TestClient(app).post("/api/shorts", json={"privacy": "private"})
    assert response.status_code == 200
    jobs = response.json()["jobs"]
    assert len(jobs) == 10
    assert len({job["title"] for job in jobs}) == 10
    assert [job["batch_index"] for job in jobs] == list(range(1, 11))
    assert all(job["format"] == "short" for job in jobs)
    assert all(job["status"] == "queued" for job in jobs)
    assert all(job["privacy"] == "private" for job in jobs)
    assert all(job["purpose"] in {"focus", "meditation", "rest"} for job in jobs)
    assert all(job["title"].endswith("#Shorts") for job in jobs)
    assert started["ids"] == [job["id"] for job in jobs]
    assert len({job["batch_id"] for job in jobs}) == 1
