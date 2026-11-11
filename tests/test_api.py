"""Approve, decline, and render orchestration without live APIs."""

import json
from pathlib import Path

from fastapi.testclient import TestClient

from app.ideas import parse_idea, to_public
from app.jobs import create_proposed, get_job
from app.pipeline import run_job


def _client():
    from app.main import app

    return TestClient(app)


def test_generate_requires_a_gemini_key(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("AMBIENT_PREVIEW", raising=False)
    response = _client().post("/api/ideas")
    assert response.status_code == 400
    assert "GEMINI_API_KEY" in response.json()["detail"]


def test_decline_and_approve_use_private_three_hours(monkeypatch):
    monkeypatch.setenv("AMBIENT_PREVIEW", "1")
    started = {}

    def fake_spawn(job_id):
        started["id"] = job_id

    monkeypatch.setattr("app.main.spawn", fake_spawn)
    client = _client()
    first = client.post("/api/ideas")
    assert first.status_code == 200
    first_job = first.json()
    second = client.post(f"/api/jobs/{first_job['id']}/decline")
    assert second.status_code == 200
    second_job = second.json()
    assert second_job["id"] != first_job["id"]
    assert second_job["title"] != first_job["title"]
    assert client.get(f"/api/jobs/{first_job['id']}").json()["status"] == "declined"
    rejected = client.post(
        f"/api/jobs/{second_job['id']}/approve",
        json={"duration_hours": 2, "privacy": "private"},
    )
    assert rejected.status_code == 400
    approved = client.post(
        f"/api/jobs/{second_job['id']}/approve",
        json={"duration_hours": 3, "privacy": "private"},
    )
    assert approved.status_code == 200
    body = approved.json()
    assert body["status"] == "rendering"
    assert body["privacy"] == "private"
    assert body["duration_hours"] == 3
    assert started["id"] == second_job["id"]


def test_missing_privacy_defaults_to_private(monkeypatch):
    monkeypatch.setenv("AMBIENT_PREVIEW", "1")
    monkeypatch.setattr("app.main.spawn", lambda job_id: None)
    monkeypatch.setattr("app.main.find_ffmpeg", lambda: "ffmpeg")
    client = _client()
    job = client.post("/api/ideas").json()
    approved = client.post(f"/api/jobs/{job['id']}/approve", json={"duration_hours": 1})
    assert approved.status_code == 200
    assert approved.json()["privacy"] == "private"


def _patch_render(monkeypatch, tmp_path):
    def fake_still(_client, _prompt, dest):
        dest.write_bytes(b"png")
        return dest

    def fake_fit(src, dest):
        dest.write_bytes(src.read_bytes())
        return dest

    def fake_thumb(src, dest):
        dest.write_bytes(b"jpg")
        return dest

    def fake_clip(image, clip, ffmpeg=None, frames=24):
        clip.write_bytes(b"clip")
        return clip

    def fake_assemble(clip, wav, output, duration_seconds, ffmpeg=None):
        output.write_bytes(b"mp4")
        return output

    monkeypatch.setattr("app.pipeline.generate_still", fake_still)
    monkeypatch.setattr("app.pipeline.fit_frame", fake_fit)
    monkeypatch.setattr("app.pipeline.write_thumbnail", fake_thumb)
    monkeypatch.setattr("app.pipeline.render_base_clip", fake_clip)
    monkeypatch.setattr("app.pipeline.assemble", fake_assemble)
    monkeypatch.setattr("app.pipeline.synthesize", lambda *args, **kwargs: __import__("numpy").zeros(8, dtype="float32"))
    monkeypatch.setattr("app.pipeline.write_wav", lambda path, samples, sample_rate: path.write_bytes(b"wav") or path)


def test_run_job_preview_skips_upload(monkeypatch, tmp_path):
    monkeypatch.setenv("AMBIENT_PREVIEW", "1")
    _patch_render(monkeypatch, tmp_path)
    called = {"n": 0}

    def fake_upload(**kwargs):
        called["n"] += 1
        return "should-not-run", None

    monkeypatch.setattr("app.pipeline.upload_files", fake_upload)
    idea = to_public(parse_idea(_idea()))
    job = create_proposed(idea)
    from app.jobs import update_job

    update_job(job["id"], duration_hours=1, privacy="private", status="rendering")
    run_job(job["id"])
    saved = get_job(job["id"])
    assert called["n"] == 0
    assert saved["status"] == "ready"
    assert "Preview mode" in saved["note"]
    metadata = json.loads(Path(saved["metadata_path"]).read_text(encoding="utf-8"))
    assert metadata["privacy"] == "private"
    assert metadata["description"].endswith("Length: 1 hour.")


def test_run_job_uploads_when_connected(monkeypatch, tmp_path):
    monkeypatch.delenv("AMBIENT_PREVIEW", raising=False)
    _patch_render(monkeypatch, tmp_path)
    monkeypatch.setattr("app.pipeline.youtube_connected", lambda: True)
    monkeypatch.setattr("app.pipeline.upload_files", lambda **kwargs: ("abc123", None))
    job = create_proposed(to_public(parse_idea(_idea())))
    from app.jobs import update_job

    update_job(job["id"], duration_hours=8, privacy="unlisted", status="rendering")
    run_job(job["id"])
    saved = get_job(job["id"])
    assert saved["status"] == "done"
    assert saved["youtube_id"] == "abc123"
    assert saved["youtube_url"].endswith("abc123")


def test_failed_upload_keeps_the_file(monkeypatch, tmp_path):
    monkeypatch.delenv("AMBIENT_PREVIEW", raising=False)
    _patch_render(monkeypatch, tmp_path)
    monkeypatch.setattr("app.pipeline.youtube_connected", lambda: True)

    def boom(**kwargs):
        raise RuntimeError("quota")

    monkeypatch.setattr("app.pipeline.upload_files", boom)
    job = create_proposed(to_public(parse_idea(_idea())))
    from app.jobs import update_job

    update_job(job["id"], duration_hours=1, privacy="private", status="rendering")
    run_job(job["id"])
    saved = get_job(job["id"])
    assert saved["status"] == "ready"
    assert "quota" in saved["error"]
    assert saved["video_path"]


def _idea():
    return {
        "purpose": "focus",
        "title": "Stream for focus",
        "description": "A stream for background listening.",
        "tags": ["stream", "focus"],
        "scene_summary": "A shaded creek.",
        "scene_prompt": "A shaded creek, no people.",
        "sound_profile": "stream",
    }
