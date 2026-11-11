# Ambient Video

A local website that asks Gemini for a long-form ambient video idea. If you approve it, the app makes one still picture, a seamless sound loop, and a multi-hour video, then uploads that video to your YouTube channel.

The picture barely moves: a slow zoom out and back. Rain, wind, noise, and fire are the soundtrack, synthesized on this machine. Gemini does not generate the audio.

## Setup

You need Python 3.12 and ffmpeg.

```powershell
winget install Gyan.FFmpeg
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
```

Put your Gemini API key in `.env`:

```
GEMINI_API_KEY=your-key
```

Create a key in [Google AI Studio](https://aistudio.google.com/apikey).

### YouTube

1. In Google Cloud, create a project and enable **YouTube Data API v3**.
2. Configure the OAuth consent screen. Add the Google account that owns the channel as a test user while the app is in testing.
3. Create an OAuth client of type **Desktop app**.
4. Download the client JSON and save it in this folder as `client_secret.json`.

The default YouTube quota allows 100 uploads a day. New videos are **private** unless you choose Unlisted or Public. Custom thumbnails need a verified channel; if YouTube rejects the thumbnail, the video still uploads and the page tells you to add `thumbnail.jpg` in YouTube Studio.

Generated pictures include Google's SynthID watermark. A still image plus a looped sound can fall under YouTube's repetitious-content rules, so review a private upload before you publish it.

## Run

```powershell
.venv\Scripts\python -m uvicorn app.main:app --host 127.0.0.1 --port 8765
```

Open http://127.0.0.1:8765

1. Click **Connect YouTube** and sign in once. The token stays in `token.json` on this machine.
2. Choose a length (1, 3, 8, or 10 hours) and a privacy setting.
3. Click **Generate random video idea**.
4. **Decline** asks for a different idea. **Approve** builds the files under `output/` and uploads them.

If the upload fails, the mp4 stays on disk. Use **Retry upload** so the app does not render the video again.

To click through the page without API keys, set `AMBIENT_PREVIEW=1` in `.env` and restart. Preview mode uses three sample ideas, draws a gradient instead of calling Gemini, and does not upload.

## What gets saved

Each approved idea gets a folder in `output/`:

- `still.png` and `frame.png` — the picture
- `loop.wav` — a 60-second seamless sound loop
- `clip.mp4` — a 24-second slow zoom
- `video.mp4` — the long video
- `thumbnail.jpg`
- `metadata.json` — title, description, and tags

## Tests

```powershell
.venv\Scripts\python -m pytest
```

The ffmpeg test renders a 15-second video. It does not encode a full hour.
