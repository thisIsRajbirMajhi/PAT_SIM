"""Behavior tests for the canonical pipeline (Prompt.md S9).

All tests drive real components (no mocked detector/estimator): a seeded
synthetic source closes the loop through SearchTrackPipeline.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import numpy as np

from fsoc_tracker.common.data import Frame
from fsoc_tracker.config.loader import load_config
from fsoc_tracker.input.synthetic_source import SyntheticSource
from pat_pipeline import make_pipeline


def _cued_run(cfg, frames=150, seed=7):
    """Run the canonical pipeline against a cued synthetic source."""
    source = SyntheticSource(cfg, seed=seed)
    pipe = make_pipeline(cfg)
    pipe.reset()
    source.reset()
    source.cue_camera_to_target()
    fps = float(cfg["camera"]["fps"])
    upd = float(cfg["camera"].get("update_interval_hz", fps))
    dt_ctrl = 1.0 / max(upd, 1)
    history = []
    for _ in range(frames):
        frame, gt = source.read()
        if frame is None:
            break
        try:
            in_fov = source.camera.world_to_image(gt.world_pos) is not None
        except Exception:
            in_fov = None
        try:
            at_lim = bool(
                source.camera.is_at_limit(
                    pipe.controller.prev_pan_rate, pipe.controller.prev_tilt_rate
                )
            )
        except Exception:
            at_lim = False
        ego = (pipe.controller.prev_pan_rate, pipe.controller.prev_tilt_rate)
        detection, estimate, cmd = pipe.step_frame(
            frame, dt=dt_ctrl, in_fov=in_fov, at_limit=at_lim, ego_rate=ego
        )
        source.apply_camera_command(cmd.pan_rate, cmd.tilt_rate, dt_ctrl)
        history.append((detection, estimate, cmd))
    return pipe, source, history


def test_cold_start_acquires_and_locks():
    """Cued cold start: CANDIDATE -> ACQUIRING -> LOCKED via the real chain."""
    cfg = load_config()
    pipe, _source, history = _cued_run(cfg)
    assert history, "no frames processed"
    det0, est0, _cmd0 = history[0]
    assert det0.valid, "cued first frame must detect"
    states = [e.tracking_state.value for _d, e, _c in history]
    assert "CANDIDATE" in states
    assert "LOCKED" in states
    first_lock = states.index("LOCKED")
    assert first_lock < 120, f"lock took {first_lock} frames"


def test_stale_prediction_does_not_block_search():
    """A never-latched pipeline searches the full frame (no gate)."""
    cfg = load_config()
    pipe = make_pipeline(cfg)
    img = np.zeros((480, 640), dtype=np.uint8)
    img[95:105, 495:505] = 255  # 10x10 blob: above min_area, far from centre
    det, _est, _cmd = pipe.step_frame(img)
    assert pipe._latched is False
    # Full-frame eligibility: the blob is found despite being far from centre.
    assert det.valid


def test_miss_loss_and_reacquisition():
    """Blank outage drives TEMP_LOST/REACQUIRING; target return re-locks."""
    cfg = load_config()
    pipe, source, history = _cued_run(cfg, frames=60)
    states = [e.tracking_state.value for _d, e, _c in history]
    assert "LOCKED" in states
    blank = np.zeros((480, 640), dtype=np.uint8)
    outage_states = []
    for fid in range(40):
        _det, est, _cmd = pipe.step_frame(
            Frame(image=blank, frame_id=1000 + fid, timestamp=1000.0 + fid)
        )
        outage_states.append(est.tracking_state.value)
    assert "TEMP_LOST" in outage_states
    assert "REACQUIRING" in outage_states
    relock = []
    for _ in range(60):
        frame, gt = source.read()
        in_fov = source.camera.world_to_image(gt.world_pos) is not None
        ego = (pipe.controller.prev_pan_rate, pipe.controller.prev_tilt_rate)
        _det, est, cmd = pipe.step_frame(frame, in_fov=in_fov, ego_rate=ego)
        source.apply_camera_command(cmd.pan_rate, cmd.tilt_rate, pipe.control_dt)
        relock.append(est.tracking_state.value)
    assert "LOCKED" in relock


def test_control_updates_at_configured_rate_and_holds():
    """With update_interval_hz = fps/2, odd ticks reuse the held command."""
    cfg = load_config()
    cfg["camera"]["fps"] = 30.0
    cfg["camera"]["update_interval_hz"] = 15.0
    pipe = make_pipeline(cfg)
    blank = np.zeros((480, 640), dtype=np.uint8)
    cmds = [pipe.step_frame(blank)[2] for _ in range(4)]
    assert all(c is not None for c in cmds)
    assert cmds[1] is cmds[0], "odd tick must hold the previous command"
    assert cmds[2] is not cmds[0], "even tick must recompute the command"
    assert cmds[3] is cmds[2]


def test_ego_rate_reaches_controller_ctx():
    """Tuple ego rates are normalized to a scalar in the controller ctx."""
    from fsoc_tracker.common.data import Detection

    cfg = load_config()
    pipe = make_pipeline(cfg)
    ctx = pipe._controller_ctx(Detection(valid=False), ego_rate=(2.0, -1.0))
    assert ctx["ego_rate"] == 2.0
    ctx0 = pipe._controller_ctx(Detection(valid=False), ego_rate=0.0)
    assert ctx0["ego_rate"] == 0.0
