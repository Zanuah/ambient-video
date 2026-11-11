"""Local website for generating, rendering, and uploading ambient videos."""

from __future__ import annotations

import threading
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from app.config import ROOT, client_secret_path, find_ffmpeg, gemini_api_key, preview_mode
from app.ideas import generate_idea, to_public
from app.jobs import create_proposed, get_job, latest_proposed, list_jobs, update_job
from app.pipeline import publish, run_job
from app.youtube import run_oauth_flow, youtube_connected

_connect_state = {"running": False, "error": None}


@asynccontextmanager
async def lifespan(_app: FastAPI):
    from app.jobs import init_db

    init_db()
    yield


app = FastAPI(title="Ambient Video", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=ROOT / "static"), name="static")


class ApproveBody(BaseModel):
    duration_hours: int = Field(description="1, 3, 8, or 10")
    privacy: str = "private"


def spawn(job_id: str) -> None:
    threading.Thread(target=run_job, args=(job_id,), daemon=True).start()


@app.get("/")
def index():
    return FileResponse(ROOT / "static" / "index.html")


@app.get("/api/health")
def health():
    return {
        "gemini_key_present": bool(gemini_api_key()),
        "preview": preview_mode(),
        "ffmpeg": find_ffmpeg() is not None,
        "youtube_client_secret": client_secret_path().exists(),
        "youtube_connected": youtube_connected(),
        "connect_running": _connect_state["running"],
        "connect_error": _connect_state["error"],
    }


@app.get("/api/jobs/current")
def current_job():
    return latest_proposed()


@app.get("/api/jobs")
def jobs(limit: int = 12):
    return list_jobs(min(limit, 50))


@app.get("/api/jobs/{job_id}")
def one_job(job_id: str):
    job = get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="No job with that id.")
    return job


@app.post("/api/ideas")
def new_idea():
    titles = [job["title"] for job in list_jobs(20)]
    try:
        idea = generate_idea(avoid_titles=titles)
    except Exception as exc:
        message = str(exc).strip() or "Could not create an idea."
        status = 400 if "GEMINI_API_KEY" in message else 502
        raise HTTPException(status_code=status, detail=message) from exc
    return create_proposed(to_public(idea))


@app.post("/api/jobs/{job_id}/decline")
def decline(job_id: str):
    job = get_job(job_id)
    if job is None or job["status"] != "proposed":
        raise HTTPException(status_code=404, detail="That idea is no longer waiting for a decision.")
    update_job(job_id, status="declined", step="declined")
    titles = [item["title"] for item in list_jobs(20)]
    try:
        idea = generate_idea(avoid_titles=titles)
    except Exception as exc:
        message = str(exc).strip() or "Could not create another idea."
        status = 400 if "GEMINI_API_KEY" in message else 502
        raise HTTPException(status_code=status, detail=message) from exc
    return create_proposed(to_public(idea))


@app.post("/api/jobs/{job_id}/approve")
def approve(job_id: str, body: ApproveBody):
    if body.duration_hours not in {1, 3, 8, 10}:
        raise HTTPException(status_code=400, detail="Duration must be 1, 3, 8, or 10 hours.")
    if body.privacy not in {"private", "unlisted", "public"}:
        raise HTTPException(status_code=400, detail="Privacy must be private, unlisted, or public.")
    job = get_job(job_id)
    if job is None or job["status"] != "proposed":
        raise HTTPException(status_code=404, detail="That idea is no longer waiting for a decision.")
    if find_ffmpeg() is None:
        raise HTTPException(
            status_code=400,
            detail="ffmpeg is not installed. Install it with: winget install Gyan.FFmpeg",
        )
    update_job(
        job_id,
        status="rendering",
        step="queued",
        duration_hours=body.duration_hours,
        privacy=body.privacy,
        error=None,
        note=None,
    )
    spawn(job_id)
    return get_job(job_id)


@app.post("/api/jobs/{job_id}/upload")
def retry_upload(job_id: str):
    job = get_job(job_id)
    if job is None or not job.get("video_path"):
        raise HTTPException(status_code=400, detail="There is no video to upload yet.")
    if preview_mode():
        raise HTTPException(status_code=400, detail="Preview mode does not upload.")
    if not Path(job["video_path"]).exists():
        raise HTTPException(status_code=400, detail="The video file is missing from disk.")
    update_job(job_id, status="uploading", step="upload", error=None)
    threading.Thread(target=publish, args=(job_id,), daemon=True).start()
    return get_job(job_id)


@app.post("/api/youtube/connect")
def connect_youtube():
    if not client_secret_path().exists():
        raise HTTPException(
            status_code=400,
            detail="Save your OAuth desktop client as client_secret.json in the project folder. See the README.",
        )
    if _connect_state["running"]:
        return {"status": "waiting"}
    _connect_state["running"] = True
    _connect_state["error"] = None

    def work():
        try:
            run_oauth_flow()
        except Exception as exc:
            _connect_state["error"] = str(exc).strip() or "YouTube sign-in failed."
        finally:
            _connect_state["running"] = False

    threading.Thread(target=work, daemon=True).start()
    return {"status": "waiting"}
