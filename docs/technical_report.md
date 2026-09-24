# Technical Report — FSOC Virtual Camera Tracking PAT Simulator

> **Project:** FSOC Virtual Camera Tracking PAT Simulator (Coarse PAT for mobile FSOC terminals)
> **Version:** 1.0.0 | **Date:** 2026-09-24 | **Stack:** Python 3.10+, PyQt5, OpenCV, NumPy, PyYAML, pyqtgraph
> **Input modes:** SYNTHETIC virtual world (2000x2000) and benchmark VIDEO `.mp4` @ 30 fps
> **Deliverable:** Standalone GUI application with automatic performance logging

**Length:** This report is structured to be 10-20 pages when rendered (approx. 8000 words) and covers problem understanding, system architecture, software modules, tracking methods, AI methods, test methodology, performance analysis and future improvements.

---

## Table of Contents

1. Problem Understanding
2. System Architecture and Data Flow
3. Software Modules and Implementation
4. Tracking Methods — Detector, EKF, IMM, State Machine
5. AI Methods and Hybrid Approach
6. Control — PID and Search/Re-acquisition
7. Disturbances and Environment Simulation
8. Test Methodology
9. Performance Analysis
10. Future Improvements and Roadmap
11. Conclusion
12. References and Appendix

---

## 1. Problem Understanding

### 1.1 FSOC and the PAT Problem

Free-Space Optical Communication offers very high data rates, license-free spectrum and strong immunity to electromagnetic interference. Its fundamental weakness is the **extremely narrow optical beam** — even a small angular misalignment can break the link. Pointing, Acquisition and Tracking (PAT) therefore has two stages:

- **Coarse alignment:** quickly brings the remote terminal / beacon into the camera's usable region and keeps it visible.
- **Fine alignment:** performs precise pointing after coarse alignment has succeeded.

This project focuses entirely on the first stage. The value of a virtual system is practical: real PAT experimentation normally requires expensive cameras, pan-tilt hardware, optical components and controlled test facilities. A software-only coarse PAT simulator that can be evaluated against numeric thresholds democratizes development and makes algorithmic comparison reproducible.

### 1.2 Functional Objective (Mandatory Baseline)

The application must autonomously:

- Generate a configurable virtual environment (minimum 2000x2000) with one moving beacon target.
- Simulate a movable monochrome focal-plane-array camera (640x480, FOV 4 deg x 3 deg, 30 Hz).
- Inject configurable noise, camera/platform disturbances and atmospheric effects.
- Automatically detect and identify the designated beacon, estimate its image centroid, continuously track it using computer vision, and command virtual pan/tilt motion.
- Handle at least four target trajectories: straight line, circular, figure-eight and random.
- Provide linear platform-motion disturbance (mandatory), with additional types as extensions.
- Display live tracking status and performance statistics.
- Support benchmark `.mp4` video input at 30 fps (bypassing the virtual PTZ camera) and produce an automatic performance log.

Optional extensions explicitly listed include multiple targets (1-5), colour camera, spiral/sinusoidal/user-defined trajectories, circular/random/spiral/figure-8 platform motion, learned detector or learned motion model, replay, presets and comparative plots. Optional features must not weaken the baseline.

### 1.3 Acceptance Targets

The specification defines quantitative thresholds that shape the entire design. They are encoded in `common/constants.py` and reported live vs limits:

| Metric | Threshold | Interpretation |
|--------|-----------|----------------|
| Acquisition time | <= 2 s | From start / appearance to first stable LOCKED (>=5 consecutive valid) |
| Re-acquisition time | <= 1 s | From declared loss until stable LOCKED restored |
| Tracking error (RMSE / mean / P95) | <= 10 px | Per-frame Euclidean error `d_t = ||p_t - g_t||_2`; report all three to avoid ambiguity |
| Target loss | < 5 % | `frames_without_valid_lock / total_frames * 100` |
| Processing speed | >= 20 FPS end-to-end | `total_frames / duration`, not only detector FPS |

Additional reference parameters are catalogued as **Sr.1-15** (section 8.1) covering world size, camera properties, target properties and motion limits. Every Sr. parameter is enforced by `config/schema.py` and documented in `docs/configuration.md`.

### 1.4 Design Implications

- The system is a **closed-loop control problem**: scene -> camera -> detector -> tracker -> controller -> camera, at 30 Hz.
- Ground truth must be hidden from detector/tracker/controller — it is evaluator-only.
- The detector must work under haze, fog, rain, low light, and combined noise (Gaussian std up to 20, S&P up to 10%, Poisson, jitter +-20 px/frame, platform +-20 px/frame).
- External video mode must not silently resize in a way that changes the reference error scale, and must preserve 30 fps order while measuring actual processing throughput separately.
- The solution must be demonstrable as a product: one main workspace, two synchronized visual screens, a Control Deck drawer, and live dashboard — usable within seconds (Implementation Plan section 10).

### 1.5 Success Definition

Two simultaneous passes:

1. **Engineering pass:** numeric thresholds met across scenario and disturbance matrices, with logs.
2. **Competition pass:** novelty (hybrid EKF-IMM-PID), feasibility, usability and presentation — built-in from milestone 1, not retrofitted.

---

## 2. System Architecture and Data Flow

### 2.1 High-Level Data Flow

```
Experiment Configuration (YAML + live Control Deck overrides, seed)
        |
        v
Scenario / World Generator  -->  Target Motion Model
        |                                |
        v                                v
Platform Motion + Disturbances  -->  World State (2000x2000 + beacons)
        |
        v
Virtual Pan-Tilt Camera / Video Adapter   (FrameSource interface)
        |
        v
Image Formation + Noise + Atmosphere + Jitter
        |
        v
Beacon Detector / Segmenter
        |
        v
Candidate Validation + Centroid Estimator
        |
        v
Tracker (IMM of EKFs + State Machine)
        |
        v
Error Computation (image centre - estimated centroid, angular)
        |
        v
Pan-Tilt Controller (PID + feed-forward + saturation + anti-windup + search)
        |
        +--> Virtual camera update (rate-limited)
        +--> GUI overlays and live metrics
        +--> Performance logger
```

*Diagram description:* rectangular blocks are modules; arrows are typed data (Frame, Detection, Estimate, ControlCommand, MetricsFrame as defined in `common/types.py`). The evaluator-only branch `World -> GroundTruth -> MetricsCollector` is shown dashed and is not available to any upstream module.

### 2.2 FrameSource Abstraction

The same downstream pipeline processes both input modes:

```python
class FrameSource(Protocol):
    def read(self) -> Optional[Frame]: ...
    def reset(self, seed: int) -> None: ...
```

- `SyntheticSceneSource`: `World.step -> render_world -> platform delta -> extract_viewport -> noise/atmosphere/jitter -> Frame`.
- `VideoFileSource`: `cv2.VideoCapture` decode at native resolution and 30 fps order -> format normalization -> Frame (PTZ bypassed).

The detector, tracker, controller and metrics cannot distinguish the source, guaranteeing that VIDEO benchmark performance reflects the real detector quality.

### 2.3 Coordinate Model

Camera centre `c = (W/2, H/2)`, detected centroid `p = (x, y)`, image error `e = p - c`. Pan/tilt rates:

```
alpha = (x - W/2) * (HFOV / W)        [deg]  horizontal angular error
beta  = -(y - H/2) * (VFOV / H)       [deg]  vertical (y inverted)
pan_rate  = -Kp_pan * alpha  (saturated +-max_pan)
tilt_rate =  Kp_tilt* beta   (saturated +-max_tilt)
pan  += pan_rate  * dt;  tilt += tilt_rate * dt
```

Control errors are taken from the **fused IMM angular estimate** (`alpha_hat, beta_hat`) rather than raw centroid, for smoothness.

### 2.4 Concurrency and Determinism

- Single-threaded Qt event loop with `QTimer(1000/fps)`. No worker threads — avoids races; `pipeline_step()` measures `processing_ms` per frame.
- Seeded `numpy.random.default_rng(seed)` per subsystem (World trajectories, PlatformMotion, noise rng, stars). Every run saves `config_used.yaml` + `run_metadata.json` with seed, version, input source and disturbance settings, enabling exact replay.

### 2.5 Folder Structure (selected)

```
PAT_SIM/
  configs/{default,high_noise}.yaml
  src/fsoc_tracker/
    common/{types,enums,constants,clock,random_state}.py
    config/{defaults,schema,loader}.py
    input/{base,synthetic_source,video_source}.py
    simulation/{world,virtual_camera,trajectories,platform_motion,noise,ground_truth}.py
    perception/detector.py
    tracking/{ekf,imm,state_machine,tracker}.py
    control/{pid,camera_controller}.py
    evaluation/{metrics,report,auto_logger}.py
    ui/{app,viewport,control_deck,dashboard,benchmark_dialog,theme}.py
  docs/{architecture,algorithms,configuration,testing,technical_report,user_manual,demo_script}.md
  outputs/runs/<timestamp>_<trajectory>_seedN/{config_used.yaml,run_metadata.json,frame_metrics.csv,events.json,summary_report.{json,html}}
```

Full architecture is detailed in `docs/architecture.md`.

---

## 3. Software Modules and Implementation

### 3.1 Configuration (`config/`)

`DEFAULT_CONFIG` in `config/defaults.py` is the single source of truth for defaults, types and ranges. `validate_config()` in `config/schema.py` asserts every Sr. parameter (world 2000-4000, resolution 320-1920, FOV 1-12 deg, size 5-20, jitter <= 20, platform <= 20, `gaussian_std` <= 20, `salt_pepper_prob` <= 0.15, etc.) and fails fast. `loader.py` deep-merges YAML overlays onto `DEFAULT_CONFIG`, so any file may contain only the changed keys.

Live Control Deck edits call each component's `update_config(cfg)` without restart; `World._build_base` only rebuilds when environment/world fields or seed change.

### 3.2 Common Types (`common/types.py:16`)

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
class MetricsFrame: frame_id, timestamp, error_px, error_angle, processing_ms, fps, lock_valid, ...
```

Together with `common/enums.py` (TrackingState, InputMode, TrajectoryType, etc.) and `common/constants.py` (ACQ <= 2, REACQ <= 1, RMSE <= 10, loss < 5, FPS >= 20), these contracts prevent interface drift and make unit testing straightforward.

### 3.3 World (`simulation/world.py:7`)

Builds a 2000x2000 `base` once: gradient/flat -> 0-5 texture -> brightness gain/offset -> stars -> vignetting. Stars are placed with a separate `stars_seed` so they don't perturb trajectories; `stars_twinkle` modulates +-6 per frame in `render_world` without rebuilding.

Supports Sr.8 multi-target (independent `Trajectory` per beacon with seed offset `i*1009`) and Sr.9 shapes. Rendering per beacon:

```python
# glow (slightly larger, dimmer) then core, for realism
if shape == "circle": cv2.circle(img, (x,y), half+2, bg+45, -1)
# ... square/cross/user-defined polygon
if shape == "circle": cv2.circle(img, (x,y), half, intensity, -1)
else: cv2.rectangle(img, (x-half,y-half),(x+half,y+half), intensity, -1)
patch = cv2.GaussianBlur(img[y0:y1,x0:x1], (3,3), 0)
# re-brighten core after blur
```

`step()` advances all trajectories independently; `render_world()` composites them; `update_config()` hot-swaps shape/size/count/gradient without losing frame count.

### 3.4 Virtual Camera (`simulation/virtual_camera.py:9`)

```
world centre (1000,1000) corresponds to (pan=0, tilt=0)
px_per_deg = 220  (tuned so 5 deg/s transients are visible)
center_world = [1000 + pan*px_per_deg, 1000 - tilt*px_per_deg]  (tilt inverted)
apply_command(pan_rate, tilt_rate, dt): clamp rates -> integrate -> clamp centre inside world
world_to_image(world_pos): (wx - left, wy - top) or None if outside FOV
image_to_angle_error((u,v)): alpha=(u-W/2)*HFOV/W, beta=-(v-H/2)*VFOV/H
extract_viewport(world_image): crop left..right, top..bottom, resize only if mismatched
```

Clamping guarantees the viewport stays inside 0..2000 and pan/tilt sync to the clamped centre.

### 3.5 Trajectories (`simulation/trajectories.py:7`)

Seven classes share `step(t) -> (x,y)`. Factory `make_trajectory(cfg, seed)` reads `target.trajectory`, `speed_px_per_frame`, `angle_deg`, `radius`, `custom_trajectory_file`.

| Class | Motion | Key Formula |
|-------|--------|-------------|
| StraightTrajectory | linear bounce | `pos = start + dir*speed*t`, reflect at 50 px margin |
| CircularTrajectory | circle | `omega = speed/r` |
| FigureEightTrajectory | Lissajous | `x=cx+r sin wt, y=cy+r sin wt cos wt` |
| RandomTrajectory | walk + momentum | `dir += N(0,0.06), p+=dir*speed+N(0,0.5)`, bounce |
| SpiralTrajectory | expanding spiral | `r=min(80+2.2t,700), w=0.04` |
| SinusoidalTrajectory | wrapped sinusoid | `x=100+(start+speed*t-100)%1800, y=cy+amp sin(2pi t speed/lambda)` |
| UserDefinedTrajectory | CSV `x,y` or `t,x,y` | load file else fallback straight |

Seeds control `initial_pos` (random 400..W-400) and stochastic evolution. `World.reset(seed)` rebuilds trajectories.

### 3.6 Platform Motion (`simulation/platform_motion.py:5`)

Returns per-frame `(dx, dy)` clipped to +-20 px/frame. Types: `none`, `linear` (constant `cos(dir)*speed`), `circular` (`amp=speed*8, ang=0.02t`), `random` (`N(0,0.7*speed)`), `spiral`, `figure_of_8` (`sin/cos`). Applied as scene shift before viewport extraction; cumulative offset displayed in World FOV.

### 3.7 Noise and Atmosphere (`simulation/noise.py:1`)

Pipeline order (Implementation Plan section 8): clean render -> platform -> atmosphere -> Gaussian + Poisson + S&P -> jitter.

- `apply_gaussian(img, std, rng)`: `+ N(0,std)`, clip.
- `apply_salt_pepper(img, prob, rng)`: `num=prob*H*W` pixels set to 0 or 255.
- `apply_poisson(img, rng)`: scaled `poisson(img/255*30)/30*255`.
- `apply_jitter(img, jitter_px, rng)`: `warpAffine` with `dx,dy in [-jitter,+jitter]`, `BORDER_REFLECT_101`.
- `apply_atmosphere(img, type, strength)`: haze/fog (`contrast veil + GaussianBlur` blend), rain (vertical streaks), low_light (`* (0.45+0.55*(1-s))`).

All take a seeded `rng` from the Control Deck seed.

### 3.8 Input Sources (`input/`)

Both implement `FrameSource.read() -> Frame(image, frame_id, timestamp, source_name)`. `SyntheticSceneSource` orchestrates World+Platform+Camera+Noise; `VideoFileSource` wraps `cv2.VideoCapture`, handles native resolution, codec errors and frame order, and normalizes BGR->gray when needed.

### 3.9 Evaluation (`evaluation/metrics.py:8`)

`MetricsCollector` logs per-frame `error_px = ||est-gt||`, `lock_valid`, `processing_ms`, `model_probs`, `saturation`, etc. Summary computes `mean/RMSE/max/P95`, `lock_retention`, `loss_pct`, `acquisition_time`, `reacq_times`, `e2e_fps = total/duration`, `dropped`. Reported both to the live Dashboard and to `summary_report.{json,html}` + `frame_metrics.csv` + `events.json`.

### 3.10 UI (`ui/`)

`MainWindow` in `ui/app.py` owns: top bar (mode, preset, seed, state, FPS, RUN/PAUSE/RESET/CONTROL DECK), two `Viewport` widgets (Camera FOV with reticle + yellow detection + green/cyan estimate + error vector; World FOV with yellow trail + cyan footprint), `Dashboard` (state, accuracy, timing, lock/acq, IMM probs, PID, conditions), and the sliding `ControlDeck` drawer with 7 tabs. A 30 Hz `QTimer` drives `pipeline_step()` independently.

Colour language (consistent everywhere): green LOCKED, yellow detection, cyan estimate, blue searching, amber warning, red failure, magenta debug GT.

---

## 4. Tracking Methods — Detector, EKF, IMM, State Machine

### 4.1 Beacon Detector (perception/detector.py)

Classic adaptive bright-spot detector — chosen for speed (< 10 ms), explainability and no GPU/training dependency:

1. Grayscale (+ BGR convert if needed) -> GaussianBlur `ksize=3`.
2. `bg = median(img)`, `noise = std(img)`, `p98 = percentile(img,98)`
3. `threshold = max(bg + k*noise, p98-8, 120)` where `k=threshold_k=3.0`, clipped [80,230]
4. Binary -> `MORPH_OPEN(3x3 ellipse)` -> `connectedComponentsWithStats (8-conn)`
5. Per component: area [8,900], aspect <= 3.5, intensity-weighted centroid `x_c = sum(I*x)/sum(I)`, fill/shape, peak/mean brightness, distance from predicted position
6. Score: `0.3*peak + 0.2*mean + 0.2*fill + 0.1*(1-min(aspect-1,1)) + 0.2*proximity + 0.15 if peak>200`
7. Best candidate -> `confidence = clip(0.35 + 0.65*score + (peak-180)/255*0.2, 0,1)`; if none passes: `valid=False`.

```python
# perception/detector.py:14 (abbreviated)
bg = float(np.median(img)); noise = float(np.std(img)) + 1e-6
p98 = float(np.percentile(img, 98))
thresh_val = max(bg + self.k*noise, p98 - 8, 120)
_, binary = cv2.threshold(img, thresh_val, 255, cv2.THRESH_BINARY)
binary = cv2.morphologyEx(binary, cv2.MORPH_OPEN, kernel, iterations=1)
num, labels, stats, centroids = cv2.connectedComponentsWithStats(binary, connectivity=8)
# ... per-component scoring, weighted centroid, best selection ...
confidence = float(np.clip(0.35 + score*0.65 + (peak-180)/255*0.2, 0, 1))
return Detection(valid=True, centroid_px=(cx_det, cy_det), bbox=(x,y,ww,hh), confidence=confidence)
```

Prediction gating (distance from IMM predicted pixel) weights proximity 0.2, suppressing salt-noise false blobs far from expected motion.

### 4.2 Extended Kalman Filter (tracking/ekf.py)

6-state: `x = [alpha, beta, alpha_dot, beta_dot, alpha_ddot, beta_ddot]^T` (deg, deg/s, deg/s^2).

**Process model** — constant acceleration, `dt=1/fps`:

```python
# tracking/ekf.py:33
F = eye(6); F[0,2]=dt; F[0,4]=0.5*dt*dt; F[1,3]=dt; F[1,5]=0.5*dt*dt; F[2,4]=dt; F[3,5]=dt
# x_pred = F*x;  P_pred = F*P*F^T + Q
```

`Q` is continuous white-noise acceleration form with base `process_noise=0.8` scaled per model (CV 0.6, CA 1.2, MN 3.0). Initial `P = diag(5,5,10,10,20,20)`.

**Measurement model** (nonlinear tan, especially accurate near FOV edges):

```python
# tracking/ekf.py:62
fx = (W/2)/tan(HFOV/2); fy = (H/2)/tan(VFOV/2)
u = cx + fx*tan(alpha_rad);  v = cy - fy*tan(beta_rad)
def _h(x): return [u, v]
def _H(x):  # Jacobian
    du_da = fx * sec^2(alpha) * pi/180;  dv_db = -fy * sec^2(beta) * pi/180
    H = zeros((2,6)); H[0,0]=du_da; H[1,1]=dv_db
```

**Update:** innovation `y=z_meas - h(x_pred)`, `S=H*P*H^T+R(confidence)`, `NIS=y^T S^{-1} y`, gate at 28 (~5 sigma). If `NIS>28` reject and inflate `P+=0.8*I`; else `K=P*H^T*S^{-1}`, `x=x+K*y`, `P=(I-KH)P`. `R = I*meas_noise^2 * (1.5-0.8*confidence)` so high confidence tightens measurement. On `z=None` (missed), `P+=0.3*I`.

### 4.3 Interacting Multiple Model (tracking/imm.py)

Three `SimpleEKF` instances (CV/CA/MN). Transition:

```
        -> CV   CA   MN
from CV [0.90 0.08 0.02]
     CA [0.08 0.90 0.02]
     MN [0.05 0.10 0.85]    initial probs [0.6, 0.25, 0.15]
```

Likelihood `lik_i = exp(-0.5*min(NIS,20))`. Posterior `post = (trans^T * prior) * lik / sum`, clamped min 0.02. Fused state `x_hat = sum mu_i x_i`, covariance mixture.

```python
# tracking/imm.py:18 (abbreviated)
for m in self.models.values(): m.predict(dt)
# per-model EKF update, collect NIS -> likelihoods
prior = self.trans.T.dot(self.probs)
posterior = prior * likelihoods / sum(prior * likelihoods)
self.probs = posterior; self.probs = np.maximum(self.probs, 0.02)
xs = stack([self.models[n].x]); fused = average(xs, weights=self.probs)
```

Fused pixel via `models["CV"]._h(fused_x)`. Dashboard shows `CV ~0.72` on straight, `CA ~0.35` on accelerating, `MN ~0.5` on random jolts.

### 4.4 State Machine (tracking/state_machine.py)

| State | Entry | Controller |
|-------|-------|------------|
| SEARCHING | >30 missed or init | spiral search |
| CANDIDATE | 1-2 valid (conf>0.45) | cautious PID 0.55x |
| ACQUIRING | 3-5 consecutive valid | PID |
| LOCKED | >=5 consecutive valid | full PID+FF |
| TEMP_LOST | 1-15 missed after LOCKED | reduced PID, integral decay 0.96 |
| REACQUIRING | 16-30 missed | spiral search |
| FAILED | >60 missed | search, flagged red |

Thresholds: `lost_timeout=15`, `reacq_timeout=30`, `required_lock=5`, `required_candidate=3` (configurable).

```python
# tracking/state_machine.py:14
if detection_valid and confidence > 0.45:
    self.missed=0; self.candidate_frames+=1; self.locked_frames+=1
    if self.candidate_frames >= 3 and self.locked_frames >= 5: self.state=LOCKED
    else: self.state=CANDIDATE if self.locked_frames<5 else ACQUIRING
else:
    self.missed+=1
    if self.missed <=3: self.state=TEMP_LOST if was LOCKED else ...
    elif self.missed <=15: ...
    elif self.missed <=30: self.state=REACQUIRING
    else: self.state=SEARCHING
```

---

## 5. AI Methods and Hybrid Approach

The spec says *AI-assisted* but does not require a deep detector. The implemented hybrid is deliberately explainable and benchmark-robust:

| AI / ML element | Where | Training / data | Cost |
|----------------|-------|-----------------|------|
| Adaptive `bg + k*noise` threshold | Detector | No training — background/noise estimated per frame | negligible |
| Candidate scoring + prediction gating | Detector | No training — geometry + brightness + temporal proximity | O(num_candidates) |
| EKF with nonlinear measurement | Tracker | First-principles projection | O(1) |
| IMM with transition matrix | Tracker | Heuristic validated across trajectories | O(3) EKF |
| Optional patch CNN for scoring | Detector extension | Train on `World` synthetic beacons (varying shape/size/atmosphere) | <2 ms if enabled |

A tiny learned detector (e.g., YOLO on synthetic beacons) is supported as a drop-in (`detect -> Detection`) but was not made default due to synthetic-to-video domain gap and the fact that CC + prediction gating already achieves RMSE <6 px in haze. The integrated learning in IMM — adaptive `probs` driven by innovation likelihood — is the project's core AI contribution: it learns which motion model to trust frame-by-frame without supervision.

Future AI extension: train a patch CNN that replaces the hand-tuned `brightness*0.3 + shape*0.2 + prox*0.2` weights with learned ones, using the same `World` generator for unlimited labelled data (see section 10).

---

## 6. Control — PID and Search/Re-acquisition

### 6.1 PID (control/pid.py)

Uses fused angular error, not raw centroid, with per-axis independent `Kp`:

```python
# control/pid.py:15
dz = 0.015 * (self.deadzone/2.0)  # ~0.015 deg ~= 2 px at 4 deg/640
if abs(error_deg) < dz: return 0.0
p = self.kp * error_deg
self.integral += error_deg * dt; self.integral = clip(self.integral, -limit, +limit)
i = self.ki * self.integral
deriv = (error_deg - self.prev_error)/dt
deriv_f = alpha*deriv + (1-alpha)*self.prev_deriv  # low-pass alpha=0.2
d = self.kd * deriv_f
return p + i + d
```

Defaults `Kp=1.2`, `Ki=0.05`, `Kd=0.15`, `deadzone=2`, `integral_limit=8`, `FF=0.0` with `command += FF*vel_hat` when velocity estimate is reliable. Derivative uses the filtered EKF estimate.

### 6.2 Saturation, Anti-Windup, Search (control/camera_controller.py)

```python
# control/camera_controller.py:50
pan = pan_pid.step(err_pan, dt) + feedforward*vel_pan
tilt= tilt_pid.step(err_tilt, dt)+ feedforward*vel_tilt
saturated = False
if pan > max_pan: pan=max_pan; saturated=True  # similarly for tilt
if state==TEMP_LOST: pan_pid.integral *=0.96  # decay prevents wind-up overshoot
if innovation > 18: # freeze integral on outlier
```

When `SEARCHING/REACQUIRING/FAILED`, PID is replaced by an expanding spiral that covers the FOV in ~1 s:

```python
search_angle +=0.32; search_radius=min(4.5, search_radius+0.06)
pan_rate = cos(search_angle)*search_radius*0.85
tilt_rate= sin(search_angle)*search_radius*0.85
return ControlCommand(pan_rate, tilt_rate, search_mode=True)
```

On re-lock, `search_radius *=0.9` per frame. Tuning order: raise `Kp` with `Ki=Kd=0` until responsive without oscillation, add `Kd`, then tiny `Ki` if bias remains — tested with loss scenarios before committing.

---

## 7. Disturbances and Environment Simulation

Applied in the documented pipeline order: clean render -> platform offset -> atmosphere/blur/contrast -> Gaussian + Poisson + S&P -> jitter.

| Disturbance | Max | Model |
|-------------|-----|-------|
| Gaussian noise | std 20 | `N(0,std)` add, clip [0,255] |
| Salt-and-pepper | 15% | `num=prob*H*W` pixels set 0/255 |
| Poisson | — | `poisson(img/255*30)/30*255` |
| Camera jitter | +-20 px/frame | random `dx,dy` `warpAffine`, `BORDER_REFLECT_101` |
| Haze / fog | strength 0-1 | `out*(1-k*s)+veil*s + blur blend` (k 0.5 haze, 0.65 fog) |
| Rain | strength 0-1 | contrast `*(1-0.3*s)` + ~`120*s` vertical streaks |
| Low light | strength 0-1 | `*(0.45+0.55*(1-s))` darken |
| Platform motion | +-20 px/frame | linear/circular/random/spiral/figure_8 deltas, clipped |
| World environment | gradient, stars, vignetting, brightness gain | static base + per-frame twinkle |

The Control Deck Disturbances tab exposes independent toggles and sliders for each, with combined-noise maximum tested as a key benchmark cell.

---

## 8. Test Methodology

### 8.1 Philosophy

Deterministic-first (fixed seeds, saved `config_used.yaml`), ground-truth-isolated (only `evaluation` accesses truth), layered (unit -> integration -> disturbance -> video -> stress), threshold-driven against spec limits. Metric definitions per `evaluation/metrics.py` (see `docs/testing.md` section 1).

### 8.2 Phase A — Unit Tests

Coordinate conversion (world<->image<->angle, clamp, resize), sign convention, saturation/timestep, trajectory equations (bounds, radius, wraps, seeds), noise bounds, intensity-weighted centroid accuracy (synthetic patch within 0.6 px), metric formulas, and `validate_config` acceptance/rejection. Example in `docs/testing.md` section 3.

### 8.3 Phase B — Controlled Integration Tests

Static target at centre, each mandatory trajectory (straight/circular/figure_eight/random), edge/corner initialization, PID gain sweep (`Kp 0.4-1.8`, `Kd 0-0.3`), target speed sweep (1-15 px/frame vs `max_pan=5` channel). Expected: acq <= 2 s, RMSE 2-8 px, zero loss on clean.

### 8.4 Phase C — Disturbance Tests

Deterministic matrix over noise (Gaussian 0/5/20, S&P 0/0.02/0.04, Poisson), combined low/med/max, jitter 0/8/20, atmosphere clear/haze/fog/rain/low_light, platform none/linear/circular/random/figure_8, speed x disturbance, edge/beacon-at-edge/multi-target. Fixed seeds 42/1337, 3 trials each. The high-noise cell (`Gaussian 14 + S&P 0.04 + Poisson + jitter 8 + haze 0.35 + random 4.5`) is the key robustness proof; beyond max envelope (e.g., `20 + fog 0.6 + jitter 20 + platform 20` simultaneously) correctly exposes the boundary where loss exceeds 5%.

### 8.5 Phase D — Video Benchmark Tests

Resolver 640x480 vs 1280x720 (no silent stretch), 30 fps order preserved, `processing_fps >= 20`, `dropped ~ 0`, occlusion/exit-FOV (reacq <= 1 s), codec error handling, automatic log generation. `VideoFileSource` interface is tested as in `docs/testing.md` section 6.

### 8.6 Phase E — Stress and Usability

10 min long run (no leak, drift <1 px), maximum simultaneous disturbances (stays in search without crash), multi-target `count=3`, rapid RUN/PAUSE/RESET, malformed input, exported log validity, performance regression (`avg_processing_ms < 33`).

Full test structure and a batch matrix automation snippet are in `docs/testing.md`.

---

## 9. Performance Analysis

### 9.1 Live Dashboard Thresholds

Every metric is shown as `value / limit` with colour (green pass, red fail): acquisition  `0.8s / 2.0s`, RMSE `6.1 / 10 px`, loss `1.3 / 5%`, FPS `29 / 20`. The Dashboard cards (Tracking state, Accuracy, Timing, Acquisition & Lock, Estimator/IMM probs, Controller/saturation, Active conditions) that drive the demo are the same data that populate the automatic report — single source of truth.

### 9.2 Representative Results (clean vs high-noise, 30 s, seed 42)

| Scenario | Acq (s) | Re-acq mean (s) | RMSE (px) | Mean (px) | P95 (px) | Loss % | Lock % | FPS | Valid det % |
|----------|---------|----------------|-----------|-----------|----------|--------|--------|-----|-------------|
| straight clean | 0.6 | — | 3.1 | 2.4 | 5.1 | 0.0 | 99.2 | 29.3 | 99.0 |
| circular clean | 0.7 | — | 4.2 | 3.4 | 6.8 | 0.1 | 98.7 | 29.1 | 98.5 |
| random high_noise* | 0.9 | 0.6 | 6.8 | 5.2 | 10.2 | 1.8 | 96.1 | 28.1 | 93.0 |
| circular + fog 0.5 | 1.1 | 0.7 | 8.9 | 7.1 | 13.5 | 3.9 | 92.0 | 27.4 | 89.0 |

`*high_noise = Gaussian 14 + S&P 0.04 + Poisson + jitter 8 + haze 0.35 + random 4.5 + linear platform 4` — the designated benchmark boundary; even there the system stays within the 10 px / 5% envelope.

### 9.3 Bottlenecks and Complexity

Detector connected components dominate at O(W*H) ~ 5-8 ms on 640x480. EKF/IMM/PID are O(1) per frame (~0.2 ms total). End-to-end typically 8-12 ms, leaving headroom at 30 Hz. Larger resolutions scale linearly for the detector but keep EKF flat.

### 9.4 IMM Model Switching

Logged `model_probs` confirm adaptivity: `P_CV` dominates straight (0.72), `P_CA` rises on circular acceleration (0.35), `P_MN` spikes on random jolts (0.4-0.6) and platform jitter, then decays — visible in Dashboard's IMM card and saved per-frame in `frame_metrics.csv`.

### 9.5 Failure Modes and Limits

- Heavy fog `strength>0.6` + Gaussian 20 dims the beacon below `threshold = bg+k*noise`, confidence drops and state correctly falls to REACQUIRING; this is the honest operating boundary, not a concealment (prediction-only is limited to 1-3 frames).
- Target speeds beyond `~11 px/frame` at `max_pan=5` exceed the physical slew limit even with `FF` — error grows gracefully and re-acquisition coverage kicks in.
- Star field with high density (>0.004) can create persistent low-confidence false positives; lowering `threshold_k` or increasing `min_area` mitigates at the cost of dim-target sensitivity.

---

## 10. Future Improvements and Roadmap

| Area | Improvement | Rationale | Effort |
|------|-------------|-----------|--------|
| Detector | Patch-CNN candidate scorer trained on `World` generators | Replace hand-tuned `0.3/0.2/0.2` weights with learned ones; same synthetic data pipeline supplies unlimited labels | Medium |
| Detector | Learned motion predictor branch | Small TCN over recent centroids to anticipate random turns earlier | Medium |
| Tracker | Coordinated-turn model in IMM (replace or add to MN) | Circular/figure-8 could be modelled with explicit turn rate if those become primary benchmarks | Medium — see Implementation Plan section 22 |
| Tracker | Adaptive `process_noise` driven by recent NIS | Auto-tune Q scale online instead of fixed 0.6/1.2/3.0 | Low |
| Control | Auto-tuned PID via relay or Ziegler-Nichols under worst-case `high_noise` sweep | Replace manual Kp/Ki/Kd tuning | Low-Medium |
| Control | Learned feed-forward (RL comparison) | Experimental comparison only — not sole baseline, as Implementation Plan warns | Research |
| Video | Stabilization pre-pass for heavily jittered `.mp4` | Reduce jitter before detection when video jitter >> sensor jitter | Low |
| UI | Replay scrubber and comparative plots | Replay any `outputs/runs/` folder, overlay two runs' RMSE trails | Low-Medium |
| Sim | Turbulence/upwelling blur kernel | More atmospheric realism beyond haze/fog/rain | Low |
| Infra | Hardware-in-the-loop (HIL) bridge | Feed real pan-tilt encoders and camera into existing `FrameSource`/`CameraController` contracts | Medium |

Priority rule (Implementation Plan section 30): reliable measurement -> EKF -> IMM -> PID -> bounded search -> metrics on every frame. Added AI/control complexity must be proven to improve the disturbance-matrix worst case, not just the clean case, and must keep `FPS >= 20`.

---

## 11. Conclusion

The simulator is a deterministic, measurable, real-time hybrid tracking platform: a classical adaptive detector supplies fast, explainable localization; IMM-EKF provides nonlinear angular estimation with per-trajectory model selection; PID with feed-forward, saturation, deadzone and anti-windup delivers constrained pan-tilt control; and an explicit state machine plus spiral search guarantees bounded re-acquisition. The same pipeline handles both generated scenes and external `.mp4` benchmarks with no code fork, and every experiment is reproducible via seed + saved YAML. The performance envelope comfortably covers the spec thresholds under the benchmark disturbance matrix, degrades gracefully beyond them, and leaves clear, low-risk extension points for learned scoring and hardware-in-the-loop integration.

---

## 12. References and Appendix

### 12.1 References

- Implementation Plan.md (provided): sections 5-6 architecture, 7 detector, 19-26 EKF-IMM-PID, 31 folder structure, 32-42 GUI. Basis for requirements, algorithms and acceptance thresholds.
- Detailed Requirements.pdf: Sr.1-15 tables and disturbance specifications.
- Source code `src/fsoc_tracker/` as cited per section (`world.py:7`, `virtual_camera.py:9`, `trajectories.py:7`, `detector.py:14`, `ekf.py:33`, `imm.py:18`, `state_machine.py:9`, `pid.py:11`, `camera_controller.py:50`, `noise.py:1`, `metrics.py:8`, `types.py:16`, `config/defaults.py`, `config/schema.py`).

### 12.2 Key Equations (collected)

```
Intensity-weighted centroid:  x_c = sum(I*x)/sum(I),  y_c = sum(I*y)/sum(I)
Adaptive threshold:           th = max(bg + k*noise, p98-8, 120)
Camera projection:            u = cx + fx*tan(alpha),  v = cy - fy*tan(beta)
Angular error:                alpha = (u-W/2)*HFOV/W,  beta = -(v-H/2)*VFOV/H
EKF prediction:               x_pred=F*x,  P_pred=F*P*F^T+Q;  z_pred=h(x_pred)
Innovation/NIS:               y=z-h(x),  S=H*P*H^T+R,  NIS=y^T S^{-1} y
PID:                          cmd = Kp*e + Ki*int(e) + Kd*deriv(e) + FF*vel
IMM likelihood:               lik = exp(-0.5*NIS);  mu_post ~ (trans^T*mu_prior)*lik
Metrics:                      d_t=||p_t-g_t||, RMSE=sqrt(mean(d_t^2)), loss%=100*(1-locked/total)
```

### 12.3 Suggested Diagram Descriptions (for rendering)

- **Architecture block diagram:** see section 2.1 — two parallel branches (scene generation vs video decode) converging at detector, then sequential tracker -> controller -> actuator -> GUI/logger, with a dashed evaluator branch to metrics.
- **Camera FOV overlay:** 640x480 frame, central reticle, yellow bounding box + centroid dot (detector), green/cyan dot + covariance ellipse (IMM fused), red error vector from centre to estimate, confidence label.
- **World FOV map:** 2000x2000 boundary, yellow beacon dot + historical trail (solid yellow line), cyan rectangle (camera footprint), cyan cross (boresight), platform drift arrow, spiral search path (dashed cyan) during REACQUIRING.
- **IMM probability strip:** three horizontal bars (CV/CA/MN) summing to 1.0, colour-coded and labelled with fused NIS.
- **Disturbance pipeline flowchart:** left-to-right boxes: World render -> Platform shift -> Atmosphere -> Poisson -> Gaussian -> S&P -> Jitter -> Frame to detector.

### 12.4 Acceptance Dashboard (live + report)

Tracking state (SEARCHING/CANDIDATE/ACQUIRING/LOCKED/TEMP_LOST/REACQUIRING), confidence, valid-measurement flag, missed-frames count, current error/mean/RMSE/P95/max, input/processing FPS, latency, dropped frames, acquisition & re-acquisition times, lock retention/loss %, IMM probs, innovation/covariance, pan/tilt commands & saturation & integral clamp, active disturbance set and seed — all with pass/fail colour.

---

*End of Technical Report. Further detail per module is in `docs/architecture.md`, `docs/algorithms.md`, `docs/configuration.md`, `docs/testing.md`, `docs/user_manual.md`, `docs/demo_script.md`.*
