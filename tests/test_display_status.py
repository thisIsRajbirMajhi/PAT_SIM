"""Headless tests for the display state machine (no Qt required).

Covers the scenario list: SCANNING, TARGET DETECTED, VERIFYING, ACQUIRING,
TRACKING, OFF-SCREEN, DEGRADED, LOST, REACQUIRING, recovery, give-up, plus
hysteresis, telemetry, and the no-fake-confidence detector mapping.
"""
import sys
import os

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from fsoc_tracker.pipeline.track.display import (
    DisplayStatus, DisplayTracker, STATUS_META,
)


def tick(dt, n=1, **kw):
    out = None
    for _ in range(n):
        dt["fi"] += 1
        dt["ts"] += 1.0 / 30.0
        out = dt["trk"].update(
            dt["fi"], dt["ts"], kw.get("valid", False), kw.get("conf", 0.0),
            kw.get("sm", "SEARCHING"), kw.get("cand", 0), kw.get("locked", 0),
            kw.get("nis", 0.0), kw.get("fov", None),
            est_pos=kw.get("est", None))
    return out


def fresh():
    return {"trk": DisplayTracker({}), "fi": -1, "ts": 0.0}


def run_init(d):
    # pass INITIALIZING window (5 frames)
    tick(d, 5, valid=False, sm="SEARCHING")


def test_01_no_target_scanning():
    d = fresh()
    run_init(d)
    st, tele = tick(d, 10, valid=False, sm="SEARCHING")
    assert st.status == DisplayStatus.SCANNING
    assert st.show_no_target is True
    assert tele.track_label == "\u2014"
    assert tele.det_conf is None
    assert tele.last_detect_age_s is None


def test_02_new_detection_target_detected():
    d = fresh()
    run_init(d)
    tick(d, 3, valid=False, sm="SEARCHING")
    st, _ = tick(d, 1, valid=True, conf=0.8, sm="CANDIDATE", cand=1, locked=1,
                 nis=0.5, fov=True)
    assert st.status == DisplayStatus.TARGET_DETECTED


def test_03_validation_verifying():
    d = fresh()
    run_init(d)
    st, _ = tick(d, 1, valid=True, conf=0.8, sm="CANDIDATE", cand=1, locked=1,
                 nis=0.5, fov=True)
    assert st.status == DisplayStatus.TARGET_DETECTED
    st, _ = tick(d, 1, valid=True, conf=0.8, sm="CANDIDATE", cand=2, locked=2,
                 nis=0.5, fov=True)
    assert st.status == DisplayStatus.VERIFYING


def test_04_acquiring_track():
    d = fresh()
    run_init(d)
    tick(d, 1, valid=True, conf=0.8, sm="CANDIDATE", cand=1, locked=1, nis=0.5, fov=True)
    tick(d, 1, valid=True, conf=0.8, sm="CANDIDATE", cand=2, locked=2, nis=0.5, fov=True)
    st, _ = tick(d, 1, valid=True, conf=0.85, sm="ACQUIRING", cand=3, locked=3,
                 nis=0.5, fov=True)
    assert st.status == DisplayStatus.ACQUIRING


def test_05_stable_tracking_and_telemetry():
    d = fresh()
    run_init(d)
    tick(d, 1, valid=True, conf=0.8, sm="CANDIDATE", cand=1, locked=1, nis=0.5, fov=True)
    tick(d, 1, valid=True, conf=0.8, sm="CANDIDATE", cand=2, locked=2, nis=0.5, fov=True)
    tick(d, 2, valid=True, conf=0.85, sm="ACQUIRING", cand=4, locked=4, nis=0.5, fov=True)
    st, tele = tick(d, 3, valid=True, conf=0.9, sm="LOCKED", cand=8, locked=8,
                    nis=0.3, fov=True)
    assert st.status == DisplayStatus.TRACKING
    assert tele.track_label == "TGT-01"
    assert tele.det_conf == pytest.approx(0.9)
    assert tele.fov == "IN FOV"
    assert tele.track_age_s is not None and tele.track_age_s >= 0
    assert tele.last_detect_age_s == pytest.approx(0.0)


def test_06_offscreen_not_lost():
    d = fresh()
    run_init(d)
    tick(d, 1, valid=True, conf=0.8, sm="CANDIDATE", cand=1, locked=1, nis=0.5, fov=True)
    tick(d, 5, valid=True, conf=0.9, sm="LOCKED", cand=8, locked=8, nis=0.3, fov=True)
    # target leaves the frame: invalid + geometrically outside, prediction fresh
    st, tele = tick(d, 1, valid=False, sm="LOCKED", cand=8, locked=8, nis=0.0,
                    fov=False, est=(10.0, 10.0))
    assert st.status == DisplayStatus.TRACKING  # coast (1-frame gap)
    st, tele = tick(d, 1, valid=False, sm="TEMP_LOST", cand=7, locked=7, nis=0.0,
                    fov=False, est=(10.0, 10.0))
    assert st.status == DisplayStatus.OFF_SCREEN
    assert st.status != DisplayStatus.LOST
    assert tele.fov == "OFF-SCREEN"
    assert tele.predicted is True and tele.pred_fresh is True
    # still off-screen several frames later: holds OFF-SCREEN, not LOST
    st, _ = tick(d, 5, valid=False, sm="REACQUIRING", cand=0, locked=0, nis=0.0,
                 fov=False, est=(10.0, 10.0))
    assert st.status == DisplayStatus.OFF_SCREEN


def test_07_degraded_and_recovery():
    d = fresh()
    run_init(d)
    tick(d, 1, valid=True, conf=0.8, sm="CANDIDATE", cand=1, locked=1, nis=0.5, fov=True)
    tick(d, 6, valid=True, conf=0.9, sm="LOCKED", cand=9, locked=9, nis=0.3, fov=True)
    st, _ = tick(d, 4, valid=True, conf=0.85, sm="LOCKED", cand=13, locked=13,
                 nis=8.0, fov=True)
    assert st.status == DisplayStatus.TRACKING  # needs 5 sustained
    st, _ = tick(d, 1, valid=True, conf=0.85, sm="LOCKED", cand=14, locked=14,
                 nis=8.0, fov=True)
    assert st.status == DisplayStatus.DEGRADED
    # recovery needs 10 consecutive clean frames
    st, _ = tick(d, 9, valid=True, conf=0.9, sm="LOCKED", cand=23, locked=23,
                 nis=0.2, fov=True)
    assert st.status == DisplayStatus.DEGRADED
    st, _ = tick(d, 1, valid=True, conf=0.9, sm="LOCKED", cand=24, locked=24,
                 nis=0.2, fov=True)
    assert st.status == DisplayStatus.TRACKING


def test_08_tracker_fails_target_lost():
    d = fresh()
    run_init(d)
    tick(d, 1, valid=True, conf=0.8, sm="CANDIDATE", cand=1, locked=1, nis=0.5, fov=True)
    tick(d, 6, valid=True, conf=0.9, sm="LOCKED", cand=9, locked=9, nis=0.3, fov=True)
    # in-FOV dropout: coast, coast, then LOST (3-miss confirmation)
    st, _ = tick(d, 1, valid=False, sm="LOCKED", cand=9, locked=9, nis=0.0, fov=True)
    assert st.status == DisplayStatus.TRACKING
    st, _ = tick(d, 1, valid=False, sm="LOCKED", cand=8, locked=8, nis=0.0, fov=True)
    assert st.status == DisplayStatus.TRACKING
    st, _ = tick(d, 1, valid=False, sm="TEMP_LOST", cand=7, locked=7, nis=0.0, fov=True)
    assert st.status == DisplayStatus.LOST


def test_09_recovery_attempt_and_success():
    d = fresh()
    run_init(d)
    tick(d, 1, valid=True, conf=0.8, sm="CANDIDATE", cand=1, locked=1, nis=0.5, fov=True)
    tick(d, 6, valid=True, conf=0.9, sm="LOCKED", cand=9, locked=9, nis=0.3, fov=True)
    tick(d, 4, valid=False, sm="TEMP_LOST", cand=5, locked=5, nis=0.0, fov=True)
    st, _ = tick(d, 3, valid=False, sm="REACQUIRING", cand=2, locked=2, nis=0.0, fov=True)
    assert st.status == DisplayStatus.REACQUIRING
    # target reappears: fresh detection chain replays to TRACKING
    st, _ = tick(d, 1, valid=True, conf=0.8, sm="CANDIDATE", cand=1, locked=1,
                 nis=0.6, fov=True)
    assert st.status == DisplayStatus.TARGET_DETECTED
    st, _ = tick(d, 5, valid=True, conf=0.9, sm="LOCKED", cand=6, locked=6,
                 nis=0.3, fov=True)
    assert st.status == DisplayStatus.TRACKING


def test_10_failed_reacquisition_returns_to_scanning():
    d = fresh()
    run_init(d)
    tick(d, 1, valid=True, conf=0.8, sm="CANDIDATE", cand=1, locked=1, nis=0.5, fov=True)
    tick(d, 6, valid=True, conf=0.9, sm="LOCKED", cand=9, locked=9, nis=0.3, fov=True)
    tick(d, 4, valid=False, sm="TEMP_LOST", cand=5, locked=5, nis=0.0, fov=True)
    st, _ = tick(d, 10, valid=False, sm="REACQUIRING", cand=0, locked=0, nis=0.0,
                 fov=True)
    assert st.status == DisplayStatus.REACQUIRING
    st, _ = tick(d, 50, valid=False, sm="SEARCHING", cand=0, locked=0, nis=0.0,
                 fov=True)
    assert st.status == DisplayStatus.SCANNING


def test_11_offscreen_expiry_becomes_lost():
    d = fresh()
    run_init(d)
    tick(d, 1, valid=True, conf=0.8, sm="CANDIDATE", cand=1, locked=1, nis=0.5, fov=True)
    tick(d, 6, valid=True, conf=0.9, sm="LOCKED", cand=9, locked=9, nis=0.3, fov=True)
    st, _ = tick(d, 2, valid=False, sm="TEMP_LOST", cand=7, locked=7, nis=0.0,
                 fov=False, est=(5.0, 5.0))
    assert st.status == DisplayStatus.OFF_SCREEN
    st, tele = tick(d, 30, valid=False, sm="SEARCHING", cand=0, locked=0, nis=0.0,
                    fov=False, est=(5.0, 5.0))
    assert st.status == DisplayStatus.LOST
    assert tele.pred_fresh is False


def test_initializing_first_frames():
    d = fresh()
    st, _ = tick(d, 1, valid=True, conf=0.9, sm="LOCKED", cand=9, locked=9,
                 nis=0.2, fov=True)
    assert st.status == DisplayStatus.INITIALIZING


def test_status_meta_covers_all():
    assert set(STATUS_META) == set(DisplayStatus)
    for _key, (label, color, _role) in STATUS_META.items():
        assert label and color.startswith("#")


def test_detector_confidence_is_measurement():
    """Detector confidence must vary with blob quality, pass the SM gate on
    real beacons, and never saturate to exactly 1.0 on nominal frames."""
    import numpy as np
    from fsoc_tracker.config.loader import load_config
    from fsoc_tracker.input.synthetic_source import SyntheticSource
    from fsoc_tracker.pipeline import BeaconDetector
    cfg = load_config()
    src = SyntheticSource(cfg, seed=42)
    src.reset()
    src.cue_camera_to_target()  # same coarse cue the live app applies on START
    det = BeaconDetector(cfg)
    confs = []
    for _ in range(60):
        frame, _gt = src.read()
        d = det.detect(frame.image)
        if d.valid:
            confs.append(d.confidence)
    assert len(confs) > 20
    assert min(confs) > 0.45, f"gate margin violated: {min(confs)}"
    assert max(confs) < 1.0, f"saturated confidence: {max(confs)}"
    assert max(confs) - min(confs) > 0.02, "confidence has no dynamic range"
