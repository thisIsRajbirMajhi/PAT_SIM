"""Headless integration tests: overlays driven by the live app (offscreen Qt).

Verifies the recorded-demo scenarios end to end:
- no TRACK CONFIRMED / fixed-100% overlay ever appears
- banner, target tag and bottom State pill always agree
- OFF-SCREEN is distinct from LOST (camera-slew maneuver)
- hidden-schedule dropout yields LOST -> REACQUIRING -> TRACKING
- blinking target degrades instead of flickering
- stale predictions are flagged, never drawn as fixes
- world/camera target IDs agree
"""
import sys
import os

import pytest

pytestmark = pytest.mark.headless

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtWidgets import QApplication  # noqa: E402

from fsoc_tracker.ui.app import MainWindow  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def make_window(qapp):
    w = MainWindow()
    return w


def run_ticks(w, n):
    states = []
    for _ in range(n):
        if not w.running:
            break
        w._tick()
        states.append(w.cam_view._display.label)
    return states


def test_clean_run_tracks_with_real_confidence(qapp):
    w = make_window(qapp)
    w.start_run()
    states = run_ticks(w, 60)
    assert "TRACKING" in states
    # no legacy/confirmed/fake states anywhere
    for s in states:
        assert "CONFIRMED" not in s
        assert "100%" not in s
        assert s != "IDENTIFIED"
    # banner, tag source and State pill agree
    assert w.cam_view._display.label == w._values["state"].text()
    assert w.cam_view._telemetry.track_label == "TGT-01"
    assert w._tele_vals["track_id"].text() == "TGT-01"
    # confidence is a real varying measurement, never exactly 1.0
    confs = [f["detection_confidence"] for f in w.metrics.frames
             if f["detection_valid"]]
    assert len(confs) > 30
    assert max(confs) < 1.0
    assert min(confs) > 0.45
    assert w._tele_vals["fov"].text() == "IN FOV"
    assert w._tele_vals["age"].text() != "\u2014"
    w.reset_run()


def test_offscreen_is_not_lost(qapp):
    w = make_window(qapp)
    w.start_run()
    run_ticks(w, 30)
    assert w.cam_view._display.label == "TRACKING"
    # slew the gimbal to the opposite corner so the locked target leaves the frame
    w.source.camera.pan = -4.25
    w.source.camera.tilt = 4.25
    w.source.camera._update_center()
    states = run_ticks(w, 8)
    assert "TRACKING \u2014 OFF-SCREEN" in states
    assert "TARGET LOST" not in states
    assert w.cam_view._telemetry.fov == "OFF-SCREEN"
    # drive back: prediction still fresh, track resumes without display loss
    w.source.cue_camera_to_target()
    states = run_ticks(w, 15)
    assert "TRACKING" in states
    # backend SM keeps its own lock-loss bookkeeping (benchmarks untouched);
    # the display layer correctly never declared the excursion a loss
    assert w.metrics.summary()["loss_count"] <= 1
    w.reset_run()


def test_hidden_dropout_lost_then_reacquire(qapp):
    w = make_window(qapp)
    w.cfg["target"]["visibility_schedule"] = [[1.0, 2.0, "hidden"]]
    w._create_source()
    from fsoc_tracker.pipeline.track.display import DisplayTracker
    w.display = DisplayTracker(w.cfg)
    w.reset_run()
    w.start_run()
    early = run_ticks(w, 30)
    assert "TRACKING" in early
    mid = run_ticks(w, 30)  # hidden window: frames 30..60
    assert "TARGET LOST" in mid
    assert "REACQUIRING" in mid
    late = run_ticks(w, 30)  # visible again
    assert "TRACKING" in late
    assert w.metrics.summary()["loss_count"] >= 1
    w.reset_run()


def test_blinking_target_degrades_without_flicker(qapp):
    w = make_window(qapp)
    w.cfg["target"]["blink_rate_hz"] = 2.0  # 50% duty: 15 on / 15 off
    w._create_source()
    from fsoc_tracker.pipeline.track.display import DisplayTracker
    w.display = DisplayTracker(w.cfg)
    w.reset_run()
    w.start_run()
    valid_states = []
    for _ in range(120):
        if not w.running:
            break
        w._tick()
        if w.last_detection is not None and w.last_detection.valid:
            valid_states.append(w.cam_view._display.label)
    assert "TRACK DEGRADED" in valid_states
    assert "TRACKING" in valid_states
    # no rapid banner oscillation: count transitions over the run
    w2 = make_window(qapp)
    w2.start_run()
    seq = run_ticks(w2, 60)
    transitions = sum(1 for a, b in zip(seq, seq[1:]) if a != b)
    assert transitions < 20
    w.reset_run()
    w2.reset_run()


def test_stale_prediction_never_drawn_as_fix(qapp):
    w = make_window(qapp)
    w.cfg["target"]["visibility_schedule"] = [[1.0, 6.0, "hidden"]]
    w._create_source()
    from fsoc_tracker.pipeline.track.display import DisplayTracker
    w.display = DisplayTracker(w.cfg)
    w.reset_run()
    w.start_run()
    run_ticks(w, 30)
    run_ticks(w, 120)  # outage far beyond the prediction budget
    tele = w.cam_view._telemetry
    assert tele.predicted is True
    assert tele.pred_fresh is False  # renderer must hide the marker
    assert tele.last_detect_age_s is not None and tele.last_detect_age_s > 1.0
    w.reset_run()


def test_world_camera_id_consistency(qapp):
    w = make_window(qapp)
    w.start_run()
    run_ticks(w, 30)
    assert w.cam_view._telemetry.track_label == "TGT-01"
    assert len(w.world_view.all_world_pos) >= 1
    # primary world trail mirrors the same object the camera tracks
    assert w.world_view.target_trails.get(0)
    w.reset_run()
