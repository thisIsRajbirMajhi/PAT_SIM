"""End-to-end searching-to-tracking orchestration: frame -> detection -> estimate -> command.

Owns detector + tracker; accepts a gimbal controller instance (from
pat_pipeline.camera) without owning it — avoids a camera<->pipeline import
cycle (controller is injected, pipeline only relies on its
.step(estimate)/.reset()/.update_config()).
Order per host tick (headless.py, ui/app MainWindow._tick):
detect(frame, predicted) -> track -> control.

The host supplies frames and applies returned commands with its own
camera/actuator adapter; ground truth must never enter this module.
"""

from fsoc_tracker.common.types import ControlCommand, Detection, Estimate
from fsoc_tracker.target.dynamics.visibility import is_blink_off, is_hidden

from ..detection import BeaconDetector
from ..state import is_search_state
from ..track import Tracker


def _scheduled_hold(frame_id, cfg) -> bool:
    """True during blink-off / hidden schedule (predictable absence -> hold)."""
    try:
        return bool(is_blink_off(frame_id, cfg) or is_hidden(frame_id, cfg))
    except Exception:
        return False


def _ego_scalar(ego_rate) -> float:
    """Normalize a scalar or (pan, tilt) ego-motion rate to max-abs deg/s."""
    try:
        if ego_rate is None:
            return 0.0
        if isinstance(ego_rate, (int, float)):
            return float(ego_rate)
        return max(abs(float(ego_rate[0])), abs(float(ego_rate[1])))
    except Exception:
        return 0.0


class SearchTrackPipeline:
    def __init__(self, cfg, controller=None):
        self.cfg = cfg
        self.detector = BeaconDetector(cfg)
        self.tracker = Tracker(cfg)
        self.controller = controller
        # Sr.15: sensor frames arrive at fps; gimbal control updates at
        # update_interval_hz. Both rates are enforced (see step_frame hold).
        self.sensor_dt = 1.0 / max(float(cfg["camera"].get("fps", 30.0)), 1)
        self.control_dt = 1.0 / max(float(cfg["camera"].get("update_interval_hz", cfg["camera"].get("fps", 30.0))), 1)
        self._frame_id = 0
        self._last_command = None
        self._latched = False

    def attach_controller(self, controller):
        self.controller = controller
        return self

    def reset(self):
        self.tracker.reset()
        self._frame_id = 0
        self._last_command = None
        self._latched = False
        if self.controller is not None:
            self.controller.reset()

    def update_config(self, cfg):
        self.cfg = cfg
        self.sensor_dt = 1.0 / max(float(cfg["camera"].get("fps", 30.0)), 1)
        self.control_dt = 1.0 / max(float(cfg["camera"].get("update_interval_hz", cfg["camera"].get("fps", 30.0))), 1)
        self.detector.update_config(cfg)
        self.tracker.update_config(cfg)
        if self.controller is not None:
            self.controller.update_config(cfg)

    def _control_due(self):
        """True when a gimbal update is due at update_interval_hz."""
        try:
            fps = max(float(self.cfg["camera"].get("fps", 30.0)), 1)
            upd = max(float(self.cfg["camera"].get("update_interval_hz", fps)), 1)
        except Exception:
            return True
        if upd >= fps:
            return True  # control at least as fast as sensor: every frame
        every = max(1, int(round(fps / upd)))
        return (self._frame_id % every) == 0

    def _controller_ctx(self, detection, scheduled_hold=False, in_fov=None, at_limit=False, ego_rate=0.0) -> dict:
        tctx = self.tracker.get_context() if hasattr(self.tracker, "get_context") else {}
        # Note: pat_loop sees only frame pixels (no gimbal handle by default),
        # so at_limit defaults False; runners that own the camera (GUI,
        # headless) pass the real world-edge flag instead.
        missed = int(tctx.get("missed", 0))
        return {
            "missed": missed,
            "cand_frames": tctx.get("cand_frames", 0),
            "locked_frames": tctx.get("locked_frames", 0),
            "det_valid": bool(getattr(detection, "valid", False)),
            "det_conf": float(getattr(detection, "confidence", 0.0) or 0.0),
            "in_fov": in_fov,
            # Latch decays: a track lost for >60 frames is cold again, so the
            # classifier returns to full-world TILE instead of INTERCEPTing a
            # stale prediction forever (cf. X8 recovery).
            "latched": bool(self._latched and missed <= 60),
            "scheduled_hold": bool(scheduled_hold),
            "saturated": False,
            "at_limit": bool(at_limit),
            "ego_rate": _ego_scalar(ego_rate),
        }

    def step_frame(self, frame, dt=None, in_fov=None, at_limit=False, ego_rate=0.0):
        """One PAT tick on a frame. Returns (detection, estimate, command|None).

        `frame` is a `Frame` (uses its `.image` and `.frame_id`) or a raw
        grayscale/BGR image array (falls back to the internal frame counter
        for schedule lookups). `in_fov`/`at_limit`/`ego_rate` are host-supplied
        camera context; the command is held between control ticks so
        update_interval_hz is enforced.
        """
        # Sensor detection/tracking runs every frame; the gimbal command is
        # held between control ticks so update_interval_hz is enforced.
        if dt is None:
            dt = self.control_dt
        frame_image = getattr(frame, "image", frame)
        frame_id = getattr(frame, "frame_id", self._frame_id)
        predicted = self.tracker.get_predicted_pixel()
        try:
            tctx0 = self.tracker.get_context() if hasattr(self.tracker, "get_context") else {}
        except Exception:
            tctx0 = {}
        try:
            _m0 = int(tctx0.get("missed", 0))
            fresh = bool(self._latched) and _m0 <= 30
            gate = self.tracker.get_gate_radius_px(missed=_m0) if (hasattr(self.tracker, "get_gate_radius_px") and fresh) else None
        except Exception:
            gate = None
        # Cold search (never latched) or stale prediction (long outage) ->
        # no gate so the full frame is eligible; latched fresh track ->
        # gated association against clutter.
        try:
            detection = self.detector.detect(frame_image, predicted_pos=predicted, gate_radius_px=gate)
        except TypeError:
            detection = self.detector.detect(frame_image, predicted_pos=predicted)
        except Exception:
            detection = self.detector.detect(frame_image)
        hold = False  # SM stays truthful (LOST->REACQUIRING); schedule only freezes the gimbal via ctx
        scheduled = _scheduled_hold(frame_id, self.cfg)
        try:
            _ego_t = (0.0, 0.0) if ego_rate in (None, 0.0, 0) else (
                (float(ego_rate), 0.0) if isinstance(ego_rate, (int, float)) else
                (float(ego_rate[0]), float(ego_rate[1])))
        except Exception:
            _ego_t = (0.0, 0.0)
        try:
            estimate = self.tracker.step(detection, frame, hold=hold, ego_rate=_ego_t)
        except TypeError:
            estimate = self.tracker.step(detection, frame)
        try:
            if getattr(estimate.tracking_state, "value", "") == "LOCKED":
                self._latched = True
        except Exception:
            pass
        command = None
        if self.controller is not None:
            if self._control_due():
                cctx = self._controller_ctx(detection, scheduled_hold=scheduled,
                                            in_fov=in_fov, at_limit=at_limit, ego_rate=ego_rate)
                try:
                    command = self.controller.step(estimate, dt=dt, ctx=cctx)
                except TypeError:
                    command = self.controller.step(estimate, dt=dt)
                self._last_command = command
            else:
                command = self._last_command
                if command is None:
                    cctx = self._controller_ctx(detection, scheduled_hold=scheduled,
                                                in_fov=in_fov, at_limit=at_limit, ego_rate=ego_rate)
                    try:
                        command = self.controller.step(estimate, dt=dt, ctx=cctx)
                    except TypeError:
                        command = self.controller.step(estimate, dt=dt)
                    self._last_command = command
        self._frame_id += 1
        return detection, estimate, command

    def searching(self):
        return is_search_state(self.tracker.last_estimate.tracking_state)


__all__ = ["SearchTrackPipeline"]
