import asyncio
import json
import logging
import logging.handlers
import shutil
import subprocess
import sys
import time as _time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, Request, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

import config as cfg
from stepper import Stepper

# ── Logging setup ────────────────────────────────────

_LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"

def _setup_logging():
    root = logging.getLogger()
    root.setLevel(logging.INFO)

    formatter = logging.Formatter(_LOG_FORMAT)

    # Console (stderr)
    console = logging.StreamHandler()
    console.setFormatter(formatter)
    root.addHandler(console)

    # File with rotation
    log_dir = Path(__file__).parent / cfg.LOG_DIR
    log_dir.mkdir(exist_ok=True)
    file_handler = logging.handlers.RotatingFileHandler(
        log_dir / "fluger.log",
        maxBytes=cfg.LOG_MAX_BYTES,
        backupCount=cfg.LOG_BACKUP_COUNT,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    root.addHandler(file_handler)

_setup_logging()
log = logging.getLogger("fluger")

stepper = Stepper()

BASE_DIR = Path(__file__).parent
FRONTEND_DIR = BASE_DIR / cfg.FRONTEND_DIR
VIDEOS_DIR = BASE_DIR / cfg.VIDEOS_DIR
PLAYER_DIR = BASE_DIR / cfg.PLAYER_DIR


def _log_config():
    log.info("=== Fluger configuration ===")
    log.info("Server: %s:%d", cfg.SERVER_HOST, cfg.SERVER_PORT)
    log.info("Frontend dir: %s (exists: %s)", FRONTEND_DIR, FRONTEND_DIR.is_dir())
    log.info("Videos dir: %s", VIDEOS_DIR)
    log.info("Player dir: %s (exists: %s)", PLAYER_DIR, PLAYER_DIR.is_dir())
    log.info("GPIO pins: DIR=%d STEP=%d ENA=%d HALL=%d",
             cfg.DIR_PIN, cfg.STEP_PIN, cfg.ENA_PIN, cfg.HALL_PIN)
    log.info("Motor: degstep=%.1f microstep=%d factor=%d",
             cfg.DEGSTEP, cfg.MICROSTEP, cfg.FACTOR)
    log.info("Browser: enabled=%s size=%dx%d pos=(%d,%d)",
             cfg.BROWSER_ENABLED, cfg.BROWSER_WIDTH, cfg.BROWSER_HEIGHT,
             cfg.BROWSER_X, cfg.BROWSER_Y)
    log.info("Max video size: %d MB", cfg.MAX_VIDEO_SIZE_MB)
    log.info("Log rotation: %d bytes, %d backups",
             cfg.LOG_MAX_BYTES, cfg.LOG_BACKUP_COUNT)
    log.info("==============================")


# ── Player state ──────────────────────────────────────

_player_state: dict = {
    "connected": False,
    "playing": False,
    "video": None,
    "loop": False,
    "started_at": None,
}


def _update_player_state(**kwargs):
    _player_state.update(kwargs)


# ── WebSocket connection managers ─────────────────────

class ConnectionManager:
    def __init__(self, name: str = "ws"):
        self._name = name
        self._connections: set[WebSocket] = set()

    @property
    def count(self) -> int:
        return len(self._connections)

    @property
    def has_connections(self) -> bool:
        return len(self._connections) > 0

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self._connections.add(ws)
        log.info("%s: client connected (%d total)", self._name, self.count)

    def disconnect(self, ws: WebSocket):
        self._connections.discard(ws)
        log.info("%s: client disconnected (%d total)", self._name, self.count)

    async def broadcast(self, message: dict):
        data = json.dumps(message)
        dead: list[WebSocket] = []
        for ws in self._connections:
            try:
                await ws.send_text(data)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self._connections.discard(ws)
            log.warning("%s: dropped dead connection (%d total)", self._name, self.count)


player_manager = ConnectionManager("player")
control_manager = ConnectionManager("control")


# ── Browser launcher ──────────────────────────────────

def _find_chrome() -> Optional[str]:
    if sys.platform == "win32":
        for name in ("chrome", "chromium"):
            path = shutil.which(name)
            if path:
                return path
        import os
        for prog in (
            os.environ.get("PROGRAMFILES", ""),
            os.environ.get("PROGRAMFILES(X86)", ""),
            os.environ.get("LOCALAPPDATA", ""),
        ):
            if not prog:
                continue
            for sub in (
                "Google/Chrome/Application/chrome.exe",
                "Chromium/Application/chrome.exe",
            ):
                p = Path(prog) / sub
                if p.is_file():
                    return str(p)
        return None
    # macOS: check known .app bundle paths
    if sys.platform == "darwin":
        for app in (
            "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
            "/Applications/Chromium.app/Contents/MacOS/Chromium",
        ):
            if Path(app).is_file():
                return app
    # Linux (Raspberry Pi) and macOS fallback: check PATH
    for name in ("chromium-browser", "chromium", "google-chrome", "google-chrome-stable"):
        path = shutil.which(name)
        if path:
            return path
    return None


_browser_proc: Optional[subprocess.Popen] = None


def _launch_browser():
    global _browser_proc
    chrome = _find_chrome()
    if not chrome:
        log.warning("Chrome/Chromium not found — player browser not launched")
        return

    # Use separate user-data-dir to avoid reusing existing Chrome instance
    # (otherwise Chrome just passes URL to existing process and exits immediately)
    user_data_dir = BASE_DIR / getattr(cfg, "BROWSER_USER_DATA_DIR", "chrome_profile")
    user_data_dir.mkdir(exist_ok=True)

    url = f"http://127.0.0.1:{cfg.SERVER_PORT}/player/"
    args = [
        chrome,
        f"--user-data-dir={user_data_dir}",
        f"--app={url}",
        "--autoplay-policy=no-user-gesture-required",
        "--disable-infobars",
        "--no-first-run",
        "--disable-session-crashed-bubble",
        "--disable-features=TranslateUI",
        "--disable-translate",
        "--lang=en-US",
        "--noerrdialogs",
    ]

    w, h = cfg.BROWSER_WIDTH, cfg.BROWSER_HEIGHT
    if w > 0 and h > 0:
        args.append(f"--window-size={w},{h}")
        args.append(f"--window-position={cfg.BROWSER_X},{cfg.BROWSER_Y}")
    else:
        args.append("--kiosk")

    _browser_proc = subprocess.Popen(args)
    log.info("Browser launched: PID %d, profile: %s", _browser_proc.pid, user_data_dir)


def _kill_browser():
    global _browser_proc
    if _browser_proc is None:
        return
    if _browser_proc.poll() is None:
        _browser_proc.terminate()
        try:
            _browser_proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            _browser_proc.kill()
            _browser_proc.wait(timeout=3)
        log.info("Browser closed")
    _browser_proc = None


def _is_browser_alive() -> bool:
    return _browser_proc is not None and _browser_proc.poll() is None


# ── Browser watchdog ──────────────────────────────────

_watchdog_task: Optional[asyncio.Task] = None


async def _browser_watchdog():
    interval = getattr(cfg, "BROWSER_WATCHDOG_INTERVAL", 10)
    while True:
        await asyncio.sleep(interval)
        # If player is connected via WebSocket, browser is working regardless of process state
        if player_manager.has_connections:
            continue
        # No WebSocket connection and process is dead — relaunch
        if not _is_browser_alive():
            log.warning("Browser process died and player not connected — relaunching")
            try:
                _launch_browser()
            except Exception:
                log.exception("Failed to relaunch browser")


# ── Video info helper ─────────────────────────────────

def _get_video_duration(filepath: Path) -> Optional[float]:
    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        return None
    try:
        result = subprocess.run(
            [
                ffprobe, "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                str(filepath),
            ],
            capture_output=True, text=True, timeout=10,
        )
        return float(result.stdout.strip())
    except Exception:
        return None


# ── Filename sanitization ─────────────────────────────

def _safe_filename(raw: str) -> str:
    name = Path(raw).name
    if not name or name.startswith(".") or name in (".", ".."):
        raise HTTPException(400, "Invalid filename")
    return name


# ── Lifespan ──────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    global _watchdog_task
    _log_config()
    VIDEOS_DIR.mkdir(exist_ok=True)

    try:
        stepper.initialize()
    except ImportError:
        log.info("RPi.GPIO not available — stepper disabled")
    except Exception:
        log.exception("Stepper initialization failed")

    if cfg.BROWSER_ENABLED:
        try:
            _launch_browser()
        except Exception:
            log.exception("Browser launch failed — continuing without browser")

        _watchdog_task = asyncio.create_task(_browser_watchdog())

    log.info("Fluger API ready")
    yield

    log.info("Shutdown started")
    if _watchdog_task:
        _watchdog_task.cancel()
        try:
            await _watchdog_task
        except asyncio.CancelledError:
            pass

    _kill_browser()
    stepper.cleanup()
    log.info("Shutdown complete")


app = FastAPI(title="Fluger API", lifespan=lifespan)


# ── HTTP error logging middleware ────────────────────

@app.middleware("http")
async def log_errors_middleware(request: Request, call_next):
    try:
        response = await call_next(request)
    except Exception:
        log.exception("Unhandled error: %s %s", request.method, request.url.path)
        raise
    if response.status_code >= 400:
        log.warning("HTTP %d: %s %s", response.status_code,
                    request.method, request.url.path)
    return response


# ── Request models ────────────────────────────────────

class RotateRequest(BaseModel):
    deg: float = Field(ge=0, lt=360)


class PlayRequest(BaseModel):
    video: str
    text: Optional[str] = None
    loop: bool = False
    text_config: Optional[dict] = None


# ── Stepper endpoints ─────────────────────────────────

@app.post("/api/rotate")
async def rotate(body: RotateRequest):
    if not stepper.available:
        raise HTTPException(503, "Stepper not available (no GPIO)")
    log.info("Rotate request: %.2f°", body.deg)
    result = await asyncio.to_thread(stepper.rotate_to, body.deg)
    log.info("Rotate complete: position=%.2f°", result.get("position", 0))
    return result


@app.get("/api/position")
def get_position():
    return {"position": stepper.current_degrees}


@app.post("/api/calibrate")
async def calibrate():
    if not stepper.available:
        raise HTTPException(503, "Stepper not available (no GPIO)")
    log.info("Calibration started")
    result = await asyncio.to_thread(stepper.calibrate)
    log.info("Calibration result: %s", result)
    return result


# ── Video management endpoints ────────────────────────

@app.get("/api/videos")
def list_videos():
    files = [
        f.name for f in VIDEOS_DIR.iterdir()
        if f.is_file() and f.suffix.lower() in cfg.ALLOWED_VIDEO_EXTENSIONS
    ]
    return {"videos": sorted(files)}


@app.get("/api/videos/{filename}/info")
async def video_info(filename: str):
    name = _safe_filename(filename)
    filepath = VIDEOS_DIR / name
    if not filepath.is_file():
        raise HTTPException(404, "Video not found")
    duration = await asyncio.to_thread(_get_video_duration, filepath)
    return {
        "filename": name,
        "size": filepath.stat().st_size,
        "duration": duration,
    }


@app.post("/api/videos/upload")
async def upload_video(file: UploadFile):
    name = _safe_filename(file.filename)
    ext = Path(name).suffix.lower()
    if ext not in cfg.ALLOWED_VIDEO_EXTENSIONS:
        raise HTTPException(400, f"Extension {ext} not allowed")

    dest = VIDEOS_DIR / name
    max_bytes = cfg.MAX_VIDEO_SIZE_MB * 1024 * 1024
    size = 0
    try:
        with open(dest, "wb") as f:
            while chunk := await file.read(1024 * 1024):
                size += len(chunk)
                if size > max_bytes:
                    raise HTTPException(413, f"File exceeds {cfg.MAX_VIDEO_SIZE_MB} MB limit")
                f.write(chunk)
    except HTTPException:
        dest.unlink(missing_ok=True)
        raise

    log.info("Video uploaded: %s (%d bytes)", name, size)
    return {"filename": name, "size": size}


@app.delete("/api/videos/{filename}")
def delete_video(filename: str):
    name = _safe_filename(filename)
    filepath = VIDEOS_DIR / name
    if not filepath.is_file():
        raise HTTPException(404, "Video not found")
    filepath.unlink()
    log.info("Video deleted: %s", name)
    return {"deleted": name}


# ── Player control endpoints ──────────────────────────

@app.post("/api/play")
async def play(body: PlayRequest):
    name = _safe_filename(body.video)
    video_file = VIDEOS_DIR / name
    if not video_file.is_file():
        raise HTTPException(404, f"Video '{name}' not found")

    log.info("Play: video=%s loop=%s text=%s", name, body.loop,
             repr(body.text[:50]) if body.text else None)

    _update_player_state(
        playing=True,
        video=name,
        loop=body.loop,
        started_at=_time.time(),
    )

    message = {
        "action": "play",
        "video": name,
        "text": body.text,
        "loop": body.loop,
        "text_config": body.text_config,
    }
    await player_manager.broadcast(message)

    await control_manager.broadcast({
        "event": "play_started",
        "video": name,
        "text": body.text,
        "loop": body.loop,
    })

    return {"status": "ok", "clients": player_manager.count}


@app.post("/api/stop")
async def stop():
    log.info("Stop playback (was playing: %s)", _player_state.get("video"))
    _update_player_state(playing=False, video=None, loop=False, started_at=None)
    await player_manager.broadcast({"action": "stop"})
    await control_manager.broadcast({"event": "play_stopped"})
    return {"status": "ok"}


@app.get("/api/player/status")
def player_status():
    return {
        **_player_state,
        "connected": player_manager.has_connections,
    }


# ── WebSocket: player ────────────────────────────────

@app.websocket("/ws/player")
async def ws_player(ws: WebSocket):
    await player_manager.connect(ws)
    await control_manager.broadcast({"event": "player_connected"})
    _update_player_state(connected=True)
    try:
        while True:
            raw = await ws.receive_text()
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                continue

            event = msg.get("event")
            if event == "ended":
                _update_player_state(playing=False, video=None, started_at=None)
                await control_manager.broadcast({
                    "event": "video_ended",
                    "video": _player_state.get("video"),
                })
                log.info("Player reported: video ended")
            elif event == "error":
                _update_player_state(playing=False)
                await control_manager.broadcast({
                    "event": "video_error",
                    "video": _player_state.get("video"),
                    "message": msg.get("message", ""),
                })
                log.warning("Player reported error: %s", msg.get("message", ""))
    except WebSocketDisconnect:
        pass
    except Exception:
        log.exception("Player WebSocket error")
    finally:
        player_manager.disconnect(ws)
        _update_player_state(connected=player_manager.has_connections)
        if not player_manager.has_connections:
            _update_player_state(playing=False, video=None, started_at=None)
        await control_manager.broadcast({"event": "player_disconnected"})


# ── WebSocket: control ────────────────────────────────

@app.websocket("/ws/control")
async def ws_control(ws: WebSocket):
    await control_manager.connect(ws)
    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        pass
    except Exception:
        log.exception("Control WebSocket error")
    finally:
        control_manager.disconnect(ws)


# ── Health ────────────────────────────────────────────

@app.get("/health")
def health():
    browser_status = "disabled"
    if cfg.BROWSER_ENABLED:
        browser_status = "running" if _is_browser_alive() else "stopped"

    return {
        "healthy": True,
        "stepper": "available" if stepper.available else "unavailable",
        "player": "connected" if player_manager.has_connections else "disconnected",
        "browser": browser_status,
    }


# ── Static mounts ─────────────────────────────────────

if VIDEOS_DIR.is_dir():
    app.mount("/videos", StaticFiles(directory=VIDEOS_DIR), name="videos")

if PLAYER_DIR.is_dir():
    app.mount("/player", StaticFiles(directory=PLAYER_DIR, html=True), name="player_static")

for name in ("assets", "img"):
    static_dir = FRONTEND_DIR / name
    if static_dir.is_dir():
        app.mount(f"/{name}", StaticFiles(directory=static_dir), name=name)


# ── Frontend SPA catch-all ────────────────────────────

@app.get("/{path:path}")
def serve_frontend(path: str):
    file = FRONTEND_DIR / path
    if file.is_file():
        return FileResponse(file)
    index = FRONTEND_DIR / "index.html"
    if index.is_file():
        return FileResponse(index)
    return {"detail": "Frontend not deployed"}


# ── Entry point with auto-restart ─────────────────────

if __name__ == "__main__":
    import uvicorn

    while True:
        try:
            log.info("Starting Fluger API on %s:%d", cfg.SERVER_HOST, cfg.SERVER_PORT)
            uvicorn.run(app, host=cfg.SERVER_HOST, port=cfg.SERVER_PORT)
            break  # clean exit
        except KeyboardInterrupt:
            log.info("Shutdown requested")
            break
        except SystemExit:
            break
        except Exception:
            log.exception("Server crashed — restarting in 3 seconds")
            _time.sleep(3)
