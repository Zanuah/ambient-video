"""Approve an idea: still, sound loop, long video, then YouTube."""

from __future__ import annotations

import json
from pathlib import Path

from app.audio import LOOP_SECONDS, SAMPLE_RATE, synthesize, write_wav
from app.config import output_dir, preview_mode
from app.ideas import append_length
from app.images import fit_frame, generate_still, write_thumbnail
from app.jobs import get_job, update_job
from app.video import assemble, render_base_clip
from app.youtube import upload_files, youtube_connected

PREVIEW_NOTE = "Preview mode saved the files locally and did not upload. Turn off AMBIENT_PREVIEW and connect YouTube to publish."
CONNECT_NOTE = "The video is ready on disk. Connect YouTube, then retry the upload."


def run_job(job_id: str) -> None:
    job = get_job(job_id)
    if job is None:
        return
    folder = output_dir() / job_id
    folder.mkdir(parents=True, exist_ok=True)
    try:
        _render(job, folder)
        job = get_job(job_id)
        if preview_mode():
            update_job(job_id, status="ready", step="done", note=PREVIEW_NOTE, error=None)
            return
        if not youtube_connected():
            update_job(job_id, status="ready", step="upload", note=CONNECT_NOTE, error=None)
            return
        publish(job_id)
    except Exception as exc:
        update_job(job_id, status="failed", error=str(exc).strip() or exc.__class__.__name__)


def _render(job: dict, folder: Path) -> None:
    job_id = job["id"]
    hours = int(job["duration_hours"])
    update_job(job_id, status="rendering", step="image", error=None)

    still = folder / "still.png"
    frame = folder / "frame.png"
    generate_still(None, job["scene_prompt"], still)
    fit_frame(still, frame)

    update_job(job_id, step="audio")
    wav = folder / "loop.wav"
    samples = synthesize(job["sound_profile"], seconds=LOOP_SECONDS, sample_rate=SAMPLE_RATE)
    write_wav(wav, samples, SAMPLE_RATE)

    update_job(job_id, step="video")
    clip = folder / "clip.mp4"
    video = folder / "video.mp4"
    render_base_clip(frame, clip)
    assemble(clip, wav, video, hours * 3600)

    update_job(job_id, step="metadata")
    thumb = folder / "thumbnail.jpg"
    write_thumbnail(frame, thumb)
    description = append_length(job["description"], hours)
    metadata = {
        "title": job["title"],
        "description": description,
        "tags": job["tags"],
        "purpose": job["purpose"],
        "sound_profile": job["sound_profile"],
        "duration_hours": hours,
        "privacy": job["privacy"],
    }
    metadata_path = folder / "metadata.json"
    metadata_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    update_job(
        job_id,
        image_path=str(still),
        wav_path=str(wav),
        video_path=str(video),
        thumbnail_path=str(thumb),
        metadata_path=str(metadata_path),
    )


def publish(job_id: str) -> None:
    job = get_job(job_id)
    if job is None or not job.get("video_path"):
        raise RuntimeError("There is no video to upload yet.")
    metadata = json.loads(Path(job["metadata_path"]).read_text(encoding="utf-8"))
    update_job(job_id, status="uploading", step="upload", error=None)
    try:
        video_id, warning = upload_files(
            video_path=job["video_path"],
            thumbnail_path=job.get("thumbnail_path"),
            title=metadata["title"],
            description=metadata["description"],
            tags=metadata["tags"],
            privacy=metadata["privacy"],
        )
    except Exception as exc:
        update_job(
            job_id,
            status="ready",
            step="upload",
            error=f"Upload failed. The video file is still on disk. {exc}",
        )
        return
    update_job(
        job_id,
        status="done",
        step="done",
        youtube_id=video_id,
        youtube_url=f"https://www.youtube.com/watch?v={video_id}",
        note=warning,
        error=None,
    )
