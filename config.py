# ── Server ──────────────────────────────────────────
SERVER_HOST = "0.0.0.0"
SERVER_PORT = 8001
FRONTEND_DIR = "frontend"

# ── GPIO pins ───────────────────────────────────────
DIR_PIN = 20      # direction
STEP_PIN = 21     # step pulse
ENA_PIN = 22      # driver enable (LOW = active)
HALL_PIN = 2      # Hall sensor (zero-point)

# ── Motor ───────────────────────────────────────────
CW = 0            # clockwise direction value
CCW = 1           # counter-clockwise direction value
DEGSTEP = 1.8     # degrees per one full step
MICROSTEP = 8     # driver microstep multiplier
FACTOR = 50       # gear ratio

# ── Speed profile — short distance (<=30 steps) ────
SHORT_START_DELAY = 0.00002
SHORT_MAX_SPEED_DELAY = 0.000020
SHORT_FIN_DELAY = 0.0003           # was 0.0010 — reduced for faster deceleration

# ── Speed profile — long distance (>30 steps) ──────
LONG_START_DELAY = 0.000010        # was 0.000014
LONG_MAX_SPEED_DELAY = 0.000010    # was 0.000015
LONG_FIN_DELAY = 0.000020          # was 0.00003

# ── Motion profile ─────────────────────────────────
ACCEL_PHASE = 0.15          # fraction of path for acceleration (was 0.2)
DECEL_PHASE = 0.15          # fraction of path for deceleration (was 0.2)
SMALL_DIST_THRESHOLD = 30   # steps; boundary between short/long profile

# ── Calibration ─────────────────────────────────────
HALL_OVERSHOOT_STEPS = 10000  # steps to pass Hall sensor before reversing
HALL_SETTLE_TIME = 0.6        # seconds to wait after overshoot
CALIBRATION_REVOLUTIONS = 3

# ── Video ──────────────────────────────────────────
VIDEOS_DIR = "videos"
PLAYER_DIR = "player"
ALLOWED_VIDEO_EXTENSIONS = {".mp4", ".webm", ".avi", ".mkv", ".mov"}
MAX_VIDEO_SIZE_MB = 500

# ── Browser (player window) ──────────────────────────
BROWSER_ENABLED = True        # launch browser on startup
BROWSER_X = 0                 # window X position (px)
BROWSER_Y = 0                 # window Y position (px)
BROWSER_WIDTH = 1536          # window width (px), 0 = kiosk/fullscreen
BROWSER_HEIGHT = 256          # window height (px), 0 = kiosk/fullscreen
BROWSER_WATCHDOG_INTERVAL = 10  # seconds between browser liveness checks
BROWSER_USER_DATA_DIR = "chrome_profile"  # separate Chrome profile to avoid reusing existing instance

# ── Logging ──────────────────────────────────────────
LOG_DIR = "logs"
LOG_MAX_BYTES = 5 * 1024 * 1024   # 5 MB per file
LOG_BACKUP_COUNT = 3              # keep 3 rotated copies
