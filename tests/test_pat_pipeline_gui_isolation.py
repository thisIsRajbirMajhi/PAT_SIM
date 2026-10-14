"""Package isolation + compatibility tests for pat_pipeline (Prompt.md S9).

- Clean-process public imports succeed.
- Every pipeline module imports with Qt/GUI import-blocked.
- Shared types/enums keep one identity; legacy paths resolve to canonical.
- init / reset / update_config lifecycle works; no circular imports.
"""
import subprocess
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))


def _run_clean(code):
    return subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        timeout=120,
    )


def test_public_imports_in_clean_process():
    r = _run_clean(
        "import sys; sys.path.insert(0, 'src');"
        "from pat_pipeline import (BeaconDetector, Tracker, CameraController,"
        " VirtualCamera, DisplayTracker, DisplayStatus, SearchTrackPipeline,"
        " make_pipeline); print('ok')"
    )
    assert r.returncode == 0, r.stderr
    assert "ok" in r.stdout


def test_modules_import_with_gui_blocked():
    r = _run_clean(
        "import sys; sys.path.insert(0, 'src')\n"
        "class B:\n"
        " def find_module(self, n, p=None):\n"
        "  return self if n.split('.')[0] in ('PyQt5', 'pyqtgraph') else None\n"
        " def load_module(self, n):\n"
        "  raise ImportError('blocked:' + n)\n"
        "sys.meta_path.insert(0, B());"
        "import pat_pipeline.detection.detector, pat_pipeline.estimation.ekf,"
        " pat_pipeline.estimation.imm, pat_pipeline.state.state_machine,"
        " pat_pipeline.state.search_policy, pat_pipeline.track.tracker,"
        " pat_pipeline.track.display, pat_pipeline.orchestration.pat_loop,"
        " pat_pipeline.camera.optics.geometry,"
        " pat_pipeline.camera.optics.virtual_camera,"
        " pat_pipeline.camera.control.pid,"
        " pat_pipeline.camera.control.camera_controller,"
        " pat_pipeline.camera.factory, pat_pipeline.factory,"
        " pat_pipeline.config;"
        "print('no-gui-imports-ok')"
    )
    assert r.returncode == 0, r.stderr
    assert "no-gui-imports-ok" in r.stdout
    assert "blocked:" not in r.stderr


def test_no_gui_modules_loaded_by_pipeline():
    # pytest-qt loads PyQt5 into this process, so verify in a clean one.
    r = _run_clean(
        "import sys; sys.path.insert(0, 'src');"
        "import pat_pipeline;"
        "leaked = [m for m in sys.modules if m.split('.')[0] in"
        " ('PyQt5', 'pyqtgraph') or m.startswith('fsoc_tracker.ui')];"
        "print('leaked:', leaked); assert not leaked, leaked; print('clean')"
    )
    assert r.returncode == 0, r.stderr
    assert "clean" in r.stdout


def test_shared_types_and_enums_identity():
    from fsoc_tracker.common.data import Detection as D1
    from fsoc_tracker.common.types import Detection as D2
    from fsoc_tracker.common.enums import TrackingState as T1
    from fsoc_tracker.common.enums.tracking import TrackingState as T2

    assert D1 is D2
    assert T1 is T2


def test_legacy_imports_resolve_to_canonical():
    import pat_pipeline as new
    import fsoc_tracker.pipeline as old_pipe
    import fsoc_tracker.camera as old_cam
    from fsoc_tracker.pipeline.track.display import DisplayTracker as OldDisplay

    assert old_pipe.BeaconDetector is new.BeaconDetector
    assert old_pipe.Tracker is new.Tracker
    assert old_pipe.SimpleEKF is new.SimpleEKF
    assert old_pipe.IMM is new.IMM
    assert old_pipe.TrackingStateMachine is new.TrackingStateMachine
    assert old_pipe.SearchTrackPipeline is new.SearchTrackPipeline
    assert old_cam.CameraController is new.CameraController
    assert old_cam.VirtualCamera is new.VirtualCamera
    assert old_cam.PIDController is new.PIDController
    assert OldDisplay is new.DisplayTracker


def test_init_reset_update_config_lifecycle():
    from fsoc_tracker.config.loader import load_config
    from pat_pipeline import make_pipeline

    cfg = load_config()
    pipe = make_pipeline(cfg)
    assert pipe.detector is not None and pipe.tracker is not None
    assert pipe.controller is not None
    pipe._latched = True
    pipe._frame_id = 42
    pipe.reset()
    assert pipe._latched is False
    assert pipe._frame_id == 0
    assert pipe._last_command is None
    cfg2 = load_config()
    cfg2["tracker"]["meas_noise"] = 6.0
    pipe.update_config(cfg2)
    assert pipe.cfg is cfg2
    assert pipe.controller is not None


def test_no_circular_imports_in_fresh_orders():
    orders = [
        "import pat_pipeline.camera.control.camera_controller",
        "import pat_pipeline.orchestration.pat_loop",
        "import pat_pipeline.track.tracker",
        "import fsoc_tracker.pipeline",
        "import fsoc_tracker.camera",
    ]
    for stmt in orders:
        r = _run_clean(f"import sys; sys.path.insert(0, 'src');{stmt}; print('ok')")
        assert r.returncode == 0, f"{stmt}: {r.stderr}"
