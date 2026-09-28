"""Gimbal controller: PID track + case-routed smart search."""
import math

from .pid import PIDController
from ...common.types import Estimate, ControlCommand
from ...common.enums import TrackingState
from ...pipeline.state.search_policy import (
    SearchCase,
    SearchContext,
    classify_search_case,
    get_search_params,
)


def _cov_trace(estimate) -> float:
    try:
        cov = getattr(estimate, "covariance", None)
        if cov is None:
            return 5.0
        import numpy as np
        arr = np.asarray(cov, dtype=float)
        return float(np.trace(arr)) if arr.size else 5.0
    except Exception:
        return 5.0


def _vel_mag(estimate) -> float:
    try:
        vx, vy = getattr(estimate, "vel_angle", (0.0, 0.0))
        return float(math.hypot(float(vx), float(vy)))
    except Exception:
        return 0.0


class CameraController:
    def __init__(self, cfg):
        c = cfg["controller"]
        self.pan_pid = PIDController(kp=c.get("kp_pan", 1.2), ki=c.get("ki", 0.05), kd=c.get("kd", 0.15), deadzone=c.get("deadzone_px", 2.0), integral_limit=c.get("integral_limit", 8.0))
        self.tilt_pid = PIDController(kp=c.get("kp_tilt", 1.2), ki=c.get("ki", 0.05), kd=c.get("kd", 0.15), deadzone=c.get("deadzone_px", 2.0), integral_limit=c.get("integral_limit", 8.0))
        self.max_pan = float(cfg["camera"]["max_pan_speed"])
        self.max_tilt = float(cfg["camera"]["max_tilt_speed"])
        self.feedforward = float(c.get("feedforward_gain", 0.0))
        self.update_hz = float(cfg["camera"].get("update_interval_hz", cfg["camera"].get("fps", 30.0)))
        self.dt = 1.0 / max(self.update_hz, 1)
        self.cfg = cfg
        self.params = get_search_params(cfg)
        # search state
        self.search_angle = 0.0
        self.search_radius = 0.0
        self.search_frames = 0
        self.raster_dir = 1.0
        self.raster_segment = 0
        self.last_case = SearchCase.TRACK
        self._build_scan_plan(cfg)
        self.max_slew = 25.0
        self.prev_pan_rate = 0.0
        self.prev_tilt_rate = 0.0

    def _build_scan_plan(self, cfg):
        try:
            res_w, res_h = cfg["camera"]["resolution"]
            fov_h = float(cfg["camera"]["fov_deg"][0])
            px_per_deg = float(res_w) / max(fov_h, 1e-6)
            world_w = float(cfg["world"]["width"])
            upd = max(float(cfg["camera"].get("update_interval_hz", cfg["camera"].get("fps", 30.0))), 1)
            pan_span = max(world_w - float(res_w), float(res_w)) / max(px_per_deg, 1e-6)
            cross_s = pan_span / max(self.max_pan, 0.5)
            self.spiral_phase_frames = int(round(float(self.params.get("spiral_phase_s", 3.0)) * upd))
            self.sweep_frames = max(20, int(round(cross_s * upd)))
        except Exception:
            self.spiral_phase_frames = 90
            self.sweep_frames = 50

    def update_config(self, cfg):
        self.cfg = cfg
        c = cfg["controller"]
        self.pan_pid.update_gains(kp=c.get("kp_pan"), ki=c.get("ki"), kd=c.get("kd"), deadzone=c.get("deadzone_px"), integral_limit=c.get("integral_limit"))
        self.tilt_pid.update_gains(kp=c.get("kp_tilt"), ki=c.get("ki"), kd=c.get("kd"), deadzone=c.get("deadzone_px"), integral_limit=c.get("integral_limit"))
        self.max_pan = float(cfg["camera"]["max_pan_speed"])
        self.max_tilt = float(cfg["camera"]["max_tilt_speed"])
        self.feedforward = float(c.get("feedforward_gain", 0.0))
        self.update_hz = float(cfg["camera"].get("update_interval_hz", cfg["camera"].get("fps", 30.0)))
        self.dt = 1.0 / max(self.update_hz, 1)
        self.params = get_search_params(cfg)
        self._build_scan_plan(cfg)

    def reset(self):
        self.pan_pid.reset(); self.tilt_pid.reset()
        self.search_angle = 0; self.search_radius = 0
        self.search_frames = 0
        self.raster_dir = 1.0
        self.raster_segment = 0
        self.last_case = SearchCase.TRACK
        self.prev_pan_rate = 0.0; self.prev_tilt_rate = 0.0

    def _build_ctx(self, estimate, ctx) -> SearchContext:
        ctx = dict(ctx or {})
        try:
            missed = int(ctx.get("missed", self.search_frames))
        except Exception:
            missed = self.search_frames
        try:
            ego = float(ctx.get("ego_rate", max(abs(self.prev_pan_rate),
                                                abs(self.prev_tilt_rate))))
        except Exception:
            ego = 0.0
        return SearchContext(
            state=getattr(estimate, "tracking_state", TrackingState.SEARCHING),
            missed=missed,
            det_valid=bool(ctx.get("det_valid", False)),
            det_conf=float(ctx.get("det_conf", 0.0) or 0.0),
            cand_frames=int(ctx.get("cand_frames", 0)),
            locked_frames=int(ctx.get("locked_frames", 0)),
            innovation=float(getattr(estimate, "innovation", 0.0) or 0.0),
            cov_trace=_cov_trace(estimate),
            vel_mag_deg_s=_vel_mag(estimate),
            in_fov=ctx.get("in_fov", None),
            saturated=bool(ctx.get("saturated", False)),
            at_limit=bool(ctx.get("at_limit", False)),
            latched=bool(ctx.get("latched", False)),
            scheduled_hold=bool(ctx.get("scheduled_hold", False)),
            search_frames=self.search_frames,
            ego_rate_deg_s=ego,
        )

    def _clamp_slew(self, pan_rate, tilt_rate, dt):
        pan_rate = max(-self.max_pan, min(self.max_pan, pan_rate))
        tilt_rate = max(-self.max_tilt, min(self.max_tilt, tilt_rate))
        max_delta = self.max_slew * dt
        dpan = pan_rate - self.prev_pan_rate
        if dpan > max_delta:
            pan_rate = self.prev_pan_rate + max_delta
        if dpan < -max_delta:
            pan_rate = self.prev_pan_rate - max_delta
        dtilt = tilt_rate - self.prev_tilt_rate
        if dtilt > max_delta:
            tilt_rate = self.prev_tilt_rate + max_delta
        if dtilt < -max_delta:
            tilt_rate = self.prev_tilt_rate - max_delta
        self.prev_pan_rate = float(pan_rate)
        self.prev_tilt_rate = float(tilt_rate)
        return float(pan_rate), float(tilt_rate)

    def _spiral_rates(self, cov_trace=5.0, informed=False):
        # Cold unlatched search uses the legacy fixed spiral exactly
        # (proven coverage); the uncertainty boost only engages with an
        # informed (latched) estimate, where wider covariance genuinely
        # means a wider area to cover.
        p = self.params
        try:
            if informed:
                boost = 1.0 + float(p.get("unc_scale", 0.6)) * min(
                    3.0, max(0.0, (float(cov_trace) - 5.0) / 10.0))
                boost = min(float(p.get("unc_max_boost", 2.5)), boost)
            else:
                boost = 1.0
        except Exception:
            boost = 1.0
        rmax = float(p.get("search_radius_max", 4.5)) * boost
        self.search_angle += float(p.get("search_angle_step", 0.45))
        self.search_radius = min(rmax, self.search_radius + float(p.get("search_radius_step", 0.09)))
        scale = float(p.get("search_rate_scale", 0.85))
        return (math.cos(self.search_angle) * self.search_radius * scale,
                math.sin(self.search_angle) * self.search_radius * scale)

    def _raster_rates(self):
        p = self.params
        sweep = max(20, getattr(self, "sweep_frames", 50))
        seg = (self.search_frames - getattr(self, "spiral_phase_frames", 90)) // sweep
        if seg != self.raster_segment:
            self.raster_segment = seg
            self.raster_dir *= -1.0
        pan_rate = self.raster_dir * self.max_pan * float(p.get("raster_pan_scale", 0.9))
        tilt_sign = 1.0 if ((seg // 2) % 2 == 0) else -1.0
        tilt_rate = tilt_sign * self.max_tilt * float(p.get("raster_tilt_scale", 0.35))
        return pan_rate, tilt_rate

    def step(self, estimate: Estimate, dt=None, ctx=None) -> ControlCommand:
        if dt is None:
            dt = self.dt
        state = estimate.tracking_state
        sctx = self._build_ctx(estimate, ctx)
        case = classify_search_case(sctx, self.params)
        self.last_case = case

        if state in (TrackingState.SEARCHING, TrackingState.REACQUIRING, TrackingState.FAILED):
            self.search_frames += 1
            sctx.search_frames = self.search_frames
            case = classify_search_case(sctx, self.params)
            self.last_case = case
            if case in (SearchCase.HOLD_SCHEDULED, SearchCase.GIVE_UP):
                pan_rate, tilt_rate = self._clamp_slew(0.0, 0.0, dt)
                return ControlCommand(pan_rate=pan_rate, tilt_rate=tilt_rate,
                                      saturated=False, search_mode=True,
                                      search_case=case.value)
            if case == SearchCase.SLEW_PREDICT:
                err_pan, err_tilt = estimate.pos_angle
                pan_rate = max(-self.max_pan, min(self.max_pan, float(err_pan) * 2.0))
                tilt_rate = max(-self.max_tilt, min(self.max_tilt, float(err_tilt) * 2.0))
                pan_rate, tilt_rate = self._clamp_slew(pan_rate, tilt_rate, dt)
                return ControlCommand(pan_rate=pan_rate, tilt_rate=tilt_rate,
                                      saturated=False, search_mode=True,
                                      search_case=case.value)
            if case == SearchCase.INTERCEPT:
                p = self.params
                err_pan, err_tilt = estimate.pos_angle
                vel_pan, vel_tilt = estimate.vel_angle
                lead = float(p.get("intercept_lead_s", 0.3))
                gain = float(p.get("intercept_gain", 2.0))
                pan_rate = (float(err_pan) + float(vel_pan) * lead) * gain
                tilt_rate = (float(err_tilt) + float(vel_tilt) * lead) * gain
                pan_rate, tilt_rate = self._clamp_slew(pan_rate, tilt_rate, dt)
                return ControlCommand(pan_rate=pan_rate, tilt_rate=tilt_rate,
                                      saturated=False, search_mode=True,
                                      search_case=case.value)
            if case == SearchCase.TILE:
                pan_rate, tilt_rate = self._raster_rates()
            else:  # EXPAND (default): legacy fixed spiral when cold,
                # uncertainty-scaled only with an informed estimate
                pan_rate, tilt_rate = self._spiral_rates(sctx.cov_trace, informed=bool(sctx.latched))
            pan_rate, tilt_rate = self._clamp_slew(pan_rate, tilt_rate, dt)
            return ControlCommand(pan_rate=pan_rate, tilt_rate=tilt_rate,
                                  saturated=False, search_mode=True,
                                  search_case=case.value)

        # Track path (CANDIDATE/ACQUIRING/LOCKED/TEMP_LOST)
        if case == SearchCase.HOLD_SCHEDULED:
            pan_rate, tilt_rate = self._clamp_slew(0.0, 0.0, dt)
            return ControlCommand(pan_rate=pan_rate, tilt_rate=tilt_rate,
                                  saturated=False, search_mode=False,
                                  search_case=case.value)
        if state == TrackingState.TEMP_LOST:
            err_pan, err_tilt = estimate.pos_angle
            pan_unsat = self.pan_pid.step(err_pan, dt) * 0.55
            tilt_unsat = self.tilt_pid.step(err_tilt, dt) * 0.55
        else:
            err_pan, err_tilt = estimate.pos_angle
            vel_pan, vel_tilt = estimate.vel_angle
            pan_unsat = self.pan_pid.step(err_pan, dt) + self.feedforward * vel_pan
            tilt_unsat = self.tilt_pid.step(err_tilt, dt) + self.feedforward * vel_tilt
        if case == SearchCase.STARE:
            # Weak cue: freeze/slow to confirm instead of chasing noise.
            scale = float(self.params.get("stare_rate_scale", 0.3))
            pan_unsat *= scale
            tilt_unsat *= scale

        pan = pan_unsat
        tilt = tilt_unsat
        saturated = False
        if pan > self.max_pan:
            pan = self.max_pan; saturated = True
        if pan < -self.max_pan:
            pan = -self.max_pan; saturated = True
        if tilt > self.max_tilt:
            tilt = self.max_tilt; saturated = True
        if tilt < -self.max_tilt:
            tilt = -self.max_tilt; saturated = True

        if saturated:
            self.pan_pid.back_calculate_anti_windup(pan_unsat, pan, dt)
            self.tilt_pid.back_calculate_anti_windup(tilt_unsat, tilt, dt)
        if estimate.innovation > 18:
            self.pan_pid.decay_integral(0.92)
            self.tilt_pid.decay_integral(0.92)
        if state == TrackingState.TEMP_LOST:
            self.pan_pid.decay_integral(0.96)
            self.tilt_pid.decay_integral(0.96)

        max_delta = self.max_slew * dt
        dpan = pan - self.prev_pan_rate
        if dpan > max_delta:
            pan = self.prev_pan_rate + max_delta; saturated = True
        if dpan < -max_delta:
            pan = self.prev_pan_rate - max_delta; saturated = True
        dtilt = tilt - self.prev_tilt_rate
        if dtilt > max_delta:
            tilt = self.prev_tilt_rate + max_delta; saturated = True
        if dtilt < -max_delta:
            tilt = self.prev_tilt_rate - max_delta; saturated = True

        self.prev_pan_rate = float(pan)
        self.prev_tilt_rate = float(tilt)

        if state == TrackingState.LOCKED:
            self.search_radius *= 0.9
        self.search_frames = 0
        self.raster_segment = 0

        out_case = case.value if case in (SearchCase.STARE, SearchCase.HOLD_SCHEDULED) else SearchCase.TRACK.value
        return ControlCommand(pan_rate=float(pan), tilt_rate=float(tilt),
                              saturated=saturated, search_mode=False,
                              search_case=out_case)
