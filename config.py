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
CW = 1            # clockwise direction value
CCW = 0           # counter-clockwise direction value
DEGSTEP = 1.8     # degrees per one full step
MICROSTEP = 10    # driver microstep multiplier (M542: SW5=OFF SW6=ON SW7=OFF SW8=ON → 2000 pulses/rev)
FACTOR = 480      # gear ratio: planetary 1:10 × external ~48:1 (confirmed empirically 2026-03-13)

# ── Speed profile — short distance (<=30 steps) ────
# Values from old production config (config.json blade 1)
SHORT_START_DELAY = 0.00001        # 10μs — from old config (Python min ~100μs)
SHORT_MAX_SPEED_DELAY = 0.00001    # 10μs — flat fast speed for small moves
SHORT_FIN_DELAY = 0.00004          # 40μs — gentle stop

# ── Speed profile — long distance (>30 steps) ──────
LONG_START_DELAY = 0.00001         # 10μs — fast start
LONG_MAX_SPEED_DELAY = 0.00002     # 20μs — cruising speed
LONG_FIN_DELAY = 0.00004           # 40μs — gentle stop

# ── Motion profile ─────────────────────────────────
ACCEL_PHASE = 0.20          # fraction of path for acceleration
DECEL_PHASE = 0.20          # fraction of path for deceleration
SMALL_DIST_THRESHOLD = 30   # steps; boundary between short/long profile

# ── Calibration ─────────────────────────────────────
HALL_OVERSHOOT_STEPS = 10000  # steps to pass Hall sensor before reversing (from old return_start())
HALL_SETTLE_TIME = 0.6        # seconds to wait after overshoot
CALIBRATION_REVOLUTIONS = 3

# ── Video ──────────────────────────────────────────
VIDEOS_DIR = "videos"
PLAYER_DIR = "player"
ALLOWED_VIDEO_EXTENSIONS = {".mp4", ".webm", ".avi", ".mkv", ".mov"}
MAX_VIDEO_SIZE_MB = 500

# ── Browser (player window) ──────────────────────────
BROWSER_ENABLED = False       # no displays connected yet
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
