import logging
import math
import time
from threading import Lock

import config as cfg

log = logging.getLogger("fluger.stepper")

try:
    import RPi.GPIO as _gpio

    GPIO_AVAILABLE = True
except ImportError:
    _gpio = None
    GPIO_AVAILABLE = False


class Stepper:
    def __init__(self):
        self.dir_pin = cfg.DIR_PIN
        self.step_pin = cfg.STEP_PIN
        self.ena_pin = cfg.ENA_PIN
        self.hall_pin = cfg.HALL_PIN
        self.cw = cfg.CW
        self.ccw = cfg.CCW
        self.degstep = cfg.DEGSTEP

        self.spr = 360 / self.degstep
        self.syscof = cfg.FACTOR * cfg.MICROSTEP

        self.max_speed_sd = cfg.SHORT_MAX_SPEED_DELAY
        self.start_delay_sd = cfg.SHORT_START_DELAY
        self.fin_delay_sd = cfg.SHORT_FIN_DELAY
        self.max_speed_ld = cfg.LONG_MAX_SPEED_DELAY
        self.start_delay_ld = cfg.LONG_START_DELAY
        self.fin_delay_ld = cfg.LONG_FIN_DELAY

        self._current_step = 0
        self._lock = Lock()
        self._gpio = None

    @property
    def available(self) -> bool:
        return self._gpio is not None

    @property
    def current_degrees(self) -> float:
        return (self._current_step / self.spr) * 360

    def initialize(self):
        if not GPIO_AVAILABLE:
            raise ImportError("RPi.GPIO unavailable")
        self._gpio = _gpio
        self._gpio.setmode(self._gpio.BCM)
        self._gpio.setwarnings(False)
        self._gpio.setup(self.dir_pin, self._gpio.OUT)
        self._gpio.setup(self.step_pin, self._gpio.OUT)
        self._gpio.setup(self.ena_pin, self._gpio.OUT)
        self._gpio.setup(self.hall_pin, self._gpio.IN)
        self._gpio.output(self.ena_pin, self._gpio.HIGH)

    def _try_reinitialize(self):
        log.warning("Attempting GPIO re-initialization")
        try:
            self.cleanup()
            self.initialize()
            log.info("GPIO re-initialized successfully")
            return True
        except Exception:
            log.exception("GPIO re-initialization failed")
            return False

    def rotate_to(self, degrees: float) -> dict:
        with self._lock:
            try:
                return self._rotate_to_inner(degrees)
            except (RuntimeError, OSError) as exc:
                log.error("Rotation failed: %s", exc)
                if self._try_reinitialize():
                    return self._rotate_to_inner(degrees)
                raise

    def _rotate_to_inner(self, degrees: float) -> dict:
        gpio = self._gpio
        target_step = math.trunc(degrees / self.degstep)
        diff = target_step - self._current_step

        if diff == 0:
            return {"position": self.current_degrees}

        direction = self.cw if diff > 0 else self.ccw
        if abs(diff) >= self.spr / 2:
            direction = self.ccw if diff > 0 else self.cw
            diff = self.spr - abs(diff)

        motor_steps = int(abs(diff) * self.syscof)

        if target_step == 0:
            self._return_to_zero()
        else:
            gpio.output(self.dir_pin, direction)
            time.sleep(0.05)
            self._move(motor_steps, diff)

        self._current_step = target_step
        return {"position": self.current_degrees}

    def calibrate(self) -> dict:
        with self._lock:
            try:
                return self._calibrate_inner()
            except (RuntimeError, OSError) as exc:
                log.error("Calibration failed: %s", exc)
                if self._try_reinitialize():
                    return self._calibrate_inner()
                raise

    def _calibrate_inner(self) -> dict:
        gpio = self._gpio
        gpio.output(self.ena_pin, gpio.LOW)
        time.sleep(1)

        steps = int(cfg.CALIBRATION_REVOLUTIONS * self.spr * self.syscof)
        accel = (self.max_speed_sd - self.start_delay_sd) / steps
        gpio.output(self.dir_pin, self.cw)

        try:
            # First attempt: accelerate then search
            for i in range(int(steps * cfg.ACCEL_PHASE)):
                self._pulse(self.start_delay_sd + accel * i)

            for _ in range(steps):
                self._pulse(self.max_speed_sd)
                if gpio.input(self.hall_pin) == 0:
                    gpio.output(self.step_pin, gpio.LOW)
                    self._current_step = 0
                    gpio.output(self.ena_pin, gpio.HIGH)
                    time.sleep(2)
                    gpio.output(self.ena_pin, gpio.HIGH)
                    return {"status": "ok", "position": 0}
            else:
                # Second attempt if first pass didn't find the sensor
                log.warning("Hall sensor not found on first pass, retrying...")
                time.sleep(5)
                gpio.output(self.dir_pin, self.cw)

                for i in range(int(steps * cfg.ACCEL_PHASE)):
                    self._pulse(self.start_delay_sd + accel * i)

                for _ in range(steps):
                    self._pulse(self.max_speed_sd)
                    if gpio.input(self.hall_pin) == 0:
                        gpio.output(self.step_pin, gpio.LOW)
                        self._current_step = 0
                        gpio.output(self.ena_pin, gpio.HIGH)
                        time.sleep(2)
                        gpio.output(self.ena_pin, gpio.HIGH)
                        return {"status": "ok", "position": 0}

                return {"status": "error", "message": "Hall sensor not found"}
        finally:
            gpio.output(self.ena_pin, gpio.LOW)
            gpio.output(self.step_pin, gpio.LOW)

    def cleanup(self):
        if self._gpio:
            try:
                self._gpio.cleanup()
            except Exception:
                log.exception("GPIO cleanup error")
            self._gpio = None

    # -- internal --

    def _pulse(self, delay: float):
        self._gpio.output(self.step_pin, self._gpio.HIGH)
        time.sleep(delay)
        self._gpio.output(self.step_pin, self._gpio.LOW)
        time.sleep(delay)

    def _move(self, steps: int, step_diff: float):
        if steps == 0:
            return
        if 0 < abs(step_diff) <= cfg.SMALL_DIST_THRESHOLD:
            self._accel_move(steps, self.start_delay_sd, self.max_speed_sd, self.fin_delay_sd)
        else:
            self._accel_move(steps, self.start_delay_ld, self.max_speed_ld, self.fin_delay_ld)

    def _accel_move(self, steps: int, start_delay: float, max_delay: float, fin_delay: float):
        gpio = self._gpio
        accel = (max_delay - start_delay) / steps
        decel = -(max_delay - fin_delay) / steps
        ramp_up_end = int(steps * cfg.ACCEL_PHASE)
        ramp_down_start = int(steps * (1 - cfg.DECEL_PHASE))

        gpio.output(self.ena_pin, gpio.LOW)
        try:
            for i in range(ramp_up_end):
                self._pulse(start_delay + accel * i)
            for _ in range(ramp_up_end, ramp_down_start):
                self._pulse(max_delay)
            for i in range(ramp_down_start, steps):
                self._pulse(max_delay + decel * (i - ramp_down_start))
        finally:
            gpio.output(self.ena_pin, gpio.LOW)
            gpio.output(self.step_pin, gpio.LOW)

    def _return_to_zero(self):
        gpio = self._gpio
        direction = self.cw if self._current_step <= self.spr / 2 else self.ccw
        gpio.output(self.dir_pin, direction)
        gpio.output(self.ena_pin, gpio.LOW)

        hall_found = False
        max_steps = int(cfg.CALIBRATION_REVOLUTIONS * self.spr * self.syscof)

        try:
            for _ in range(max_steps):
                self._pulse(self.start_delay_sd)

                if gpio.input(self.hall_pin) == 0 and not hall_found:
                    hall_found = True
                    if direction == self.ccw:
                        for _ in range(cfg.HALL_OVERSHOOT_STEPS):
                            self._pulse(self.start_delay_sd)
                        time.sleep(cfg.HALL_SETTLE_TIME)
                        direction = self.cw
                        gpio.output(self.dir_pin, direction)
                        hall_found = False

                if hall_found and gpio.input(self.hall_pin) == 0:
                    break

            self._current_step = 0
        finally:
            gpio.output(self.ena_pin, gpio.LOW)
            gpio.output(self.step_pin, gpio.LOW)
