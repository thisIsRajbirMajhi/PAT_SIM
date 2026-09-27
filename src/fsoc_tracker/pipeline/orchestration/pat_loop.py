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


class SearchTrackPipeline:
    def __init__(self, cfg, controller=None):
        self.cfg = cfg
        self.detector = BeaconDetector(cfg)
        self.tracker = Tracker(cfg)
        self.controller = controller
        self.dt = 1.0 / max(float(cfg["camera"]["fps"]), 1)

    def attach_controller(self, controller):
        self.controller = controller
        return self

    def reset(self):
        self.tracker.reset()
        if self.controller is not None:
            self.controller.reset()

    def update_config(self, cfg):
        self.cfg = cfg
        self.dt = 1.0 / max(float(cfg["camera"]["fps"]), 1)
        self.detector.update_config(cfg)
        self.tracker.update_config(cfg)
        if self.controller is not None:
            self.controller.update_config(cfg)

    def step_frame(self, frame_image, dt=None):
        """One PAT tick on a raw frame image. Returns (detection, estimate, command|None)."""
        if dt is None:
            dt = self.dt
        predicted = self.tracker.get_predicted_pixel()
        try:
            detection = self.detector.detect(frame_image, predicted_pos=predicted)
        except Exception:
            detection = self.detector.detect(frame_image)
        estimate = self.tracker.step(detection, frame_image)
        command = None
        if self.controller is not None:
            command = self.controller.step(estimate, dt=dt)
        return detection, estimate, command

    def searching(self):
        return is_search_state(self.tracker.last_estimate.tracking_state)


__all__ = ["SearchTrackPipeline"]
