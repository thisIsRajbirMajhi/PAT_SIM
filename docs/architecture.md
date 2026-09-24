# System Architecture — FSOC Virtual Camera Tracking PAT Simulator

> **Version:** 1.0.0 | **Date:** 2026-09-24 | **Stack:** Python 3.10+, PyQt5, OpenCV, NumPy, PyYAML, pyqtgraph

## 1. Purpose and Scope

This document describes the system architecture of the **FSOC Virtual Camera Tracking PAT Simulator** — a software-only coarse pointing, acquisition and tracking (PAT) simulator for mobile Free-Space Optical Communication (FSOC) terminals. The simulator controls a virtual pan–tilt camera to find, centre and follow a moving optical beacon under realistic disturbances.

The simulator supports two interchangeable input modes — SYNTHETIC virtual world and external benchmark VIDEO `.mp4` at 30 fps — through a single perception–tracking–control pipeline. Ground truth is evaluator-only and never leaks to detection or control.

Success is judged on two simultaneous criteria: engineering pass (acquisition ≤ 2 s, re-acquisition ≤ 1 s, RMSE ≤ 10 px, loss < 5 %, FPS ≥ 20) and competition/demo pass (explainable, real-time, reproducible).

---

## 2. High-Level Architecture

### 2.1 Data-Flow Overview

```
Experiment Configuration (YAML + Control Deck live overrides, seed)
        |
        v
Scenario / World Generator  -->  Target Motion Model (7 trajectories)
        |                                |
        v                                v
Platform Motion + Disturbances  -->  World State (2000x2000 base + beacons)
        |
        v
Virtual Pan-Tilt Camera / Video Adapter   (FrameSource abstraction)
        |
        v
Image Formation + Noise + Atmosphere + Jitter
        |
        v
Beacon Detector / Segmenter  (adaptive threshold -> candidates -> centroid)
        |
        v
Candidate Validation + Centroid Estimator
        |
        v
Tracker (IMM of EKFs + State Machine)  -->  Prediction & model probabilities
        |
        v
Error Computation  (image centre - estimated centroid, angular)
        |
        v
Pan-Tilt Controller (PID + feed-forward + saturation + anti-windup + search)
        |
        +--> Virtual camera update (pan/tilt rate-limited)
        +--> GUI overlays and live metrics
        +--> Performance logger -> outputs/runs/<timestamp>_<traj>_seedN/
```

Ground-truth `World -> GroundTruth` is evaluator-only and never provided to `Detector`, `Tracker` or `Controller`.

### 2.2 FrameSource Abstraction

Both SYNTHETIC and VIDEO inputs satisfy a single interface, so the downstream pipeline is identical:

```python
# src/fsoc_tracker/input/base.py
class FrameSource(Protocol):
    def read(self) -> Optional[Frame]: ...
    def reset(self, seed: int) -> None: ...
```

```
FrameSource
  +-- SyntheticSceneSource  -> World + VirtualCamera.extract_viewport + Noise/Atmosphere/Jitter -> Frame
  +-- VideoFileSource       -> cv2.VideoCapture decode -> resize/format -> Frame  (PTZ bypassed)
                |
                v
        Detector -> Tracker -> Metrics -> GUI/Logging   (identical)
```

In VIDEO mode the virtual PTZ renderer is bypassed; EKF-IMM still estimates motion and PID commands are displayed but not applied to a viewport.

---

## 3. Module Decomposition

| Layer | Package | Responsibility | Must Not Do |
|-------|---------|---------------|-------------|
| `config` | `src/fsoc_tracker/config/` | Validate parameters, presets, seeds (`schema.py`, `defaults.py`, `loader.py`) | Touch frames or tracking state |
| `common` | `src/fsoc_tracker/common/` | Shared data contracts `Frame`, `Detection`, `Estimate`, `ControlCommand`, `MetricsFrame` (`types.py`, `enums.py`, `constants.py`, `clock.py`, `random_state.py`) | Contain algorithm logic |
| `input` | `src/fsoc_tracker/input/` | `SyntheticSceneSource`, `VideoFileSource`, `FrameSource` interface | Detect/track |
| `simulation` | `src/fsoc_tracker/simulation/` | `World`, trajectories, platform motion, `VirtualCamera`, noise, atmosphere, `ground_truth.py` | Expose ground truth to tracker |
| `perception` | `src/fsoc_tracker/perception/` | `BeaconDetector` (threshold -> morphology -> CC -> scoring -> weighted centroid) | Control camera |
| `tracking` | `src/fsoc_tracker/tracking/` | `SimpleEKF`, `IMM`, `TrackingStateMachine`, `Tracker` facade | Update GUI widgets |
| `control` | `src/fsoc_tracker/control/` | `PIDController`, `CameraController` (feed-forward, saturation, anti-windup, spiral search) | Decide blob validity |
| `evaluation` | `src/fsoc_tracker/evaluation/` | `MetricsCollector`, `report.py`, `auto_logger.py`, timing/events | Change tracking decisions |
| `ui` | `src/fsoc_tracker/ui/` | `App`, `Viewport`, `ControlDeck`, `Dashboard`, `LiveDashboardWindow`, `theme.py` | Contain algorithmic business logic |
| `infrastructure` | `src/fsoc_tracker/infrastructure/` | Logging, profiling, storage, exception handling | Hide failures |

### 3.3 Spec Parameters Sr.1-15 and Disturbances — Enforced Ranges

| Sr. | Parameter | Key / File | Spec | Default | Allowed | Notes |
|-----|-----------|-----------|------|---------|---------|-------|
| 1 | World/screen size | `world.width/height` `world.py` | 2000x2000 min | 2000 | 2000-4000 | `background` 0-80 default 18 |
| 2 | Camera type | `camera.type` | Monochrome focal-plane | monochrome | monochrome/colour | BGR auto-gray |
| 3 | Resolution | `camera.resolution` | 640x480 | 640x480 | 320-1920 x 240-1080 | |
| 4 | FOV | `camera.fov_deg` | 4 deg x 3 deg | 4.0,3.0 | 1-12 deg each | `px_per_deg 220` |
| 5 | Update rate | `camera.fps` / `update_interval_hz` | >=30 Hz cam, >=20 Hz ctrl | 30 | 30-60 / 20-60 | dt=1/fps |
| 6 | Initial camera pos | `initial_position/pan/tilt` | Centre | centre 0,0 | centre/user-defined | |
| 7 | Target type | `target.type` | Beacon spot | beacon_spot | beacon_spot | |
| 8 | Target count | `target.count` | 1 mandatory | 1 | 1-5 | independent trajectories |
| 9 | Target shape | `target.shape` | Square default | square | square/circle/gaussian/cross/user-defined | |
| 10 | Target size | `target.size` | 5-20 px | 10 | 5-20 | |
| 11 | Initial target pos | `target.initial_pos/mode` | Random default | None random | None/[x,y] | seed |
| 12 | Trajectory | `target.trajectory` + speed/angle/radius | straight/circular/figure_eight/random + spiral/sinusoidal/user-defined | circular 2.8 | 0-20 speed, 50-800 radius | |
| 13 | Max pan speed | `camera.max_pan_speed` | 5 deg/s default 5-10 | 5.0 | 1-15 (spec 5-10) | |
| 14 | Max tilt speed | `camera.max_tilt_speed` | same | 5.0 | 1-15 | |
| 15 | Performance | acquistion <=2s reacq <=1s RMSE <=10 px loss <5% FPS >=20 | thresholds `constants.py` | — | — | all reported live |

Disturbances (all in `simulation/noise.py` + `platform_motion.py` + `world.py` environment): Gaussian 0-20 std, salt-pepper 0-0.15 prob, Poisson on/off, jitter +-20 px/frame, atmosphere haze/fog/rain/low_light strength 0-1, platform none/linear/circular/random/spiral/figure_8 speed 0-20 px/frame, gradient/stars/vignetting/brightness. See `docs/configuration.md` for per-key tables and `schema.py` asserts.

---

## 4. Folder Structure

```
PAT_SIM/
+-- README.md
+-- launch.py
+-- pyproject.toml
+-- requirements.txt
+-- .gitignore
+-- configs/
|   +-- default.yaml
|   +-- high_noise.yaml
+-- src/fsoc_tracker/
|   +-- __init__.py
|   +-- main.py                    # entry point — creates QApplication, MainWindow
|   +-- __main__.py
|   +-- version.py
|   +-- common/
|   |   +-- types.py               # Frame, GroundTruth, Detection, Estimate, ControlCommand, MetricsFrame
|   |   +-- enums.py               # TrackingState, InputMode, TrajectoryType, etc.
|   |   +-- constants.py           # thresholds: ACQ<=2s, REACQ<=1s, RMSE<=10px, loss<5%, FPS>=20
|   |   +-- clock.py
|   |   +-- random_state.py
|   +-- config/
|   |   +-- defaults.py            # DEFAULT_CONFIG dict
|   |   +-- schema.py              # validate_config() asserts spec ranges
|   |   +-- loader.py              # YAML load, deep-merge, override
|   +-- input/
|   |   +-- base.py                # FrameSource protocol
|   |   +-- synthetic_source.py    # World + VirtualCamera + noise pipeline
|   |   +-- video_source.py        # cv2.VideoCapture adapter @30 fps
|   +-- simulation/
|   |   +-- world.py               # World — base building, gradient/stars/vignetting, beacon rendering
|   |   +-- virtual_camera.py      # VirtualCamera — world<->image<->angle, px_per_deg, extract_viewport
|   |   +-- trajectories.py        # 7 trajectory classes + make_trajectory()
|   |   +-- platform_motion.py     # PlatformMotion — none/linear/circular/random/spiral/figure-8
|   |   +-- noise.py               # apply_gaussian / salt_pepper / poisson / jitter / atmosphere
|   |   +-- ground_truth.py        # evaluator-only projection
|   +-- perception/
|   |   +-- detector.py            # BeaconDetector
|   +-- tracking/
|   |   +-- ekf.py                 # SimpleEKF — 6-state EKF with tan projection + NIS gating
|   |   +-- imm.py                 # IMM — 3-model (CV/CA/MN) mixing + likelihood + fuse
|   |   +-- state_machine.py       # TrackingStateMachine — SEARCHING..FAILED
|   |   +-- tracker.py             # Tracker facade
|   +-- control/
|   |   +-- pid.py                 # PIDController
|   |   +-- camera_controller.py   # CameraController — PID+FF+saturation+spiral search
|   +-- evaluation/
|   |   +-- metrics.py             # MetricsCollector
|   |   +-- report.py              # JSON/HTML report generation
|   |   +-- auto_logger.py         # frame_metrics.csv, events.json, run_metadata.json
|   +-- ui/
|       +-- app.py                 # MainWindow — top bar, two viewports, dashboard, timers
|       +-- viewport.py            # CameraFOV + WorldFOV rendering with overlays
|       +-- control_deck.py        # Sliding Control Deck drawer — 7 tabs
|       +-- dashboard.py           # Metrics + IMM probs + PID + conditions panel
|       +-- benchmark_dialog.py
|       +-- live_dashboard_window.py
|       +-- theme.py
+-- docs/
|   +-- architecture.md            # this file
|   +-- algorithms.md
|   +-- configuration.md
|   +-- testing.md
|   +-- technical_report.md
|   +-- user_manual.md
|   +-- demo_script.md
+-- Resources/
|   +-- Implementation Plan.md
|   +-- Detailed Requirements.pdf
+-- data/  (input_videos, annotations — large files external)
+-- outputs/
    +-- runs/<timestamp>_<trajectory>_seedN/
        +-- config_used.yaml
        +-- run_metadata.json
        +-- frame_metrics.csv
        +-- events.json
        +-- summary_report.json
        +-- summary_report.html
```

---

## 5. Component Details

### 5.1 World (`simulation/world.py`)

Builds a 2000x2000 `base` once, then reuses it per-frame with cheap beacon overlay.

**Build order:** gradient/flat -> texture (0-5) -> brightness gain/offset -> stars -> vignetting. Twinkle jitter is applied per-frame in `render_world()` without rebuilding.

Supports **Sr.8 multi-target** (independent trajectories per beacon with offset seeds) and **Sr.9 shapes** (square, circle, gaussian, cross, user-defined polygon). Rendering does glow -> blur -> re-brightened core for realism.

```python
# src/fsoc_tracker/simulation/world.py:12
class World:
    def __init__(self, cfg, seed=42):
        self.base = self._build_base(cfg, seed)          # 2000x2000 uint8
        self.target_count = int(cfg["target"].get("count", 1))
        self.traj = make_trajectory(cfg, seed=seed)
        self.trajectories = [self.traj]
        for i in range(1, self.target_count):
            distractor_cfg = cfg.copy()
            distractor_cfg["target"] = cfg["target"].copy()
            distractor_cfg["target"]["trajectory"] = "random"
            self.trajectories.append(make_trajectory(distractor_cfg, seed=seed + i*1009))

    def render_world(self, world_pos=None):
        img = self.base.copy()
        # Sr.9 shapes: square/circle/cross/user-defined
        cv2.rectangle(img, (x-half, y-half), (x+half, y+half), int(self.target_intensity), -1)
        patch = cv2.GaussianBlur(img[y0:y1, x0:x1], (3,3), 0)
        return img
```

`update_config()` rebuilds `base` only when environment/world fields or seed change; `reset(seed)` rebuilds trajectories deterministically.

### 5.2 Virtual Camera (`simulation/virtual_camera.py`)

Maps world <-> image <-> angle. World centre (1000,1000) is (pan=0, tilt=0).

```python
# src/fsoc_tracker/simulation/virtual_camera.py:18
px_per_deg = 220.0  # tuned so 5 deg/s moves visibly
center_world = [world_center + pan*px_per_deg, world_center - tilt*px_per_deg]

# image error -> angle error (used by controller)
alpha = (u - W/2) * (HFOV / W)
beta  = -(v - H/2) * (VFOV / H)

# EKF measurement model (nonlinear tan)
fx = (W/2) / tan(HFOV/2)
u = cx + fx * tan(alpha_rad)
v = cy - fy * tan(beta_rad)
```

`apply_command(pan_rate, tilt_rate, dt)` clamps to `max_pan/tilt` and keeps the viewport inside 0..2000. `extract_viewport()` uses 1:1 pixel mapping; resize only if world size differs from resolution.

### 5.3 Trajectories (`simulation/trajectories.py`)

Seven classes under `Trajectory.step(t) -> (x,y)`, created by `make_trajectory(cfg, seed)`:

| Class | Motion | Formula |
|-------|--------|---------|
| `StraightTrajectory` | linear bounce | `pos = start + dir*speed*t`, reflect at 50 px margin |
| `CircularTrajectory` | circle | `omega = speed/r`, `(cx+r cos wt, cy+r sin wt)` |
| `FigureEightTrajectory` | figure-8 (Lissajous) | `x=cx+r sin wt`, `y=cy+r sin wt cos wt` |
| `RandomTrajectory` | random walk + momentum | `dir += N(0,0.06)`, `p+=dir*speed+N(0,0.5)`, bounce |
| `SpiralTrajectory` | expanding spiral | `r=min(80+2.2t,700)`, `w=0.04` |
| `SinusoidalTrajectory` | sinusoid wrapped | `x=100+(start+speed*t-100)%1800`, `y=cy+amp sin(2pi t speed/lambda)` |
| `UserDefinedTrajectory` | CSV `x,y` or `t,x,y` | load file else fallback straight line |

### 5.4 Platform Motion (`simulation/platform_motion.py`)

Independent scene shift returned as `(dx, dy)` per frame, clipped to +-20 px/frame. Types: `none`, `linear` (constant dir), `circular` (`amp=speed*8`, w=0.02), `random` (N(0,0.7*speed)), `spiral`, `figure_of_8`.

### 5.5 Noise & Atmosphere (`simulation/noise.py`)

Pipeline order (Implementation Plan section 8): clean render -> platform offset -> atmosphere -> Gaussian + Poisson + S&P -> jitter.

```python
# src/fsoc_tracker/simulation/noise.py
def apply_gaussian(img, std, rng): ...
def apply_salt_pepper(img, prob, rng): ...
def apply_poisson(img, rng): ...
def apply_jitter(img, jitter_px, rng): ...   # cv2.warpAffine
def apply_atmosphere(img, type, strength):   # haze/fog/rain/low_light
```

Each respects its configurable severity (e.g., `gaussian_std` 0-20, `salt_pepper_prob` 0-0.15, `jitter_px` +-20).

### 5.6 Beacon Detector (`perception/detector.py`)

Classic bright-spot detector — fast, explainable, no heavy NN.

```
grayscale -> GaussianBlur(3) -> bg=median, noise=std, p98=98th pct
threshold = max(bg + k*noise, p98-8, 120) clipped [80,230]
binary -> MORPH_OPEN(3x3 ellipse) -> connectedComponentsWithStats (8-conn)
for each component: area [8,900], aspect <=3.5, intensity-weighted centroid,
                   fill, brightness/peak/proximity scoring
select best; confidence = clip(0.35+0.65*score+(peak-180)/255*0.2, 0,1)
return Detection(valid, centroid_px, bbox, confidence, score, area)
```

Gating by predicted position (`Tracker.get_predicted_pixel()`) adds 0.2 proximity score weight, rejecting salt-noise false blobs.

### 5.7 Tracker (`tracking/tracker.py` + `ekf.py` + `imm.py` + `state_machine.py`)

`Tracker.step(detection, frame) -> Estimate` composes IMM prediction -> EKF update -> state machine.

- **EKF** — 6-state `[alpha,beta, alpha_dot,beta_dot, alpha_ddot,beta_ddot]`, constant-acceleration `F`, continuous-white-noise `Q`, nonlinear `h`, Jacobian `H` with `sec^2`, NIS gating at ~28, confidence-adapted `R`.
- **IMM** — three `SimpleEKF` (CV scale 0.6, CA 1.2, MN 3.0). Transition `[[0.9,0.08,0.02],[0.08,0.9,0.02],[0.05,0.1,0.85]]`, initial `[0.6,0.25,0.15]`. Likelihood `exp(-0.5*NIS)`. Fused `x_hat = sum mu_i x_i`.
- **StateMachine** — SEARCHING -> CANDIDATE (>=3 valid) -> ACQUIRING -> LOCKED (>=5 consecutive) -> TEMP_LOST (1-15 missed) -> REACQUIRING (16-30) -> SEARCHING/FAILED.

### 5.8 Controller (`control/camera_controller.py` + `pid.py`)

Normal tracking: `error_deg = fused alpha,beta`, `command = PID(error) + FF*velocity`, clamped to `[-max_pan,+max_pan]`. Deadzone ~0.015 deg*(deadzone/2), integral limit, derivative low-pass alpha=0.2, anti-windup, integral decay 0.96 in TEMP_LOST.

Search mode (SEARCHING/REACQUIRING/FAILED): expanding spiral `pan=cos(theta)*r*0.85`, `tilt=sin(theta)*r*0.85`, `theta+=0.32`, `r+=0.06` capped at 4.5 deg, ensuring re-acquisition <= 1 s.

### 5.9 Evaluation (`evaluation/metrics.py`)

`MetricsCollector.update()` logs per-frame `error_px = ||est-gt||`, `lock_valid`, `processing_ms`, `model_probs`; summary computes mean/RMSE/max/P95, `lock_retention = locked/total`, `loss_pct`, `acquisition_time`, `reacq_times`, `e2e_fps = total/duration`, `dropped`.

### 5.10 UI (`ui/`)

`MainWindow` owns two `Viewport` widgets (Camera FOV with reticle + yellow detection + green/cyan estimate + error vector; World FOV with yellow trail + cyan footprint), top bar (mode, state, seed, FPS, RUN/PAUSE/RESET/CONTROL DECK), `Dashboard` (accuracy, timing, lock/acq, IMM probs, PID, conditions), and sliding `ControlDeck` drawer (7 tabs: Presets, Target, Camera, Estimator/Controller, Environment, Disturbances, Input/Logging). A 30 Hz `QTimer` drives `pipeline_step()` separately from rendering.

---

## 6. Data Contracts (`common/types.py`)

```python
@dataclass
class Frame:        image: ndarray; frame_id: int; timestamp: float; source_name: str
@dataclass
class GroundTruth:  world_pos: (float,float); visible: bool; image_pos: Optional[(float,float)]
@dataclass
class Detection:    valid: bool; centroid_px: Optional[(float,float)]; bbox; confidence, score, area: float
@dataclass
class Estimate:     pos_px; pos_angle:(float,float); vel_angle; covariance; model_probs:(3,); tracking_state; innovation
@dataclass
class ControlCommand: pan_rate, tilt_rate: float; saturated, search_mode: bool
@dataclass
class MetricsFrame: frame_id, timestamp, error_px, error_angle, processing_ms, fps, lock_valid, tracking_state, ...
```

All modules exchange these typed objects, not bare dicts.

---

## 7. Configuration Flow

`configs/default.yaml` (or overlay `high_noise.yaml`) -> `config/loader.py` loads YAML, deep-merges with `DEFAULT_CONFIG` from `config/defaults.py` -> `validate_config()` asserts spec ranges -> passed to `World`, `VirtualCamera`, `BeaconDetector`, `Tracker`, `CameraController`, `MetricsCollector`. Live Control Deck edits call each component's `update_config(cfg)` without restart; `World._build_base` only rebuilds if environment/world fields change.

---

## 8. Runtime Sequences

### 8.1 SYNTHETIC step (per 30 Hz tick)

```
World.step() -> world_pos
World.render_world() -> world_image (2000x2000)
PlatformMotion.step() -> delta
VirtualCamera.extract_viewport(world_image) -> viewport (640x480)
apply_atmosphere -> apply_gaussian/salt_pepper/poisson -> apply_jitter
GroundTruth = VirtualCamera.world_to_image(world_pos)  # evaluator only
BeaconDetector.detect(viewport, predicted_pos) -> Detection
Tracker.step(Detection, Frame) -> Estimate
MetricsCollector.update(..., GroundTruth)
CameraController.step(Estimate) -> ControlCommand
VirtualCamera.apply_command(pan_rate, tilt_rate, dt)
Viewport/Dashboard repaint + AutoLogger append
```

### 8.2 VIDEO step

```
VideoFileSource.read() -> Frame (BGR->gray, no PTZ, no synthetic noise)
# remainder identical from BeaconDetector onward
```

---

## 9. Concurrency, Performance and Determinism

- **Single-threaded Qt event loop** with `QTimer(interval = 1000/fps)` — no detector/tracker threads.
- **Determinism:** seeded `numpy.random.default_rng(seed)` per subsystem. Seed saved in `config_used.yaml` for exact replay.
- **Profiling:** EKF/IMM/PID are O(1) per frame; detector dominates at O(W*H) connected components, kept < 10 ms via 640x480 viewport.

---

## 10. Error Handling and Safety

- `validate_config` fails fast on spec violations.
- `Detector.detect` returns `Detection(valid=False)` on degenerate frames — never raises.
- `EKF.update(None)` inflates `P` and skips correction; NIS > 28 rejects outliers.
- `VirtualCamera.apply_command` clamps rates; viewport centre clamped inside world.
- `MetricsCollector` treats `GroundTruth.image_pos=None` as loss, not NaN.
- Control integral clamped and decayed; anti-windup on saturation.

---

## 11. Extensibility

- New trajectory: subclass `Trajectory`, register in `make_trajectory`.
- New atmosphere: branch in `apply_atmosphere`.
- Learned detector: implement `detect(frame_gray, predicted_pos) -> Detection`.
- All without touching `FrameSource` or `MetricsCollector`.

---

## 12. Deployment View

Standalone desktop app (`python -m fsoc_tracker.main` or `launch.py`). No external services. Outputs are self-contained `outputs/runs/` folders. Large input videos and outputs are git-ignored.

---

## 13. References

- Implementation Plan.md sections 5-6 (architecture, coordinate model)
- Implementation Plan.md sections 19-26 (EKF-IMM-PID design)
- Implementation Plan.md section 31 (folder structure)
- Detailed Requirements.pdf — acceptance limits and Sr. tables
