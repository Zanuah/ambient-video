# Clean, build, and start Ambient Video, then open it in the browser.
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    Write-Error "Install Docker Desktop, then run this script again."
}

if (-not (Test-Path .env)) {
    Copy-Item .env.example .env
    Write-Host "Created .env from .env.example. Put your GEMINI_API_KEY in it, then run this script again if the key was empty."
}
if (-not (Test-Path client_secret.json)) {
    New-Item -ItemType File -Path client_secret.json | Out-Null
    Write-Host "Created an empty client_secret.json. Replace it with your YouTube OAuth desktop client before connecting YouTube."
}
if (-not (Test-Path token.json)) {
    New-Item -ItemType File -Path token.json | Out-Null
}
New-Item -ItemType Directory -Force -Path output, data | Out-Null

Write-Host "Clean"
docker compose down --remove-orphans --rmi local

Write-Host "Build"
docker compose build

Write-Host "Start"
docker compose up -d --wait --force-recreate

Write-Host "Open"
Start-Process "http://127.0.0.1:8765"
