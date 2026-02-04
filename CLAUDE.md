# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Fluger API — FastAPI backend for the "Neuro-Fluger" interactive installation (Raspberry Pi). Serves a Vue frontend, controls a stepper motor (blade rotation) via GPIO, and plays video with optional text overlay on the display. Designed for 24/7 unattended operation with auto-restart and browser watchdog.

## Commands

```bash
pip install -r requirements.txt
python main.py
```

Server auto-restarts on crash. Port and host configured in `config.py`.

## Architecture

- `config.py` — all configurable constants (pins, speeds, server, video, browser settings). New parameters always go here.
- `main.py` — FastAPI app with auto-restart, browser watchdog, WebSocket hub, REST API.
- `stepper.py` — stepper motor controller (GPIO, Hall sensor, trapezoidal speed, error recovery).
- `frontend/` — Vue build output (static assets, SPA with history-mode routing).
- `player/index.html` — fullscreen HTML5 video player with WebSocket control, CSS text overlay, event feedback.
- `player/config.js` — text overlay styling defaults (font, color, position, fade timings).
- `videos/` — uploaded video files storage.

## API Endpoints

### Stepper
- `POST /api/rotate` `{"deg": 0-359}` — rotate blade to absolute angle
- `GET /api/position` — current blade angle
- `POST /api/calibrate` — zero-point calibration via Hall sensor

### Video Management
- `GET /api/videos` — list uploaded videos
- `GET /api/videos/{filename}/info` — video duration (via ffprobe) and file size
- `POST /api/videos/upload` — upload video file (multipart form, field: `file`)
- `DELETE /api/videos/{filename}` — delete video

### Player Control
- `POST /api/play` `{"video": "file.mp4", "text": "optional", "loop": false, "text_config": {...}}` — play video
- `POST /api/stop` — stop playback
- `GET /api/player/status` — player state (connected, playing, video, started_at)

### WebSocket
- `WebSocket /ws/player` — player browser connection (bidirectional: commands + events)
- `WebSocket /ws/control` — controlling device receives real-time events (video_ended, player_connected, etc.)

### Other
- `GET /player/` — player page (auto-opened by Chrome on startup)
- `GET /health` — structured health check (stepper, player, browser status)
- `GET /{path}` — SPA catch-all

## Configuration

All hardcoded values live in `config.py`. When adding new parameters, always put them there.

Frontend text overlay config is in `player/config.js`.

## Dependencies

- **FastAPI** + **Uvicorn** — web framework and ASGI server
- **python-multipart** — file upload support
- **RPi.GPIO** — GPIO control (Raspberry Pi only, gracefully skipped on other platforms)
- **ffprobe** (optional) — video duration detection
