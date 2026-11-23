"""Rebuild uploaded videos with the subscribe card, upload the new file, and delete the old one.

YouTube cannot change the picture on an existing upload, so each video gets a new id.
Progress is stored in data/subscribe-backfill.json so a stopped run can continue.
"""

from __future__ import annotations

import json
import sqlite3
import sys
import traceback
from pathlib import Path

from googleapiclient.errors import HttpError

from app.config import data_dir, output_dir
from app.jobs import update_job
from app.video import assemble, render_short
from app.youtube import _service, upload_files

PROGRESS = data_dir() / "subscribe-backfill.json"


def load_jobs() -> list[dict]:
    database = data_dir() / "jobs.db"
    with sqlite3.connect(database) as connection:
        rows = connection.execute("SELECT document FROM jobs").fetchall()
    jobs = [json.loads(row[0]) for row in rows]
    uploaded = [job for job in jobs if job.get("youtube_id") and job.get("status") == "done"]
    uploaded.sort(key=lambda job: (job.get("format") != "short", job.get("updated_at") or ""))
    return uploaded


def load_progress() -> dict:
    if not PROGRESS.exists():
        return {"done": {}}
    return json.loads(PROGRESS.read_text(encoding="utf-8"))


def save_progress(progress: dict) -> None:
    PROGRESS.parent.mkdir(parents=True, exist_ok=True)
    PROGRESS.write_text(json.dumps(progress, indent=2), encoding="utf-8")


def rebuild(job: dict) -> Path:
    folder = output_dir() / job["id"]
    metadata = json.loads((folder / "metadata.json").read_text(encoding="utf-8"))
    destination = folder / "video-subscribe.mp4"
    if destination.exists():
        destination.unlink()
    if job.get("format") == "short":
        seconds = int(metadata.get("duration_seconds") or job.get("duration_seconds") or 30)
        render_short(folder / "frame.png", folder / "loop.wav", destination, seconds=seconds)
    else:
        hours = int(metadata.get("duration_hours") or job.get("duration_hours") or 3)
        assemble(folder / "clip.mp4", folder / "loop.wav", destination, hours * 3600)
    return destination


def replace_local_video(folder: Path, rendered: Path) -> None:
    final = folder / "video.mp4"
    backup = folder / "video-before-subscribe.mp4"
    if final.exists() and not backup.exists():
        final.replace(backup)
    rendered.replace(final)
    if backup.exists():
        backup.unlink()


def delete_video(video_id: str) -> None:
    try:
        _service().videos().delete(id=video_id).execute()
    except HttpError as exc:
        if exc.resp.status == 404:
            return
        raise


def channel_videos() -> list[dict]:
    service = _service()
    channel = service.channels().list(part="contentDetails", mine=True).execute()["items"][0]
    playlist = channel["contentDetails"]["relatedPlaylists"]["uploads"]
    page = None
    videos = []
    while True:
        response = service.playlistItems().list(
            part="snippet,status",
            playlistId=playlist,
            maxResults=50,
            pageToken=page,
        ).execute()
        for item in response.get("items", []):
            snippet = item["snippet"]
            videos.append(
                {
                    "id": snippet["resourceId"]["videoId"],
                    "title": snippet["title"],
                    "privacy": (item.get("status") or {}).get("privacyStatus") or "public",
                }
            )
        page = response.get("nextPageToken")
        if not page:
            break
    return videos


def jobs_by_title() -> dict[str, list[dict]]:
    grouped: dict[str, list[dict]] = {}
    for job in load_jobs():
        grouped.setdefault(job.get("title") or "", []).append(job)
    return grouped


def quota_exceeded(exc: HttpError) -> bool:
    text = exc.content.decode("utf-8", errors="replace").lower()
    return exc.resp.status in {403, 400} and ("quota" in text or "uploadlimitexceeded" in text)


def main() -> int:
    progress = load_progress()
    done = progress.setdefault("done", {})
    catalog = jobs_by_title()
    videos = [video for video in channel_videos() if video["id"] != "xFto7qJcE2k"]
    pending = []
    skipped = []
    for video in videos:
        job = catalog.get(video["title"], [None])[0]
        if job is None:
            for job_title, jobs in catalog.items():
                if job_title and video["title"].startswith(job_title):
                    job = jobs[0]
                    break
        if job is None:
            skipped.append(video["title"])
            continue
        if done.get(video["id"], {}).get("deleted"):
            continue
        pending.append((video, job))
    print(
        f"On the channel: {len(videos)}. Replacing: {len(pending)}. No local project file: {len(skipped)}.",
        flush=True,
    )
    for title in skipped:
        print(f"  left as-is: {title}", flush=True)
    for index, (video, job) in enumerate(pending, start=1):
        title = video["title"]
        old_id = video["id"]
        print(f"[{index}/{len(pending)}] {title}", flush=True)
        try:
            entry = done.get(old_id)
            if entry and entry.get("new"):
                new_id = entry["new"]
                warning = entry.get("warning")
                rendered = output_dir() / job["id"] / "video-subscribe.mp4"
            else:
                rendered = rebuild(job)
                metadata_path = output_dir() / job["id"] / "metadata.json"
                metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
                thumb = output_dir() / job["id"] / "thumbnail.jpg"
                new_id, warning = upload_files(
                    video_path=str(rendered),
                    thumbnail_path=str(thumb) if thumb.exists() else None,
                    title=metadata["title"],
                    description=metadata["description"],
                    tags=metadata.get("tags") or job.get("tags") or [],
                    privacy=video["privacy"],
                    sound_profile=metadata.get("sound_profile") or job.get("sound_profile"),
                    purpose=metadata.get("purpose") or job.get("purpose"),
                    notify_subscribers=False,
                    apply_studio=False,
                )
                done[old_id] = {"old": old_id, "new": new_id, "title": title, "deleted": False, "warning": warning}
                save_progress(progress)
            delete_video(old_id)
            if rendered.exists():
                replace_local_video(output_dir() / job["id"], rendered)
            update_job(
                job["id"],
                youtube_id=new_id,
                youtube_url=f"https://www.youtube.com/watch?v={new_id}",
                privacy=video["privacy"],
                note=warning,
            )
            done[old_id]["deleted"] = True
            save_progress(progress)
            print(f"  replaced {old_id} with {new_id}", flush=True)
            if warning:
                print(f"  warning: {warning}", flush=True)
        except HttpError as exc:
            save_progress(progress)
            if quota_exceeded(exc):
                print("YouTube upload quota is used up. Run this again after the quota resets.", flush=True)
                return 0
            traceback.print_exc()
            print(f"  failed: {exc}", flush=True)
            return 1
        except Exception as exc:
            save_progress(progress)
            traceback.print_exc()
            print(f"  failed: {exc}", flush=True)
            return 1
    print("Every uploaded video now has the subscribe card.", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
