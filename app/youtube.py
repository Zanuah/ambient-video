"""YouTube OAuth and a resumable upload. Videos default to private."""

from __future__ import annotations

import signal
import threading
from pathlib import Path

from app.config import client_secret_path, token_path
from app.ideas import normalize_tags

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]
# YouTube category 10 is Music, which is where ambient soundscapes are usually filed.
MUSIC_CATEGORY = "10"
THUMBNAIL_WARNING = (
    "The video uploaded, but YouTube did not accept the thumbnail. "
    "Add thumbnail.jpg from the job folder in YouTube Studio. "
    "The channel may need to be verified before custom thumbnails work."
)


def build_insert_body(title: str, description: str, tags: list[str], privacy: str) -> dict:
    if privacy not in {"private", "unlisted", "public"}:
        raise ValueError("Privacy must be private, unlisted, or public.")
    return {
        "snippet": {
            "title": title,
            "description": description,
            "tags": normalize_tags(tags),
            "categoryId": MUSIC_CATEGORY,
        },
        "status": {
            "privacyStatus": privacy,
            "selfDeclaredMadeForKids": False,
        },
    }


def resumable_upload(request) -> dict:
    response = None
    while response is None:
        _status, response = request.next_chunk()
    if not isinstance(response, dict) or "id" not in response:
        raise RuntimeError("YouTube did not return a video id.")
    return response


def load_credentials():
    path = token_path()
    if not path.exists():
        return None
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials

    creds = Credentials.from_authorized_user_file(str(path), SCOPES)
    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
        path.write_text(creds.to_json(), encoding="utf-8")
    if creds and creds.valid:
        return creds
    return None


def youtube_connected() -> bool:
    try:
        return load_credentials() is not None
    except Exception:
        return False


def run_oauth_flow():
    """Open the Google consent window and store a local token.

    google-auth calls signal.signal, which only works on the main thread.
    The Connect button runs in a worker thread, so ignore that restriction.
    """
    secret = client_secret_path()
    if not secret.exists():
        raise RuntimeError("Save your OAuth desktop client as client_secret.json in the project folder.")
    from google_auth_oauthlib.flow import InstalledAppFlow

    original = signal.signal

    def allow_worker_thread(signum, handler):
        try:
            return original(signum, handler)
        except ValueError:
            return None

    if threading.current_thread() is not threading.main_thread():
        signal.signal = allow_worker_thread
    try:
        flow = InstalledAppFlow.from_client_secrets_file(str(secret), SCOPES)
        creds = flow.run_local_server(port=0, open_browser=True, prompt="consent")
    finally:
        signal.signal = original
    token_path().write_text(creds.to_json(), encoding="utf-8")
    return creds


def _service():
    creds = load_credentials()
    if creds is None:
        raise RuntimeError("Connect YouTube before uploading.")
    from googleapiclient.discovery import build

    return build("youtube", "v3", credentials=creds)


def upload_files(
    video_path: str,
    thumbnail_path: str | None,
    title: str,
    description: str,
    tags: list[str],
    privacy: str,
) -> tuple[str, str | None]:
    from googleapiclient.errors import HttpError
    from googleapiclient.http import MediaFileUpload

    service = _service()
    body = build_insert_body(title, description, tags, privacy)
    media = MediaFileUpload(video_path, mimetype="video/mp4", resumable=True, chunksize=8 * 1024 * 1024)
    request = service.videos().insert(part="snippet,status", body=body, media_body=media)
    video_id = resumable_upload(request)["id"]
    warning = None
    if thumbnail_path and Path(thumbnail_path).exists():
        try:
            service.thumbnails().set(
                videoId=video_id,
                media_body=MediaFileUpload(thumbnail_path, mimetype="image/jpeg"),
            ).execute()
        except HttpError:
            warning = THUMBNAIL_WARNING
    return video_id, warning
