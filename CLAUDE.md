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

## Legacy System Context (Old Architecture)

This project (Fluger API) is a **rewrite** of the old Python-based blade controller. The original source code is lost, but the client-side components survive in two sibling projects. Understanding them explains *why* this project's API is shaped the way it is.

### Old System — Three-Tier Architecture

```
┌─────────────────────────┐
│  vdnh-navigation (Vue)  │  ← 3D map kiosk UI, route calculation, user interaction
│  port 3000 (via app.js) │
└───────────┬─────────────┘
            │ REST + WebSocket
┌───────────▼─────────────┐
│  vdnh-app (Node.js)     │  ← proxy/orchestrator, priority queue, multi-blade management
│  port 3001              │
└───────────┬─────────────┘
            │ raw TCP / JSON (line-delimited)
┌───────────▼─────────────┐
│  Old Python controller  │  ← per-blade: GPIO stepper, LEDs, video, Hall sensor
│  (on each Raspberry Pi) │     ← source code LOST
└─────────────────────────┘
```

### vdnh-navigation (Vue frontend)

**Repo:** `front_vdnh-navigation` — Vue 3 + TypeScript + Three.js kiosk app for VDNH.

- Renders interactive 3D map (GLTF models via Three.js), multilingual (RU/EN/ZH).
- User clicks a POI → backend calculates shortest path → returns `angle` (bearing 0-359°).
- On compact/kiosk displays, sends blade command via fluger bridge:
  ```
  POST /api/fluger/navigation
  { category, distance, text, deg: angle, color }
  ```
- Idle detection → sends `POST /api/fluger/idle { mode: "idle_VDNH" | ... }`.
- WebSocket `/ws/fluger` for real-time blade status monitoring.
- Also has panorama viewer, events page, RussPass integration, voice navigation.
- Key file: `src/shared/api/flugerBridge.ts` — HTTP/WS client for blade communication.
- Config in `public/config.js`: `FLUGER_SERVER`, `FLUGER_CONNECT` (blade IPs/ports), `FLUGER_CAMERA_ROTATION` (offset).

### vdnh-app (Node.js proxy server)

**Repo:** `front_vdnh-app` — Express server bridging frontend ↔ blade hardware.

**Two servers:**
- `app.js` (port 3000) — serves Vue build, error logging with source-map resolution, auto-update from central API.
- `main-server.js` (port 3001) — fluger control API + WebSocket broadcast.

**TCP protocol to blades (`index.js`):**
- Raw TCP sockets, JSON messages line-delimited (`\n`).
- On connect: sends full blade config (GPIO pins, motor params, LED settings) as JSON.
- Commands: `{ reqType, deg, namefile, screenplay, hexcolour, hexcolour2 }`.
- Blade responses are Russian-language status strings:
  - `"Запущена калибровка"` → initialization
  - `"Fluger готов к работе"` → ready
  - `"Запущен шаговый двигатель"` → motor running
  - `"Ожидание команды для воспроизведения"` → waiting for video start
  - `"Началось воспроизведение видео"` → video playing
  - `"Запрос клиента выполнен"` → command done
  - `"Ping"` / `"Pong"` — heartbeat

**Priority queue system (3 queues):**
1. **Performance** (highest) — `reqType: "performance"` / `"representation"` — can interrupt anything.
2. **Navigation** (medium) — `reqType: "navigation"` / `"navigation_null"` — can interrupt idle.
3. **Secondary** (lowest) — `reqType: "idle"` / `"trinity"` / `"reset"` — background animations.

**Idle cycle:** rotates through preset modes (idle_self_presentation → trinity_ruspass → idle_Moscow → ...) with random angles, random palette colors, and LED screenplay patterns.

**Multi-blade sync:** waits for all blades to reach "waiting for video" state before sending synchronized `"Старт видео"` command.

**Reconnection:** auto-retry every 15s; on reconnect restores last idle command via `blade.lastIdleCommand`.

**Config:** `config.json` holds per-blade hardware config (IP, port, GPIO pins, motor params, LED pixel count, brightness). `fluger.json` has command templates and idle animation sequences.

### Why This Matters for the New Fluger API

- The new project (this repo) replaces the old Python blade controller that ran on each Pi.
- The old system had 3 blades managed by a central Node.js orchestrator; this project runs standalone per-blade.
- Old protocol was TCP/JSON with Russian status strings; new protocol is HTTP REST + WebSocket.
- Old system bundled LED control, motor, and video in one command (`reqType` + `namefile` + `screenplay` + colors); new API separates stepper (`/api/rotate`) and video (`/api/play`).
- The navigation frontend (`vdnh-navigation`) currently calls the old Node proxy; adapting it to call this API directly would remove the middle layer.
