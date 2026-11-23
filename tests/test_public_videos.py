"""Ten random 3-hour public videos, without calling Gemini, ffmpeg, or YouTube."""

import pytest

from app.ideas import public_batch_prompt, parse_public_batch


def test_public_prompt_includes_meditation_and_work_focus():
    prompt = public_batch_prompt(["Steady Night Rain on a Zinc Roof"])
    assert "meditation" in prompt
    assert "coding" in prompt
    assert "deep work" in prompt
    assert "studying" in prompt
    assert "Do not use sleep" in prompt
    assert "Steady Night Rain on a Zinc Roof" in prompt


def test_batch_rejects_fewer_than_ten():
    with pytest.raises(ValueError):
        parse_public_batch({"ideas": []})


def test_public_button_queues_ten_three_hour_public_videos(monkeypatch):
    monkeypatch.setenv("AMBIENT_PREVIEW", "1")
    monkeypatch.setattr("app.main.find_ffmpeg", lambda: "ffmpeg")
    started = {}

    def fake_spawn(job_ids):
        started["ids"] = list(job_ids)

    monkeypatch.setattr("app.main.spawn_public_batch", fake_spawn)
    from fastapi.testclient import TestClient
    from app.main import app

    response = TestClient(app).post("/api/public-videos")
    assert response.status_code == 200
    jobs = response.json()["jobs"]
    assert len(jobs) == 10
    assert len({job["title"] for job in jobs}) == 10
    assert [job["batch_index"] for job in jobs] == list(range(1, 11))
    assert all(job["format"] == "long" for job in jobs)
    assert all(job["status"] == "queued" for job in jobs)
    assert all(job["privacy"] == "public" for job in jobs)
    assert all(job["duration_hours"] == 3 for job in jobs)
    assert all(job["purpose"] in {"focus", "meditation", "rest"} for job in jobs)
    titles = " ".join(job["title"].lower() for job in jobs)
    assert "meditation" in titles
    assert "coding" in titles
    assert started["ids"] == [job["id"] for job in jobs]
    assert len({job["batch_id"] for job in jobs}) == 1


def test_second_public_batch_is_refused_while_one_is_running(monkeypatch):
    monkeypatch.setenv("AMBIENT_PREVIEW", "1")
    monkeypatch.setattr("app.main.find_ffmpeg", lambda: "ffmpeg")
    from fastapi.testclient import TestClient
    from app.main import _public_batch_state, app

    _public_batch_state["running"] = True
    try:
        response = TestClient(app).post("/api/public-videos")
        assert response.status_code == 409
    finally:
        _public_batch_state["running"] = False


def test_public_batch_requires_youtube_when_not_previewing(monkeypatch):
    monkeypatch.delenv("AMBIENT_PREVIEW", raising=False)
    monkeypatch.setattr("app.main.find_ffmpeg", lambda: "ffmpeg")
    monkeypatch.setattr("app.main.youtube_connected", lambda: False)
    from fastapi.testclient import TestClient
    from app.main import app

    response = TestClient(app).post("/api/public-videos")
    assert response.status_code == 400
    assert "Connect YouTube" in response.json()["detail"]
