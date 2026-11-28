#!/usr/bin/env bash
# Clean, build, and start Ambient Video, then open it in the browser.
set -euo pipefail
cd "$(dirname "$0")"

if ! command -v docker >/dev/null 2>&1; then
  echo "Install Docker Desktop, then run this script again." >&2
  exit 1
fi

if [[ ! -f .env ]]; then
  cp .env.example .env
  echo "Created .env from .env.example. Put your GEMINI_API_KEY in it, then run this script again if the key was empty."
fi
if [[ ! -f client_secret.json ]]; then
  touch client_secret.json
  echo "Created an empty client_secret.json. Replace it with your YouTube OAuth desktop client before connecting YouTube."
fi
if [[ ! -f token.json ]]; then
  touch token.json
fi
mkdir -p output data

echo "Clean"
docker compose down --remove-orphans --rmi local

echo "Build"
docker compose build

echo "Start"
docker compose up -d --wait --force-recreate

echo "Open"
open "http://127.0.0.1:8765"
