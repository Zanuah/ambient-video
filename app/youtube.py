"""YouTube OAuth and a resumable upload. Videos default to private."""

from __future__ import annotations

import signal
import threading
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from app.config import client_secret_path, token_path
from app.ideas import normalize_tags, tags_for_video

SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    # Needed to remove a video after a replacement upload. youtube.upload cannot delete.
    "https://www.googleapis.com/auth/youtube.force-ssl",
]
# YouTube category 10 is Music, which is where ambient soundscapes are usually filed.
MUSIC_CATEGORY = "10"
INSERT_PARTS = "snippet,status,recordingDetails,paidProductPlacementDetails"
CHICAGO = ZoneInfo("America/Chicago")
UTC = ZoneInfo("UTC")
_token_lock = threading.Lock()
THUMBNAIL_WARNING = (
    "The video uploaded, but YouTube did not accept the thumbnail. "
    "Add thumbnail.jpg from the job folder in YouTube Studio. "
    "The channel may need to be verified before custom thumbnails work."
)
AUDIO_LANGUAGE_WARNING = "The video uploaded, but YouTube did not accept the English audio language."
STUDIO_WARNING = (
    "The video uploaded, but YouTube Studio did not save the location or the caption certification. "
    "Open the video in YouTube Studio, set the location to San Antonio, Texas, "
    "choose never aired on television, and click Save."
)


def recording_date(recorded_at: datetime | None = None) -> str:
    """Midnight at the start of the San Antonio calendar day, as UTC."""
    current = recorded_at or datetime.now(CHICAGO)
    if current.tzinfo is None:
        current = current.replace(tzinfo=CHICAGO)
    else:
        current = current.astimezone(CHICAGO)
    local_midnight = current.replace(hour=0, minute=0, second=0, microsecond=0)
    return local_midnight.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def build_insert_body(
    title: str,
    description: str,
    tags: list[str],
    privacy: str,
    recorded_at: datetime | None = None,
) -> dict:
    if privacy not in {"private", "unlisted", "public"}:
        raise ValueError("Privacy must be private, unlisted, or public.")
    return {
        "snippet": {
            "title": title,
            "description": description,
            "tags": normalize_tags(tags),
            "categoryId": MUSIC_CATEGORY,
            "defaultLanguage": "en",
        },
        "status": {
            "privacyStatus": privacy,
            "selfDeclaredMadeForKids": False,
            "containsSyntheticMedia": True,
        },
        "recordingDetails": {
            "recordingDate": recording_date(recorded_at),
        },
        "paidProductPlacementDetails": {
            "hasPaidProductPlacement": False,
        },
    }


def build_audio_language_body(
    video_id: str,
    title: str,
    description: str,
    tags: list[str],
    category_id: str,
) -> dict:
    """videos.update clears omitted snippet fields, so send the whole snippet."""
    return {
        "id": video_id,
        "snippet": {
            "title": title,
            "description": description,
            "tags": tags,
            "categoryId": category_id,
            "defaultLanguage": "en",
            "defaultAudioLanguage": "en",
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

    with _token_lock:
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
    sound_profile: str | None = None,
    purpose: str | None = None,
    notify_subscribers: bool = True,
    apply_studio: bool = True,
) -> tuple[str, str | None]:
    from googleapiclient.errors import HttpError
    from googleapiclient.http import MediaFileUpload

    service = _service()
    if sound_profile and purpose:
        tags = tags_for_video(tags, sound_profile, purpose)
    body = build_insert_body(title, description, tags, privacy)
    media = MediaFileUpload(video_path, mimetype="video/mp4", resumable=True, chunksize=8 * 1024 * 1024)
    request = service.videos().insert(
        part=INSERT_PARTS,
        body=body,
        media_body=media,
        notifySubscribers=notify_subscribers,
    )
    video_id = resumable_upload(request)["id"]
    warnings: list[str] = []
    try:
        service.videos().update(
            part="snippet",
            body=build_audio_language_body(
                video_id,
                title,
                description,
                body["snippet"]["tags"],
                MUSIC_CATEGORY,
            ),
        ).execute()
    except HttpError:
        warnings.append(AUDIO_LANGUAGE_WARNING)
    if thumbnail_path and Path(thumbnail_path).exists():
        try:
            service.thumbnails().set(
                videoId=video_id,
                media_body=MediaFileUpload(thumbnail_path, mimetype="image/jpeg"),
            ).execute()
        except HttpError:
            warnings.append(THUMBNAIL_WARNING)
    if apply_studio:
        try:
            from app.studio import apply_studio_settings

            apply_studio_settings(video_id)
        except Exception:
            warnings.append(STUDIO_WARNING)
    return video_id, " ".join(warnings) or None
