"""Regression tests for the scheduled-hold controller context (Prompt.md S5).

Covers the latent `NameError` in the original `pat_loop._controller_ctx`
(which referenced an undefined `scheduled` variable): the hold flag must
flow explicitly from the blink/hidden schedule into the controller ctx,
for both `Frame` and raw-array inputs.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import numpy as np

from fsoc_tracker.common.data import Frame
from fsoc_tracker.config.loader import load_config
from pat_pipeline import SearchTrackPipeline


class _CtxCapture:
    """Minimal controller stand-in recording every ctx it receives."""

    def __init__(self):
        self.ctxs = []
        self.calls = 0

    def step(self, estimate, dt=None, ctx=None):
        self.calls += 1
        self.ctxs.append(dict(ctx or {}))

        class _Cmd:
            pan_rate = 0.0
            tilt_rate = 0.0
            saturated = False
            search_case = "CAPTURED"

        return _Cmd()

    def reset(self):
        self.ctxs.clear()
        self.calls = 0

    def update_config(self, cfg):
        pass


def _blink_cfg():
    cfg = load_config()
    cfg["target"]["blink_rate_hz"] = 5.0
    cfg["camera"]["fps"] = 30.0
    return cfg


def test_controller_ctx_carries_explicit_scheduled_hold():
    """_controller_ctx must accept scheduled_hold explicitly (no NameError)."""
    from fsoc_tracker.common.data import Detection

    pipe = SearchTrackPipeline(load_config(), controller=_CtxCapture())
    det = Detection(valid=False)
    ctx_off = pipe._controller_ctx(det, scheduled_hold=False)
    ctx_on = pipe._controller_ctx(det, scheduled_hold=True)
    assert ctx_off["scheduled_hold"] is False
    assert ctx_on["scheduled_hold"] is True


def test_step_frame_sets_scheduled_hold_during_blink_off():
    """Frame 3 at 5 Hz blink / 30 fps is blink-off -> ctx flag True."""
    cap = _CtxCapture()
    pipe = SearchTrackPipeline(_blink_cfg(), controller=cap)
    img = np.zeros((480, 640), dtype=np.uint8)
    for fid in range(4):
        pipe.step_frame(Frame(image=img, frame_id=fid, timestamp=fid / 30.0))
    assert cap.calls == 4
    assert cap.ctxs[0]["scheduled_hold"] is False
    assert cap.ctxs[3]["scheduled_hold"] is True


def test_step_frame_accepts_raw_array_and_frame():
    """Raw ndarray and Frame inputs produce identical detect/track results."""
    cfg = load_config()
    pipe = SearchTrackPipeline(cfg, controller=None)
    img = np.zeros((480, 640), dtype=np.uint8)
    det_raw, est_raw, cmd_raw = pipe.step_frame(img)
    assert cmd_raw is None  # no controller attached
    pipe.reset()
    det_fr, est_fr, _ = pipe.step_frame(
        Frame(image=img, frame_id=0, timestamp=0.0)
    )
    assert det_raw.valid == det_fr.valid
    assert (est_raw.pos_px is None) == (est_fr.pos_px is None)
