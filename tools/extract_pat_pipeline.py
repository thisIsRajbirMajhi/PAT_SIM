#!/usr/bin/env python3
"""Extract PAT-SIM's canonical pipeline to src/pat_pipeline."""
from __future__ import annotations
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
DEST = SRC / "pat_pipeline"
MARKER = DEST / ".extraction_complete"

MODULES = {
    "fsoc_tracker/pipeline/detection/__init__.py": "detection/__init__.py",
    "fsoc_tracker/pipeline/detection/detector.py": "detection/detector.py",
    "fsoc_tracker/pipeline/estimation/__init__.py": "estimation/__init__.py",
    "fsoc_tracker/pipeline/estimation/ekf.py": "estimation/ekf.py",
    "fsoc_tracker/pipeline/estimation/imm.py": "estimation/imm.py",
    "fsoc_tracker/pipeline/state/__init__.py": "state/__init__.py",
    "fsoc_tracker/pipeline/state/state_machine.py": "state/state_machine.py",
    "fsoc_tracker/pipeline/state/search_policy.py": "state/search_policy.py",
    "fsoc_tracker/pipeline/track/__init__.py": "track/__init__.py",
    "fsoc_tracker/pipeline/track/tracker.py": "track/tracker.py",
    "fsoc_tracker/pipeline/track/display.py": "track/display.py",
    "fsoc_tracker/pipeline/orchestration/__init__.py": "orchestration/__init__.py",
    "fsoc_tracker/pipeline/orchestration/pat_loop.py": "orchestration/pat_loop.py",
    "fsoc_tracker/camera/optics/__init__.py": "camera/optics/__init__.py",
    "fsoc_tracker/camera/optics/geometry.py": "camera/optics/geometry.py",
    "fsoc_tracker/camera/optics/virtual_camera.py": "camera/optics/virtual_camera.py",
    "fsoc_tracker/camera/control/__init__.py": "camera/control/__init__.py",
    "fsoc_tracker/camera/control/camera_controller.py": "camera/control/camera_controller.py",
    "fsoc_tracker/camera/control/pid.py": "camera/control/pid.py",
}

def write_text(relative: str, content: str) -> None:
    path = SRC / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content.rstrip() + "\n", encoding="utf-8")

def canonicalize_imports(text: str) -> str:
    text = text.replace("from ...common.", "from fsoc_tracker.common.")
    text = text.replace("from ...target.", "from fsoc_tracker.target.")
    text = text.replace("from ...pipeline.state.", "from pat_pipeline.state.")
    return text

def shim(old_path: str, import_path: str, names: list[str] | None = None) -> None:
    if names:
        body = "\n".join(f"    {name}," for name in names)
        content = (
            '"""Compatibility exports; canonical implementation is in pat_pipeline."""\n'
            f"from {import_path} import (\n{body}\n)\n\n"
            f"__all__ = {names!r}"
        )
    else:
        content = (
            '"""Compatibility exports; canonical implementation is in pat_pipeline."""\n'
            f"from {import_path} import *"
        )
    write_text(old_path, content)

def main() -> None:
    if MARKER.exists():
        print("PAT pipeline extraction already applied.")
        return
    if DEST.exists():
        raise SystemExit(f"{DEST} exists without extraction marker; refusing to overwrite.")
    DEST.mkdir(parents=True)
    for rel in ("detection", "estimation", "state", "track", "orchestration",
                "camera", "camera/optics", "camera/control"):
        (DEST / rel).mkdir(parents=True, exist_ok=True)

    for source_rel, destination_rel in MODULES.items():
        source = SRC / source_rel
        if not source.is_file():
            raise SystemExit(f"Required source module missing: {source}")
        target = DEST / destination_rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        target.write_text(canonicalize_imports(target.read_text(encoding="utf-8")),
                          encoding="utf-8")

    write_text("pat_pipeline/config.py", '''"""Pipeline defaults shared with fsoc_tracker configuration."""
from fsoc_tracker.config.defaults import DEFAULT_CONFIG
DETECTOR_DEFAULTS = DEFAULT_CONFIG["detector"]
TRACKER_DEFAULTS = DEFAULT_CONFIG["tracker"]
CONTROLLER_DEFAULTS = DEFAULT_CONFIG["controller"]
def get_detector(cfg):
    return cfg.get("detector", {})
def get_tracker(cfg):
    return cfg.get("tracker", {})
__all__ = ["DETECTOR_DEFAULTS", "TRACKER_DEFAULTS", "CONTROLLER_DEFAULTS", "get_detector", "get_tracker"]
''')

    write_text("pat_pipeline/camera/__init__.py", '''"""GUI-independent camera optics and control."""
from .control import CameraController, PIDController
from .optics import (VirtualCamera, angle_to_pixel, deg_per_px, focal_px_rad,
                     pixel_to_angle, px_per_deg, viewport_bounds)
__all__ = ["VirtualCamera", "CameraController", "PIDController", "px_per_deg",
           "deg_per_px", "pixel_to_angle", "angle_to_pixel", "viewport_bounds",
           "focal_px_rad"]
''')

    write_text("pat_pipeline/factory.py", '''"""Factories for constructing the reusable PAT pipeline."""
from .camera import CameraController
from .detection import BeaconDetector
from .orchestration import SearchTrackPipeline
from .track import Tracker
def make_detector(cfg):
    return BeaconDetector(cfg)
def make_tracker(cfg):
    return Tracker(cfg)
def make_controller(cfg):
    return CameraController(cfg)
def make_pipeline(cfg, controller=None):
    """Create a pipeline with a controller unless one is explicitly injected."""
    return SearchTrackPipeline(cfg, controller=controller if controller is not None else make_controller(cfg))
__all__ = ["make_detector", "make_tracker", "make_controller", "make_pipeline"]
''')

    write_text("pat_pipeline/__init__.py", '''"""Reusable, GUI-independent searching-to-tracking pipeline."""
from .config import CONTROLLER_DEFAULTS, DETECTOR_DEFAULTS, TRACKER_DEFAULTS, get_detector, get_tracker
from .detection import BeaconDetector
from .estimation import IMM, SimpleEKF
from .state import (CONFIDENCE_THRESHOLD, REQUIRED_CANDIDATE_FRAMES, REQUIRED_LOCK_FRAMES,
                    SEARCH_ANGLE_STEP, SEARCH_RADIUS_MAX, SEARCH_RADIUS_STEP, SEARCH_RATE_SCALE,
                    SEARCH_STATES, TEMP_LOST_GAIN, TrackingStateMachine, describe_state,
                    is_search_state, is_track_state, track_gain)
from .track import DisplayStatus, DisplayState, TrackTelemetry, DisplayTracker, Tracker
from .orchestration import SearchTrackPipeline
from .camera import CameraController, PIDController, VirtualCamera
from .factory import make_controller, make_detector, make_pipeline, make_tracker
__all__ = [
    "BeaconDetector", "SimpleEKF", "IMM", "TrackingStateMachine", "Tracker",
    "DisplayStatus", "DisplayState", "TrackTelemetry", "DisplayTracker", "SearchTrackPipeline",
    "CameraController", "PIDController", "VirtualCamera", "SEARCH_STATES",
    "SEARCH_ANGLE_STEP", "SEARCH_RADIUS_STEP", "SEARCH_RADIUS_MAX", "SEARCH_RATE_SCALE",
    "TEMP_LOST_GAIN", "REQUIRED_CANDIDATE_FRAMES", "REQUIRED_LOCK_FRAMES",
    "CONFIDENCE_THRESHOLD", "is_search_state", "is_track_state", "track_gain",
    "describe_state", "DETECTOR_DEFAULTS", "TRACKER_DEFAULTS", "CONTROLLER_DEFAULTS",
    "get_detector", "get_tracker", "make_detector", "make_tracker", "make_controller",
    "make_pipeline",
]
''')

    # Propagate scheduled-hold explicitly into controller context.
    loop_path = DEST / "orchestration/pat_loop.py"
    loop = loop_path.read_text(encoding="utf-8")
    old_sig = "def _controller_ctx(self, detection, in_fov=None, at_limit=False, ego_rate=0.0) -> dict:"
    new_sig = "def _controller_ctx(self, detection, in_fov=None, at_limit=False, ego_rate=0.0, scheduled_hold=False) -> dict:"
    if old_sig not in loop or '"scheduled_hold": scheduled,' not in loop:
        raise SystemExit("Could not safely locate scheduled-hold context code in pat_loop.py")
    loop = loop.replace(old_sig, new_sig)
    loop = loop.replace('"scheduled_hold": scheduled,', '"scheduled_hold": bool(scheduled_hold),')
    loop = loop.replace(
        "self._controller_ctx(detection, in_fov=in_fov, at_limit=at_limit, ego_rate=ego_rate)",
        "self._controller_ctx(detection, in_fov=in_fov, at_limit=at_limit, ego_rate=ego_rate, scheduled_hold=scheduled)"
    )
    loop_path.write_text(loop, encoding="utf-8")

    shims = [
        ("fsoc_tracker/pipeline/detection/detector.py", "pat_pipeline.detection.detector", ["BeaconDetector"]),
        ("fsoc_tracker/pipeline/estimation/ekf.py", "pat_pipeline.estimation.ekf", ["SimpleEKF"]),
        ("fsoc_tracker/pipeline/estimation/imm.py", "pat_pipeline.estimation.imm", ["IMM"]),
        ("fsoc_tracker/pipeline/state/state_machine.py", "pat_pipeline.state.state_machine", ["TrackingStateMachine"]),
        ("fsoc_tracker/pipeline/state/search_policy.py", "pat_pipeline.state.search_policy", None),
        ("fsoc_tracker/pipeline/track/tracker.py", "pat_pipeline.track.tracker", ["Tracker"]),
        ("fsoc_tracker/pipeline/track/display.py", "pat_pipeline.track.display", None),
        ("fsoc_tracker/pipeline/orchestration/pat_loop.py", "pat_pipeline.orchestration.pat_loop", ["SearchTrackPipeline"]),
        ("fsoc_tracker/camera/optics/virtual_camera.py", "pat_pipeline.camera.optics.virtual_camera", ["VirtualCamera"]),
        ("fsoc_tracker/camera/optics/geometry.py", "pat_pipeline.camera.optics.geometry", None),
        ("fsoc_tracker/camera/control/camera_controller.py", "pat_pipeline.camera.control.camera_controller", ["CameraController"]),
        ("fsoc_tracker/camera/control/pid.py", "pat_pipeline.camera.control.pid", ["PIDController"]),
    ]
    for old_path, import_path, names in shims:
        shim(old_path, import_path, names)

    headless = ROOT / "headless.py"
    h = headless.read_text(encoding="utf-8")
    replacements = [
        ("from fsoc_tracker.pipeline import BeaconDetector, Tracker", "from pat_pipeline import BeaconDetector, Tracker"),
        ("from fsoc_tracker.camera import CameraController", "from pat_pipeline.camera import CameraController"),
        ("from fsoc_tracker.pipeline.track.display import DisplayTracker, DisplayStatus", "from pat_pipeline.track.display import DisplayTracker, DisplayStatus"),
    ]
    for old, new in replacements:
        if old not in h:
            raise SystemExit(f"Expected headless import not found: {old}")
        h = h.replace(old, new)
    headless.write_text(h, encoding="utf-8")

    ui_path = ROOT / "src/fsoc_tracker/ui/app.py"
    ui = ui_path.read_text(encoding="utf-8")
    ui_replacements = [
        ("from ..pipeline.track.display import DisplayTracker", "from pat_pipeline.track.display import DisplayTracker"),
        ("from ..pipeline import BeaconDetector, Tracker", "from pat_pipeline import BeaconDetector, Tracker"),
        ("from ..camera import CameraController", "from pat_pipeline.camera import CameraController"),
    ]
    for old, new in ui_replacements:
        if old not in ui:
            raise SystemExit(f"Expected GUI import not found: {old}")
        ui = ui.replace(old, new)
    ui_path.write_text(ui, encoding="utf-8")

    # Make desktop dependencies optional; existing GUI users can install .[gui].
    pyproject = ROOT / "pyproject.toml"
    p = pyproject.read_text(encoding="utf-8")
    old_deps = 'dependencies = ["numpy>=1.24", "opencv-python>=4.8", "PyQt5>=5.15", "pyqtgraph>=0.12", "PyYAML>=6.0", "pillow>=10.0"]'
    new_deps = 'dependencies = ["numpy>=1.24", "opencv-python>=4.8", "PyYAML>=6.0", "pillow>=10.0"]\n\n[project.optional-dependencies]\ngui = ["PyQt5>=5.15", "pyqtgraph>=0.12"]'
    if old_deps not in p:
        raise SystemExit("Unexpected pyproject dependency declaration; refusing to alter it.")
    pyproject.write_text(p.replace(old_deps, new_deps), encoding="utf-8")

    write_text("pat_pipeline/README.md", '''# PAT Pipeline

This package is the canonical GUI-independent implementation of PAT detection, estimation, search state, tracking, orchestration, virtual-camera optics, and camera control.

## Quick start

    from fsoc_tracker.config.loader import load_config
    from pat_pipeline import make_pipeline

    cfg = load_config()
    pipeline = make_pipeline(cfg)
    pipeline.reset()
    detection, estimate, command = pipeline.step_frame(frame)

The pipeline computes commands; input sources, camera actuation, ground-truth scoring, run logging, and rendering remain host responsibilities. The host can pass FOV, camera-limit, and ego-motion context to step_frame.

Shared types/enums, validated configuration, and scheduled visibility remain single-sourced in fsoc_tracker.common, fsoc_tracker.config, and fsoc_tracker.target.dynamics.visibility. Legacy fsoc_tracker.pipeline and fsoc_tracker.camera paths remain compatibility exports.

The package does not import the GUI. Install core dependencies with pip install .; install desktop UI extras with pip install '.[gui]'.

See tests/test_pat_pipeline_package.py and headless.py for test examples.
''')

    test_path = ROOT / "tests/test_pat_pipeline_package.py"
    test_path.write_text('''import subprocess
import sys
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

def test_core_import_does_not_load_gui():
    code = """
import sys, pat_pipeline
assert not any(n == 'PyQt5' or n.startswith('PyQt5.') for n in sys.modules)
assert not any(n == 'pyqtgraph' or n.startswith('pyqtgraph.') for n in sys.modules)
assert not any(n == 'fsoc_tracker.ui' or n.startswith('fsoc_tracker.ui.') for n in sys.modules)
"""
    subprocess.run([sys.executable, "-c", code], cwd=ROOT, check=True)

def test_legacy_imports_share_canonical_class_objects():
    from pat_pipeline.detection.detector import BeaconDetector as NewDetector
    from fsoc_tracker.pipeline.detection.detector import BeaconDetector as OldDetector
    from pat_pipeline.track.tracker import Tracker as NewTracker
    from fsoc_tracker.pipeline.track.tracker import Tracker as OldTracker
    from pat_pipeline.camera.control.camera_controller import CameraController as NewController
    from fsoc_tracker.camera.control.camera_controller import CameraController as OldController
    assert NewDetector is OldDetector
    assert NewTracker is OldTracker
    assert NewController is OldController

def test_scheduled_hold_reaches_controller_context():
    from fsoc_tracker.config.loader import load_config
    from pat_pipeline.orchestration import SearchTrackPipeline
    cfg = load_config()
    cfg["target"]["blink_rate_hz"] = 15.0
    class CaptureController:
        def __init__(self):
            self.ctx = None
        def reset(self):
            pass
        def update_config(self, cfg):
            pass
        def step(self, estimate, dt=None, ctx=None):
            self.ctx = ctx
            class Command:
                pan_rate = 0.0
                tilt_rate = 0.0
            return Command()
    controller = CaptureController()
    pipeline = SearchTrackPipeline(cfg, controller=controller)
    pipeline._frame_id = 1
    frame = np.zeros((int(cfg["camera"]["resolution"][1]), int(cfg["camera"]["resolution"][0])), dtype=np.uint8)
    pipeline.step_frame(frame)
    assert controller.ctx is not None
    assert controller.ctx["scheduled_hold"] is True
''', encoding="utf-8")

    MARKER.write_text("completed\n", encoding="utf-8")
    print(f"Extraction complete: {DEST}")

if __name__ == "__main__":
    main()
