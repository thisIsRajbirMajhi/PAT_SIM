import time, numpy as np
from ..common.types import Frame, Detection, Estimate
from ..common.enums import TrackingState
from .imm import IMM
from .state_machine import TrackingStateMachine

class Tracker:
    def __init__(self, cfg):
        self.cfg = cfg
        self.imm = IMM(cfg)
        self.sm = TrackingStateMachine(cfg)
        self.dt = 1.0 / max(float(cfg["camera"]["fps"]), 1)
        self.last_estimate = Estimate()

    def reset(self):
        self.imm.reset()
        self.sm.reset()
        self.last_estimate = Estimate()

    def update_config(self, cfg):
        self.cfg = cfg
        self.dt = 1.0 / max(float(cfg["camera"]["fps"]), 1)
        # Rebuild IMM and SM to avoid stale parameters (Fix P1-06)
        self.imm = IMM(cfg)
        self.sm = TrackingStateMachine(cfg)

    def step(self, detection: Detection, frame: Frame) -> Estimate:
        # predict
        self.imm.predict(self.dt)
        # update with detection if valid
        if detection.valid and detection.centroid_px is not None:
            z = detection.centroid_px
            conf = detection.confidence
            self.imm.update(z, confidence=conf)
        else:
            self.imm.update(None, confidence=0.0)

        state = self.sm.update(detection.valid, detection.confidence if detection.valid else 0.0)

        # build estimate
        # IMM fused pixel -> angle already via fused state
        angle = self.imm.get_angle()
        vel = self.imm.get_velocity()
        pix = self.imm.get_pixel()
        # if we have detection, trust detection pixel for high confidence; else use predicted
        pos_px = (float(pix[0]), float(pix[1])) if pix is not None else None
        # Keep pos inside frame bounds check? Not needed

        est = Estimate(
            pos_px=pos_px,
            pos_angle=angle,
            vel_angle=vel,
            covariance=self.imm.fused_P.copy(),
            model_probs=tuple(float(x) for x in self.imm.probs),
            tracking_state=state,
            innovation=self.imm.last_nis
        )
        self.last_estimate = est
        return est

    def get_predicted_pixel(self):
        pix = self.imm.get_pixel()
        return (float(pix[0]), float(pix[1]))
