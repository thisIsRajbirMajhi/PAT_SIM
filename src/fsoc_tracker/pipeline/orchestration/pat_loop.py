"""End-to-end searching-to-tracking orchestration: frame -> detection -> estimate -> command.

Owns detector + tracker; accepts a gimbal controller instance (from camera/)
without owning it — avoids a camera<->pipeline import cycle (controller is
injected, pipeline only relies on its .step(estimate)/.reset()/.update_config()).
Order per ui/app MainWindow tick: detect(frame, predicted) -> track -> control.
"""
from ...common.types import ControlCommand, Detection, Estimate
from ..detection import BeaconDetector
from ..state import is_search_state
from ..track import Tracker


def _scheduled_hold(frame_id, cfg) -> bool:
    """True during blink-off / hidden schedule (predictable absence -> hold)."""
    try:
        from ...target.dynamics.visibility import is_blink_off, is_hidden
        return bool(is_blink_off(frame_id, cfg) or is_hidden(frame_id, cfg))
    except Exception:
        return False


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

    def _controller_ctx(self, detection, in_fov=None) -> dict:
        tctx = self.tracker.get_context() if hasattr(self.tracker, "get_context") else {}
        # Note: pat_loop sees only frame pixels (no gimbal handle), so
        # at_limit stays False here; the GUI and headless runners, which own
        # the camera, provide the real world-edge flag instead.
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
            "scheduled_hold": scheduled,
            "saturated": False,
            "at_limit": False,
        }

    def step_frame(self, frame_image, dt=None, in_fov=None):
        """One PAT tick on a raw frame image. Returns (detection, estimate, command|None)."""
        # Sensor detection/tracking runs every frame; the gimbal command is
        # held between control ticks so update_interval_hz is enforced.
        if dt is None:
            dt = self.control_dt
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
        scheduled = _scheduled_hold(self._frame_id, self.cfg)
        try:
            estimate = self.tracker.step(detection, frame_image, hold=hold)
        except TypeError:
            estimate = self.tracker.step(detection, frame_image)
        try:
            if getattr(estimate.tracking_state, "value", "") == "LOCKED":
                self._latched = True
        except Exception:
            pass
        command = None
        if self.controller is not None:
            if self._control_due():
                cctx = self._controller_ctx(detection, in_fov=in_fov)
                try:
                    command = self.controller.step(estimate, dt=dt, ctx=cctx)
                except TypeError:
                    command = self.controller.step(estimate, dt=dt)
                self._last_command = command
            else:
                command = self._last_command
                if command is None:
                    cctx = self._controller_ctx(detection, in_fov=in_fov)
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
