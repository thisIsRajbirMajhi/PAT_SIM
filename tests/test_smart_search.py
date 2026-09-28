"""Smart-search tests: classifier routing, controller modes, gating, hold, metrics."""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import numpy as np

from fsoc_tracker.common.data.estimation import Estimate
from fsoc_tracker.common.enums import TrackingState
from fsoc_tracker.config.loader import load_config
from fsoc_tracker.pipeline.state.search_policy import (
    SearchCase,
    SearchContext,
    classify_search_case,
    get_search_params,
)
from fsoc_tracker.camera.control.camera_controller import CameraController
from fsoc_tracker.pipeline.track.tracker import Tracker
from fsoc_tracker.evaluation.metrics import MetricsCollector


def _est(state=TrackingState.SEARCHING, pos=(1.0, 0.5), vel=(0.0, 0.0), nis=0.5):
    return Estimate(
        pos_px=(320.0, 240.0),
        pos_angle=pos,
        vel_angle=vel,
        covariance=np.eye(6) * 5.0,
        model_probs=(0.6, 0.25, 0.15),
        tracking_state=state,
        innovation=nis,
    )


def _ctx(**kw):
    base = dict(state=TrackingState.SEARCHING, missed=10, det_valid=False,
                det_conf=0.0, cand_frames=0, locked_frames=0, innovation=0.5,
                cov_trace=30.0, vel_mag_deg_s=0.0, in_fov=None, saturated=False,
                at_limit=False, latched=False, scheduled_hold=False, search_frames=10)
    base.update(kw)
    return SearchContext(**base)


def test_params_single_source():
    cfg = load_config()
    p = get_search_params(cfg)
    for k in ("search_angle_step", "search_radius_max", "spiral_phase_s",
              "stare_rate_scale", "intercept_gain", "give_up_frames"):
        assert k in p


def test_classifier_routes_all_cases():
    assert classify_search_case(_ctx(state=TrackingState.LOCKED)) == SearchCase.TRACK
    assert classify_search_case(_ctx(state=TrackingState.LOCKED, det_valid=True, det_conf=0.2)) == SearchCase.STARE
    assert classify_search_case(_ctx(scheduled_hold=True)) == SearchCase.HOLD_SCHEDULED
    assert classify_search_case(_ctx(search_frames=10**6, missed=10**6)) == SearchCase.GIVE_UP
    assert classify_search_case(_ctx(at_limit=True)) == SearchCase.EXPAND
    fast = _ctx(in_fov=False, missed=5, vel_mag_deg_s=5.0, search_frames=5, latched=True)
    assert classify_search_case(fast) == SearchCase.INTERCEPT
    fresh = _ctx(in_fov=False, missed=5, vel_mag_deg_s=0.1, search_frames=5, latched=True)
    assert classify_search_case(fresh) == SearchCase.SLEW_PREDICT
    cold_offscreen = _ctx(in_fov=False, missed=5, vel_mag_deg_s=0.0, search_frames=5, latched=False)
    assert classify_search_case(cold_offscreen) == SearchCase.EXPAND
    stale = _ctx(in_fov=False, missed=30, vel_mag_deg_s=5.0, search_frames=5, latched=True)
    assert classify_search_case(stale) == SearchCase.EXPAND
    # sweep-past loss: camera slewing fast pollutes filter velocity, so even
    # a fresh latched estimate must not drive prediction moves
    sweeping = _ctx(in_fov=False, missed=5, vel_mag_deg_s=5.0, search_frames=5,
                    latched=True, ego_rate_deg_s=4.0)
    assert classify_search_case(sweeping) == SearchCase.EXPAND
    steady_fast = _ctx(in_fov=False, missed=5, vel_mag_deg_s=5.0, search_frames=5,
                       latched=True, ego_rate_deg_s=0.3)
    assert classify_search_case(steady_fast) == SearchCase.INTERCEPT
    edge_slew = _ctx(in_fov=False, missed=5, vel_mag_deg_s=0.1, search_frames=5,
                     latched=True, at_limit=True)
    assert classify_search_case(edge_slew) == SearchCase.HOLD_SCHEDULED
    edge_tile = _ctx(in_fov=None, missed=100, latched=False, search_frames=500, at_limit=True)
    assert classify_search_case(edge_tile) == SearchCase.TILE
    cold = _ctx(in_fov=None, missed=100, latched=False, search_frames=500)
    assert classify_search_case(cold) == SearchCase.TILE
    short = _ctx(in_fov=None, missed=10, latched=True, search_frames=10)
    assert classify_search_case(short) == SearchCase.EXPAND


def test_controller_search_cases_move_and_hold():
    cfg = load_config()
    ctrl = CameraController(cfg)
    # EXPAND moves
    cmd = ctrl.step(_est(TrackingState.SEARCHING), dt=1 / 30,
                    ctx=dict(missed=10, det_valid=False, det_conf=0.0, in_fov=None,
                             latched=True, scheduled_hold=False))
    assert cmd.search_mode and cmd.search_case == SearchCase.EXPAND.value
    assert abs(cmd.pan_rate) + abs(cmd.tilt_rate) > 0
    # HOLD freezes
    ctrl.reset()
    cmd = ctrl.step(_est(TrackingState.SEARCHING), dt=1 / 30,
                    ctx=dict(missed=10, det_valid=False, det_conf=0.0,
                             scheduled_hold=True))
    assert cmd.search_case == SearchCase.HOLD_SCHEDULED.value
    assert cmd.pan_rate == 0.0 and cmd.tilt_rate == 0.0
    # SLEW_PREDICT drives toward error
    ctrl.reset()
    cmd = ctrl.step(_est(TrackingState.SEARCHING, pos=(2.0, -1.0)), dt=1 / 30,
                    ctx=dict(missed=5, det_valid=False, det_conf=0.0,
                             in_fov=False, latched=True, scheduled_hold=False))
    assert cmd.search_case == SearchCase.SLEW_PREDICT.value
    assert cmd.pan_rate > 0 and cmd.tilt_rate < 0
    # GIVE_UP holds at zero
    ctrl.reset()
    cmd = ctrl.step(_est(TrackingState.SEARCHING), dt=1 / 30,
                    ctx=dict(missed=10**6, det_valid=False, det_conf=0.0))
    assert cmd.search_case == SearchCase.GIVE_UP.value
    assert cmd.pan_rate == 0.0 and cmd.tilt_rate == 0.0


def test_controller_stare_slows_track():
    cfg = load_config()
    c1 = CameraController(cfg)
    c2 = CameraController(cfg)
    est = _est(TrackingState.LOCKED, pos=(0.2, 0.1))
    full = c1.step(est, dt=1 / 30, ctx=dict(det_valid=True, det_conf=0.9))
    stare = c2.step(est, dt=1 / 30, ctx=dict(det_valid=True, det_conf=0.2))
    assert stare.search_case == SearchCase.STARE.value
    assert abs(stare.pan_rate) < abs(full.pan_rate)


def test_tracker_hold_freezes_state_and_gate_bounds():
    cfg = load_config()
    tr = Tracker(cfg)
    from fsoc_tracker.common.data.detection import Detection
    from fsoc_tracker.common.data.frame import Frame
    frame = Frame(image=np.zeros((10, 10), dtype=np.uint8), frame_id=0, timestamp=0.0)
    tr.step(Detection(valid=True, confidence=0.9, centroid_px=(320.0, 240.0)), frame)
    # hold=True is a manual freeze hook (not used by the live loop: the SM
    # stays truthful through scheduled outages so LOST->REACQUIRING is honest;
    # only the gimbal holds via controller ctx).
    missed_before = tr.sm.missed
    tr.step(Detection(valid=False), frame, hold=True)
    assert tr.sm.missed == missed_before
    tr.step(Detection(valid=False), frame, hold=False)
    assert tr.sm.missed == missed_before + 1
    gate = tr.get_gate_radius_px()
    assert 40.0 <= gate <= 320.0


def test_detector_gate_rejects_far_clutter():
    import cv2
    from fsoc_tracker.pipeline.detection.detector import BeaconDetector
    cfg = load_config()
    det = BeaconDetector(cfg)
    img = np.zeros((480, 640), dtype=np.uint8)
    cv2.circle(img, (100, 100), 6, 255, -1)  # far bright clutter
    cv2.circle(img, (320, 240), 6, 230, -1)  # near prediction
    d = det.detect(img, predicted_pos=(320.0, 240.0), gate_radius_px=40.0)
    assert d.valid and abs(d.centroid_px[0] - 320) < 20


def test_metrics_records_search_cases():
    m = MetricsCollector()
    m.start_run()
    est = _est(TrackingState.SEARCHING)
    m.update(0, 0.0, False, est, None, 1.0, 30.0, 0, 0, search_case="EXPAND")
    m.update(1, 1 / 30, False, est, None, 1.0, 30.0, 0, 0, search_case="TILE")
    s = m.summary()
    assert s["search_case_counts"] == {"EXPAND": 1, "TILE": 1}


def test_ekf_clamps_divergence_and_caps_covariance():
    from fsoc_tracker.pipeline.estimation.ekf import SimpleEKF
    cfg = load_config()
    ekf = SimpleEKF(cfg)
    ekf.x = __import__("numpy").array([50.0, -40.0, 100.0, -100.0, 500.0, -500.0])
    ekf.predict(dt=1.0)
    assert all(abs(v) <= lim for v, lim in
               zip(ekf.x, (12.0, 12.0, 15.0, 15.0, 60.0, 60.0)))
    import numpy as np
    assert float(np.diag(ekf.P).max()) <= 400.0
    # jitter-aware R: same innovation is less surprising with jitter on
    cfg_j = load_config()
    cfg_j["camera"]["jitter_px"] = 20.0
    a = SimpleEKF(cfg)
    b = SimpleEKF(cfg_j)
    a.x[:] = 0.0
    b.x[:] = 0.0
    _, nis_clean = a.update((340.0, 250.0), confidence=0.9)
    _, nis_jit = b.update((340.0, 250.0), confidence=0.9)
    assert nis_jit < nis_clean


def test_state_machine_blink_tolerant_lock():
    from fsoc_tracker.pipeline.state.state_machine import TrackingStateMachine
    cfg = load_config()
    sm = TrackingStateMachine(cfg)
    # 5 Hz blink at 30 fps: 3 strong on, 3 off — never 5 consecutive
    for i in range(30):
        strong = (i % 6) < 3
        sm.update(bool(strong), 0.9 if strong else 0.0)
        if sm.state == TrackingState.LOCKED:
            break
    assert sm.state == TrackingState.LOCKED
    # genuine 30-frame outage must NOT lock
    sm.reset()
    for _ in range(30):
        sm.update(False, 0.0)
    assert sm.state != TrackingState.LOCKED


def test_camera_at_limit_helper():
    from fsoc_tracker.camera.optics.virtual_camera import VirtualCamera
    cam = VirtualCamera(world_size=(2000, 2000), resolution=(640, 480),
                        fov_deg=(4.0, 3.0))
    cam.pan = -4.25
    cam.tilt = 4.25
    cam._update_center()
    assert cam.is_at_limit(-1.0, 0.0) is True   # pushing further out
    assert cam.is_at_limit(1.0, 0.0) is False   # driving back in
    cam.pan = 0.0
    cam.tilt = 0.0
    cam._update_center()
    assert cam.is_at_limit(-5.0, 5.0) is False  # centred: no limit


def test_uncued_fast_crossing_acquires():
    """End-to-end without Qt: fast target crossing the FOV uncued must lock."""
    from fsoc_tracker.config.loader import load_config as _load
    from fsoc_tracker.input.synthetic_source import SyntheticSource
    from fsoc_tracker.pipeline import BeaconDetector, Tracker
    from fsoc_tracker.camera import CameraController
    cfg = _load()
    cfg["target"]["initial_mode"] = "user-defined"
    cfg["target"]["initial_pos"] = [200, 1000]
    cfg["target"]["trajectory"] = "straight"
    cfg["target"]["speed_px_per_frame"] = 8.0
    cfg["target"]["blink_rate_hz"] = 0.0
    cfg["target"]["visibility_schedule"] = None
    src = SyntheticSource(cfg, seed=7)
    det = BeaconDetector(cfg)
    trk = Tracker(cfg)
    ctl = CameraController(cfg)
    src.reset()
    trk.reset()
    ctl.reset()
    latched = False
    reached = False
    for i in range(300):
        frame, gt = src.read()
        pred = trk.get_predicted_pixel()
        try:
            _m = int(trk.get_context().get("missed", 0))
        except Exception:
            _m = 0
        gate = trk.get_gate_radius_px() if (latched and _m <= 30) else None
        try:
            d = det.detect(frame.image, predicted_pos=pred, gate_radius_px=gate)
        except TypeError:
            d = det.detect(frame.image, predicted_pos=pred)
        e = trk.step(d, frame, hold=False)
        if getattr(e.tracking_state, "value", "") == "LOCKED":
            latched = True
            reached = True
            break
        tctx = trk.get_context()
        try:
            iv = src.camera.world_to_image(gt.world_pos) is not None if gt is not None else None
        except Exception:
            iv = None
        cctx = {"missed": tctx["missed"], "cand_frames": tctx["cand_frames"],
                "locked_frames": tctx["locked_frames"], "det_valid": d.valid,
                "det_conf": float(d.confidence or 0.0), "in_fov": iv,
                "latched": latched, "scheduled_hold": False}
        cmd = ctl.step(e, dt=1 / 30, ctx=cctx)
        src.apply_camera_command(cmd.pan_rate, cmd.tilt_rate, 1 / 30)
    assert reached, "uncued fast crossing never reached TRACKING"
