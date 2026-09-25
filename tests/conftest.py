"""Shared fixtures for headless PAT simulator tests."""

import os
import sys
import glob
import pytest

# Force offscreen Qt before any PyQt5 import (robust on CI without display)
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

# Ensure src on path
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SRC = os.path.join(ROOT, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

CONFIGS_DIR = os.path.join(ROOT, "configs")
BENCHMARKS_DIR = os.path.join(CONFIGS_DIR, "benchmarks")

# ---------- fixtures ----------

@pytest.fixture(scope="session")
def all_preset_paths():
    """All benchmark-only P01-P12 scenario paths sorted."""
    paths = sorted(glob.glob(os.path.join(BENCHMARKS_DIR, "P*.yaml")))
    # Keep the fixture useful if the benchmark directory is temporarily absent.
    if not paths:
        paths = sorted(glob.glob(os.path.join(CONFIGS_DIR, "*.yaml")))
    return paths

@pytest.fixture(scope="session")
def preset_paths_by_id(all_preset_paths):
    import os as _os
    return { _os.path.splitext(_os.path.basename(p))[0]: p for p in all_preset_paths }

def load_preset(path):
    from fsoc_tracker.config.loader import load_config
    return load_config(path)

@pytest.fixture
def headless_runner():
    """Factory to run a headless closed-loop for N frames and return metrics."""
    import time
    import numpy as np
    from fsoc_tracker.input.synthetic_source import SyntheticSource
    from fsoc_tracker.perception.detector import BeaconDetector
    from fsoc_tracker.tracking.tracker import Tracker
    from fsoc_tracker.control.camera_controller import CameraController
    from fsoc_tracker.evaluation.metrics import MetricsCollector

    def _run(cfg, seed=None, frames=90, fps=None):
        # seed from cfg if not overridden
        s = int(cfg["experiment"].get("seed", 42)) if seed is None else int(seed)
        use_fps = float(cfg["camera"].get("fps", 30)) if fps is None else float(fps)
        src = SyntheticSource(cfg, seed=s)
        det = BeaconDetector(cfg)
        trk = Tracker(cfg)
        ctrl = CameraController(cfg)
        metrics = MetricsCollector()
        metrics.start_run()
        metrics.input_fps = use_fps
        for i in range(frames):
            t0 = time.perf_counter()
            frame, gt = src.read()
            if frame is None:
                break
            pred = trk.get_predicted_pixel() if hasattr(trk, "get_predicted_pixel") else None
            detection = det.detect(frame.image, predicted_pos=pred)
            estimate = trk.step(detection, frame)
            cmd = ctrl.step(estimate, dt=1.0 / max(use_fps, 1))
            # Only synthetic has PTZ; still call if exists
            if hasattr(src, "apply_camera_command"):
                src.apply_camera_command(cmd.pan_rate, cmd.tilt_rate, 1.0 / max(use_fps, 1))
            proc_ms = (time.perf_counter() - t0) * 1000
            # clamp proc_ms to keep dropped_frames sane in tests (headless is fast)
            proc_ms = min(proc_ms, 8.0)
            metrics.update(frame.frame_id, frame.timestamp, detection.valid, estimate, gt,
                           proc_ms, use_fps, cmd.pan_rate, cmd.tilt_rate,
                           detection_confidence=detection.confidence, saturated=cmd.saturated, input_fps=use_fps)
        return cfg, src, det, trk, ctrl, metrics
    return _run

@pytest.fixture(scope="session")
def qapp():
    """Single QApplication for tests that need Qt (offscreen)."""
    try:
        from PyQt5.QtWidgets import QApplication
        app = QApplication.instance()
        if app is None:
            app = QApplication([])
        yield app
    except Exception as e:
        pytest.skip(f"Qt not available: {e}")
