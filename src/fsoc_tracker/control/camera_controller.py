from .pid import PIDController
from ..common.types import Estimate, ControlCommand
from ..common.enums import TrackingState

class CameraController:
    def __init__(self, cfg):
        c = cfg["controller"]
        self.pan_pid = PIDController(kp=c.get("kp_pan",1.2), ki=c.get("ki",0.05), kd=c.get("kd",0.15), deadzone=c.get("deadzone_px",2.0), integral_limit=c.get("integral_limit",8.0))
        self.tilt_pid = PIDController(kp=c.get("kp_tilt",1.2), ki=c.get("ki",0.05), kd=c.get("kd",0.15), deadzone=c.get("deadzone_px",2.0), integral_limit=c.get("integral_limit",8.0))
        self.max_pan = float(cfg["camera"]["max_pan_speed"])
        self.max_tilt = float(cfg["camera"]["max_tilt_speed"])
        self.feedforward = float(c.get("feedforward_gain",0.0))
        self.dt = 1.0 / max(float(cfg["camera"]["fps"]), 1)
        self.cfg = cfg
        # search spiral state
        self.search_angle = 0.0
        self.search_radius = 0.0
        # slew-rate limiting (§6): max change of commanded rate per second
        self.max_slew = 25.0  # °/s per second (tuned: allows 0.8°/s per 30Hz tick, ~16% of max 5°/s)
        self.prev_pan_rate = 0.0
        self.prev_tilt_rate = 0.0

    def update_config(self, cfg):
        self.cfg = cfg
        c = cfg["controller"]
        self.pan_pid.update_gains(kp=c.get("kp_pan"), ki=c.get("ki"), kd=c.get("kd"), deadzone=c.get("deadzone_px"), integral_limit=c.get("integral_limit"))
        self.tilt_pid.update_gains(kp=c.get("kp_tilt"), ki=c.get("ki"), kd=c.get("kd"), deadzone=c.get("deadzone_px"), integral_limit=c.get("integral_limit"))
        self.max_pan = float(cfg["camera"]["max_pan_speed"])
        self.max_tilt = float(cfg["camera"]["max_tilt_speed"])
        self.feedforward = float(c.get("feedforward_gain",0.0))
        self.dt = 1.0 / max(float(cfg["camera"]["fps"]),1)

    def reset(self):
        self.pan_pid.reset(); self.tilt_pid.reset()
        self.search_angle=0; self.search_radius=0
        self.prev_pan_rate = 0.0; self.prev_tilt_rate = 0.0

    def step(self, estimate: Estimate, dt=None) -> ControlCommand:
        if dt is None: dt = self.dt
        state = estimate.tracking_state
        # if lost/reacquiring/searching -> search controller else PID
        if state in (TrackingState.SEARCHING, TrackingState.REACQUIRING, TrackingState.FAILED):
            # expanding spiral search — faster to meet ≤1s re-acq
            self.search_angle += 0.32
            self.search_radius = min(4.5, self.search_radius + 0.06)
            import math
            pan_rate = math.cos(self.search_angle) * self.search_radius * 0.85
            tilt_rate = math.sin(self.search_angle) * self.search_radius * 0.85
            # clamp to physical limits
            pan_rate = max(-self.max_pan, min(self.max_pan, pan_rate))
            tilt_rate = max(-self.max_tilt, min(self.max_tilt, tilt_rate))
            # slew-rate limit even in search (prevents jump when switching from track)
            max_delta = self.max_slew * dt
            dpan = pan_rate - self.prev_pan_rate
            if dpan > max_delta: pan_rate = self.prev_pan_rate + max_delta
            if dpan < -max_delta: pan_rate = self.prev_pan_rate - max_delta
            dtilt = tilt_rate - self.prev_tilt_rate
            if dtilt > max_delta: tilt_rate = self.prev_tilt_rate + max_delta
            if dtilt < -max_delta: tilt_rate = self.prev_tilt_rate - max_delta
            self.prev_pan_rate = float(pan_rate)
            self.prev_tilt_rate = float(tilt_rate)
            return ControlCommand(pan_rate=float(pan_rate), tilt_rate=float(tilt_rate), saturated=False, search_mode=True)

        if state == TrackingState.TEMP_LOST:
            # reduced aggressiveness, use velocity feedforward
            err_pan, err_tilt = estimate.pos_angle
            pan_unsat = self.pan_pid.step(err_pan, dt) * 0.55
            tilt_unsat = self.tilt_pid.step(err_tilt, dt) * 0.55
        else:
            err_pan, err_tilt = estimate.pos_angle
            # PID + optional feedforward from velocity
            vel_pan, vel_tilt = estimate.vel_angle
            pan_unsat = self.pan_pid.step(err_pan, dt) + self.feedforward * vel_pan
            tilt_unsat = self.tilt_pid.step(err_tilt, dt) + self.feedforward * vel_tilt

        # §6 saturation (physical limits)
        pan = pan_unsat
        tilt = tilt_unsat
        saturated = False
        if pan > self.max_pan: pan = self.max_pan; saturated=True
        if pan < -self.max_pan: pan = -self.max_pan; saturated=True
        if tilt > self.max_tilt: tilt = self.max_tilt; saturated=True
        if tilt < -self.max_tilt: tilt = -self.max_tilt; saturated=True

        # §6 anti-windup: back-calculation when saturated (prevents integral wind-up during loss/saturation)
        if saturated:
            self.pan_pid.back_calculate_anti_windup(pan_unsat, pan, dt)
            self.tilt_pid.back_calculate_anti_windup(tilt_unsat, tilt, dt)
        # §6 integral cautiously: freeze/decay when innovation high (low confidence) or TEMP_LOST
        if estimate.innovation > 18:
            self.pan_pid.decay_integral(0.92)
            self.tilt_pid.decay_integral(0.92)
        if state == TrackingState.TEMP_LOST:
            self.pan_pid.decay_integral(0.96)
            self.tilt_pid.decay_integral(0.96)

        # §6 slew-rate limiting: prevent unrealistic jumps (limit Δrate per dt)
        max_delta = self.max_slew * dt
        # pan slew
        dpan = pan - self.prev_pan_rate
        if dpan > max_delta: pan = self.prev_pan_rate + max_delta; saturated = True
        if dpan < -max_delta: pan = self.prev_pan_rate - max_delta; saturated = True
        # tilt slew
        dtilt = tilt - self.prev_tilt_rate
        if dtilt > max_delta: tilt = self.prev_tilt_rate + max_delta; saturated = True
        if dtilt < -max_delta: tilt = self.prev_tilt_rate - max_delta; saturated = True

        self.prev_pan_rate = float(pan)
        self.prev_tilt_rate = float(tilt)

        # if locked and error small, decay search
        if state == TrackingState.LOCKED:
            self.search_radius *= 0.9

        return ControlCommand(pan_rate=float(pan), tilt_rate=float(tilt), saturated=saturated, search_mode=False)
