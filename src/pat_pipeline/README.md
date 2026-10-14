# pat_pipeline — headless-independent search-to-track pipeline

Canonical home of the PAT sense-decide-act chain, extracted from
`fsoc_tracker` so it can be developed, tested, and reused without any GUI.

## Purpose and architecture

`pat_pipeline` owns the full searching-to-tracking loop over a frame stream:

```text
frame -> BeaconDetector -> Tracker (IMM + state machine)
      -> CameraController -> ControlCommand  (host applies it)
```

| Subpackage | Contents |
|---|---|
| `detection/` | `BeaconDetector` — adaptive threshold + connected components + scoring + prediction gating |
| `estimation/` | `SimpleEKF` (6-state angle filter), `IMM` (CV/CA/MN fusion) |
| `state/` | `TrackingStateMachine` (SEARCHING→CANDIDATE→ACQUIRING→LOCKED, TEMP_LOST/REACQUIRING/FAILED) + `search_policy` (search-vs-track spec, case classifier) |
| `track/` | `Tracker` (predict/update/state → `Estimate`), `DisplayTracker`/`DisplayStatus` (GUI-free status truth) |
| `orchestration/` | `SearchTrackPipeline` — the shared per-frame orchestrator |
| `camera/` | `VirtualCamera` + `geometry`, `PIDController` + `CameraController` |
| `config.py` | defaults accessors (values owned by `pat_common.config.defaults`) |
| `factory.py` | `make_detector/make_tracker/make_controller/make_camera/make_pipeline` |

Legacy `fsoc_tracker.pipeline.*` and `fsoc_tracker.camera.*` modules remain as
thin re-exports resolving to these canonical objects (class identity holds:
`fsoc_tracker.pipeline.Tracker is pat_pipeline.Tracker`).

## Public API

```python
from pat_pipeline import (
    BeaconDetector,
    Tracker,
    CameraController,
    VirtualCamera,
    DisplayTracker,
    DisplayStatus,
    SearchTrackPipeline,
    make_pipeline,
)
```

## Lifecycle

```python
pipe = make_pipeline(cfg)          # exactly one detector + tracker + controller
pipe.attach_controller(my_gimbal)  # optional: inject your own controller
pipe.reset()                       # start of run: clears filter, SM, latch, command hold
pipe.update_config(cfg)            # propagates to detector / tracker / controller
```

`make_pipeline(cfg)` creates one of each component. Do not construct a second
detector/tracker/controller for the same run — reuse the pipeline's objects
(`pipe.detector`, `pipe.tracker`, `pipe.controller`).

## Per-frame contract

```python
detection, estimate, command = pipe.step_frame(
    frame, dt=None, in_fov=None, at_limit=False, ego_rate=0.0)
```

Inputs:

- `frame`: a `Frame` (uses `.image` + `.frame_id`) or a raw image array
  (falls back to the internal frame counter for schedule lookups).
- `in_fov`: `True`/`False` from host geometry, or `None` when unknown
  (e.g. video input — the host may fill it from `detection.valid` after).
- `at_limit`: host world-edge flag (default `False`).
- `ego_rate`: scalar or `(pan, tilt)` gimbal rate in deg/s for filter
  ego-compensation and the search classifier.
- Ground truth is never an input. The pipeline decides from pixels alone.

Order inside the tick (mirrors the former `MainWindow._tick`/`headless` loop):

1. tracker prediction → 2. gated detection (no gate while cold/stale) →
3. estimator update → 4. state transition (stays truthful through loss) →
5. controller ctx (`missed`, `cand/locked_frames`, `det_valid/conf`,
   `in_fov`, decayed `latched`, `scheduled_hold` from the blink/hidden
   schedule, `saturated`, `at_limit`, scalar `ego_rate`) →
6. control command when due at `update_interval_hz`, otherwise the held
   previous command. Returns `(detection, estimate, command|None)`
   (`command` is `None` only when no controller is attached).

`pipe.searching()` reports whether the tracker state is a search state.

## Host-applied commands

The pipeline computes commands; the host applies them with its own
camera/actuator adapter:

```python
if is_ptz:
    source.apply_camera_command(cmd.pan_rate, cmd.tilt_rate, dt_ctrl)
```

Sensor acquisition, world advancement, metrics/logging, and rendering stay
in the host (`headless.py`, `fsoc_tracker/ui/`).

## Shared core (no copy, no GUI/simulator)

- `pat_common.types` / `pat_common.enums` — one authoritative definition of
  `Frame`, `Detection`, `Estimate`, `ControlCommand`, `TrackingState`, …
- `pat_common.config` (defaults, sections, loader, validation) — config
  source of truth.
- `pat_common.visibility` — blink/hidden schedule helpers.
- `pat_common.kinds` — trajectory / platform type vocabularies.

Legacy `fsoc_tracker.common.*`, `fsoc_tracker.config.*`, and
`fsoc_tracker.target.dynamics.visibility` paths re-export these exact
objects. Importing `pat_pipeline` loads zero `fsoc_tracker` modules
(verified) and no Qt.

## Testing without a GUI

```powershell
.\.venv\Scripts\python.exe -m pytest -q            # full suite
python headless.py --scenario X1-baseline --seed 42 # headless end-to-end
```

`pat_pipeline` imports with `PyQt5`/`pyqtgraph` import-blocked (verified by
`tests/test_pat_pipeline_gui_isolation.py`). Install options:

```powershell
pip install -e .        # pipeline + headless (no Qt)
pip install -e ".[gui]" # full application with GUI
```

## Known limitations / future separation

- `pat_pipeline` + `pat_common` ship inside this repo's `src/` layout; a
  standalone distribution (own install metadata) is future work.
- `acquisition_time_s`/`reacquisition` metrics in the host layer use
  wall-clock time and vary run to run; deterministic frame-level outputs
  (detections, estimates, commands, states) are the equivalence signal.
