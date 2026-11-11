"""SQLite history for ideas and renders."""

from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone

from app.config import data_dir


def db_path():
    folder = data_dir()
    folder.mkdir(parents=True, exist_ok=True)
    return folder / "jobs.db"


def connect() -> sqlite3.Connection:
    connection = sqlite3.connect(db_path(), timeout=30)
    connection.row_factory = sqlite3.Row
    return connection


def init_db() -> None:
    with connect() as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS jobs (
                id TEXT PRIMARY KEY,
                status TEXT NOT NULL,
                document TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _save(job: dict) -> dict:
    init_db()
    with connect() as connection:
        connection.execute(
            """
            INSERT INTO jobs (id, status, document, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                status = excluded.status,
                document = excluded.document,
                updated_at = excluded.updated_at
            """,
            (job["id"], job["status"], json.dumps(job), job["updated_at"]),
        )
    return job


def create_proposed(idea: dict) -> dict:
    timestamp = _now()
    job = {
        "id": uuid.uuid4().hex,
        "status": "proposed",
        "step": "idea",
        "purpose": idea["purpose"],
        "title": idea["title"],
        "description": idea["description"],
        "tags": idea["tags"],
        "scene_prompt": idea["scene_prompt"],
        "scene_summary": idea["scene_summary"],
        "sound_profile": idea["sound_profile"],
        "sound_label": idea["sound_label"],
        "duration_hours": None,
        "privacy": None,
        "image_path": None,
        "wav_path": None,
        "video_path": None,
        "thumbnail_path": None,
        "metadata_path": None,
        "youtube_id": None,
        "youtube_url": None,
        "note": None,
        "error": None,
        "created_at": timestamp,
        "updated_at": timestamp,
    }
    return _save(job)


def get_job(job_id: str) -> dict | None:
    init_db()
    with connect() as connection:
        row = connection.execute("SELECT document FROM jobs WHERE id = ?", (job_id,)).fetchone()
    if row is None:
        return None
    return json.loads(row["document"])


def update_job(job_id: str, **fields) -> dict:
    job = get_job(job_id)
    if job is None:
        raise KeyError(job_id)
    job.update(fields)
    job["updated_at"] = _now()
    return _save(job)


def latest_proposed() -> dict | None:
    init_db()
    with connect() as connection:
        row = connection.execute(
            "SELECT document FROM jobs WHERE status = 'proposed' ORDER BY updated_at DESC LIMIT 1"
        ).fetchone()
    if row is None:
        return None
    return json.loads(row["document"])


def list_jobs(limit: int = 12) -> list[dict]:
    init_db()
    with connect() as connection:
        rows = connection.execute(
            "SELECT document FROM jobs ORDER BY updated_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [json.loads(row["document"]) for row in rows]
