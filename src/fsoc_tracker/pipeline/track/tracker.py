"""Tracker — canonical implementation (moved from tracking/tracker.py).

Owns IMM + TrackingStateMachine; predict -> update -> state -> Estimate.
"""
from ...common.types import Detection, Estimate, Frame
from ..estimation import IMM
from ..state import TrackingStateMachine


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
        # propagate so EKF measurement noise / jitter / process noise refresh
        try:
            self.imm.update_config(cfg)
        except Exception:
            try:
                self.imm.cfg = cfg
            except Exception:
                pass

    def step(self, detection: Detection, frame: Frame, hold: bool = False) -> Estimate:
        # predict
        self.imm.predict(self.dt)
        # update with detection if valid
        if detection.valid and detection.centroid_px is not None:
            z = detection.centroid_px
            conf = detection.confidence
            try:
                _missed = int(getattr(self.sm, "missed", 0))
            except Exception:
                _missed = 0
            # Acquisition after a long outage: the prior is pure accumulated
            # process noise, so re-seed at the measurement instead of
            # updating a fiction (prevents overconfident wrong velocity that
            # all later frames then gate-reject — cf. X8 sweep-past lock).
            if _missed > 30 and conf > 0.45 and hasattr(self.imm, "reseed"):
                try:
                    self.imm.reseed(z)
                except Exception:
                    pass
            self.imm.update(z, confidence=conf)
        else:
            self.imm.update(None, confidence=0.0)

        if hold:
            # Scheduled absence (blink/hidden): freeze state machine so the
            # outage does not count as misses; keep last state.
            state = self.sm.state
        else:
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

    def get_gate_radius_px(self, sigma: float = 3.0, min_px: float = 40.0,
                           max_px: float = 320.0, missed: int = 0) -> float:
        """3-sigma association gate (px) from fused covariance, grown by the
        predicted motion over the outage.

        Rejects bright clutter far from the prediction (crowded/star scenes)
        without affecting cold search (large P -> large gate, capped).
        Growth with `missed` frames is essential: right after a lock the
        covariance is small (overconfident) while the true error may already
        be large — a tight static gate would blind re-acquisition (X8).
        """
        try:
            import math
            import numpy as np
            P = np.asarray(self.imm.fused_P, dtype=float)
            # Pixel scale: project angle covariance via px/deg from config.
            res_w = float(self.cfg["camera"]["resolution"][0])
            fov_h = float(self.cfg["camera"]["fov_deg"][0])
            px_per_deg = res_w / max(fov_h, 1e-6)
            # fused state is [pan, tilt, vel..., ]; position block P[0:2,0:2]
            var_deg2 = max(float(P[0, 0]) + float(P[1, 1]), 1e-6) / 2.0
            gate = float(sigma * (var_deg2 ** 0.5) * px_per_deg)
            # outage growth: prediction drifts at |v| px/frame while unseen
            try:
                vx, vy = self.imm.get_velocity()
                vpx_f = math.hypot(float(vx), float(vy)) * px_per_deg * max(self.dt, 1e-3)
                gate += 1.5 * vpx_f * max(0, int(missed))
            except Exception:
                pass
            return float(min(max_px, max(min_px, gate)))
        except Exception:
            return float(max_px)

    def get_context(self) -> dict:
        """Lightweight facts for the search classifier (no GT)."""
        try:
            missed = int(getattr(self.sm, "missed", 0))
        except Exception:
            missed = 0
        try:
            cand = int(getattr(self.sm, "candidate_frames", 0))
        except Exception:
            cand = 0
        try:
            locked = int(getattr(self.sm, "locked_frames", 0))
        except Exception:
            locked = 0
        return {"missed": missed, "cand_frames": cand, "locked_frames": locked}
