# FSOC Virtual Camera Tracking — Structured Notes

## 1. Executive summary

This problem asks for a **software-only coarse pointing, acquisition and tracking (PAT) simulator** for mobile Free Space Optical Communication (FSOC) terminals. The system must control a virtual pan–tilt camera so that it can find, center and continuously follow a moving optical beacon under realistic disturbances.

The core challenge is not merely object detection. It is a closed-loop control problem:

1. A virtual scene produces a target and background.
2. The camera observes only its current field of view.
3. The vision module detects the beacon and estimates its centroid.
4. The controller converts image error into pan/tilt commands.
5. The virtual camera moves within speed limits.
6. The next frame is generated, and the loop repeats.

The solution is judged on both **technical capability** and **demonstrable product quality**: mandatory functionality, robustness under benchmark scenarios and videos, measurable tracking performance, architecture, innovation, usability, documentation and presentation.

## 2. Why the problem matters

FSOC can offer very high data rates, license-free spectrum and strong immunity to electromagnetic interference. Its main weakness is the extremely narrow optical beam. Even a small angular misalignment can break the link.

PAT therefore has two stages:

- **Coarse alignment:** quickly brings the remote terminal or beacon into the camera’s usable region and keeps it visible.
- **Fine alignment:** performs precise pointing after coarse alignment has succeeded.

This project focuses on the first stage. The virtual system is valuable because real PAT experimentation normally requires expensive cameras, pan–tilt hardware, optical components and controlled test facilities.

## 3. Problem interpreted as system requirements

### 3.1 Functional objective

Build an application that autonomously:

- generates a configurable virtual environment;
- generates one or more moving beacon targets;
- simulates a movable camera viewport;
- detects and identifies the designated beacon;
- estimates its image position, preferably its centroid;
- continuously tracks it using computer vision;
- commands virtual pan and tilt motion;
- injects configurable noise, jitter, platform motion and atmospheric effects;
- displays live tracking status and performance statistics;
- produces an automatic performance log.

### 3.2 Mandatory versus optional scope

**Mandatory baseline**

- One moving beacon target.
- Monochrome focal-plane-array style camera model.
- At least four target trajectories: straight line, circular, figure-eight and random.
- Linear platform motion disturbance.
- Configurable noise and camera/platform disturbances.
- Virtual pan–tilt control.
- Automatic detection, centroiding, acquisition, continuous tracking and re-acquisition.
- Real-time statistics and exportable performance logs.
- Input support for benchmark `.mp4` video at 30 fps, bypassing the virtual PTZ camera.

**Useful optional extensions**

- Multiple targets.
- Colour camera mode.
- Spiral, sinusoidal and user-defined trajectories.
- Circular, random, spiral or figure-eight platform motion.
- Learned detector or learned motion model.
- Replay, experiment presets and comparative plots.

The optional features should not weaken the mandatory baseline. A reliable, measurable baseline is more valuable than a large but unstable feature set.

## 4. Reference parameters and acceptance targets

| Area | Parameter | Suggested/reference value | Design implication |
| --- | --- | --- | --- |
| Scene | Screen size | Minimum 2000 × 2000 px | Provide a larger world canvas than the camera viewport. |
| Camera | Type | Monochrome focal-plane array | Use intensity-first processing; colour can be optional. |
| Camera | Resolution | 640 × 480 px | Make resolution user-configurable where practical. |
| Camera | FOV | Default 4° × 3° | Convert pixel error to angular error for control. |
| Camera | Update rate | At least 30 Hz | Keep simulation/rendering separate from control if needed. |
| Camera | Initial position | Screen centre | Define deterministic initial state for repeatable tests. |
| Target | Type | Beacon spot | Model a bright, localized optical source. |
| Target | Count | One mandatory | Multi-target support is optional. |
| Target | Shape | Default square | Keep target generation configurable. |
| Target | Size | 5–20 px per side; default 10 × 10 | Test small and large apparent targets. |
| Target | Initial location | User-defined; default random | Record the random seed for reproducibility. |
| Target | Motion | Straight, circular, figure-eight, random | Expose trajectory and speed parameters. |
| Camera motion | Maximum pan speed | Default 5°/s; user-defined 5–10°/s | Apply saturation; never command impossible motion. |
| Camera motion | Maximum tilt speed | Default 5°/s; user-defined 5–10°/s | Apply independent pan/tilt limits. |
| Camera motion | Update interval | At least 20 Hz | Control loop must run fast enough for stable tracking. |
| Performance | Acquisition time | ≤ 2 s | Measure from start/appearance to valid lock. |
| Performance | Tracking error | ≤ 10 px | Report mean, RMSE, maximum and percentile error. |
| Performance | Target loss | < 5% | Define loss as frames without a valid lock. |
| Performance | Re-acquisition time | ≤ 1 s | Use a recovery/search mode after loss. |
| Performance | Processing speed | ≥ 20 FPS | Report end-to-end FPS, not only detector FPS. |
| Noise | Types | Salt-and-pepper, Gaussian, Poisson | Allow one or more simultaneously. |
| Noise | Maximum standard deviation | 20 px | Make severity configurable and log it. |
| Disturbance | Camera jitter | ±20 px/frame | Apply image-space or angular perturbation consistently. |
| Atmosphere | Conditions | Clear, haze, fog, rain, low light | Model contrast/brightness reduction first. |
| Platform | Motion | Up to ±20 px/frame; linear mandatory | Separate platform motion from camera actuation. |

### Important ambiguity to resolve in implementation

The specification uses both **camera update rate** and **control update interval**, and it lists 30 Hz for the camera but at least 20 Hz for the control. A robust design should run the visual pipeline at 30 fps or faster and the control loop at no less than 20 Hz. For benchmark video, process frames at their native 30 fps while measuring actual processing throughput separately.

## 5. Recommended system architecture

```
Experiment Configuration
        |
        v
Scenario / World Generator ----> Target Motion Model
        |                                |
        v                                v
Platform Motion + Disturbances --> World State
        |
        v
Virtual Pan–Tilt Camera / Video Adapter
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
Tracker + State Machine + Prediction
        |
        v
Error Computation (image centre - target centroid)
        |
        v
Pan–Tilt Controller with saturation and rate limits
        |
        +--> Virtual camera update
        +--> GUI overlay and live metrics
        +--> Performance logger
```

### 5.1 Core modules

1. **Configuration manager** — validates parameters, presets and random seeds.
2. **Scene/world generator** — maintains the full 2D world and target ground truth.
3. **Target-motion engine** — implements trajectories and target appearance.
4. **Platform-motion model** — moves the apparent scene independently of camera commands.
5. **Virtual camera model** — maps world coordinates to a viewport using pan, tilt, FOV and resolution.
6. **Disturbance pipeline** — applies noise, jitter, blur/contrast loss and atmospheric effects in a known order.
7. **Input adapter** — supports both generated frames and external `.mp4` frames.
8. **Beacon detector** — finds candidate bright regions or learned detections.
9. **Centroiding and validation** — estimates subpixel or pixel centroid and rejects false candidates.
10. **Tracker and state machine** — manages acquisition, lock, temporary loss and re-acquisition.
11. **Controller** — converts image-space error into constrained pan/tilt commands.
12. **Metrics and logger** — records ground truth, estimates, error, timing and state transitions.
13. **GUI/presentation layer** — shows the feed, target overlay, reticle, control state and metrics.

Keep ground truth and estimator output separate. Ground truth is for evaluation and must never leak into the detector or controller.

## 6. Coordinate model and control loop

Let the camera image centre be:

- `c = (W/2, H/2)`

Let the detected beacon centroid be:

- `p = (x, y)`

The image error is:

- `e = p - c = (x - W/2, y - H/2)`

A simple proportional controller is a suitable baseline:

- `pan_rate = -Kp_pan × e_x × (HFOV / W)`
- `tilt_rate =  Kp_tilt × e_y × (VFOV / H)`

The sign convention must be defined once and tested with a calibration scene. Depending on the coordinate convention, the tilt sign may need inversion.

Then clamp commands:

- `pan_rate ∈ [-max_pan_speed, +max_pan_speed]`
- `tilt_rate ∈ [-max_tilt_speed, +max_tilt_speed]`

Update camera angles using the control timestep `Δt`:

- `pan  = pan  + pan_rate  × Δt`
- `tilt = tilt + tilt_rate × Δt`

A better practical controller is a **dead-zone proportional controller with optional derivative damping**:

- dead zone prevents jitter near the centre;
- proportional action recentres the target quickly;
- derivative action reduces overshoot;
- command saturation enforces physical limits;
- slew-rate limiting prevents unrealistic jumps.

Use integral action cautiously. It can accumulate error when the target is lost or a command is saturated, causing wind-up. If integral action is added, include anti-windup and reset it during loss/re-acquisition.

## 7. Detection and tracking strategy

### 7.1 Baseline detector

Because the target is a beacon spot, a classical detector is likely to be more explainable and reliable than a heavy neural network for the first version:

1. Convert to monochrome/intensity.
2. Apply optional denoising or a small Gaussian filter.
3. Estimate a threshold using a fixed threshold, percentile threshold or adaptive threshold.
4. Apply morphological opening/closing if noise creates fragmented regions.
5. Find connected components or contours.
6. Score candidates using brightness, area, shape, compactness and proximity to the predicted location.
7. Compute the intensity-weighted centroid of the selected component.

For a pixel set `S` with intensity `I(x,y)`, the weighted centroid is:

- `x_c = Σ(I(x,y) × x) / ΣI(x,y)`
- `y_c = Σ(I(x,y) × y) / ΣI(x,y)`

This is preferable to a bounding-box centre when the spot is blurred, noisy or partially occluded.

### 7.2 Tracking state machine

Use explicit states rather than a single Boolean:

- **SEARCHING:** no valid target; camera performs a bounded search pattern or uses prior motion.
- **CANDIDATE:** a possible target has been detected but confidence is not yet stable.
- **ACQUIRING:** detections are consistent and the controller is moving toward the beacon.
- **LOCKED:** valid detections are being maintained and error is monitored.
- **TEMPORARILY LOST:** detections have failed for a short period; use prediction and local search.
- **RE-ACQUIRING:** expand the search region or scan while enforcing the ≤1 s target.
- **FAILED/ABORTED:** recovery timed out or the experiment ended.

This state machine makes acquisition time, loss rate and re-acquisition time measurable and auditable.

### 7.3 Prediction and robustness

Use a lightweight constant-velocity predictor or Kalman filter:

- state: `[x, y, vx, vy]`;
- measurement: detected `[x, y]`;
- prediction: used to gate candidates and bridge brief detection failures.

Do not allow prediction to hide persistent failure. A lock should be counted only while measurements remain valid within a defined timeout.

### 7.4 AI-assisted enhancements

The specification says AI-assisted, but it does not require a deep-learning detector. Strong options are:

- a learned classifier for candidate patches after classical proposal generation;
- an adaptive threshold model that learns background brightness/noise;
- a learned motion predictor for difficult trajectories;
- a small object detector trained on synthetic beacon images;
- reinforcement-learning or learned control only as an experimental comparison, not as the sole baseline.

A hybrid approach is defensible: classical vision supplies fast, explainable localization, while AI improves candidate validation or prediction under noise. Report the AI method, training data generation, inference cost and failure cases.

## 8. Disturbance and simulation design

Apply disturbances in a reproducible, documented pipeline. A recommended order is:

1. Generate clean world and target.
2. Render the current camera viewport.
3. Apply platform/camera motion effects.
4. Apply blur, contrast/brightness reduction or atmospheric degradation.
5. Add Poisson, Gaussian and salt-and-pepper noise.
6. Add camera jitter if it is modelled as image-space disturbance.
7. Deliver the frame to the detector.

Record the random seed, disturbance type, severity and trajectory for every run. This enables exact replay and fair comparison.

### Disturbance test matrix

- Clear, low-noise baseline.
- Each noise type separately.
- Combined noise at low, medium and maximum severity.
- Camera jitter at 0, moderate and ±20 px/frame.
- Linear platform motion at increasing speeds.
- Haze, fog, rain and low-light presets.
- Target speeds near the controller limit.
- Target temporarily leaving the viewport.
- Initial target positions near the viewport edge and far from centre.

## 9. Metrics and definitions

The performance log should include both configuration and results.

### 9.1 Required metrics

- Simulation/video duration.
- Input FPS, processed FPS and end-to-end FPS.
- Frame count and dropped frames.
- Acquisition time.
- Re-acquisition time for every loss event and summary statistics.
- Mean/average centroiding error.
- RMSE of centroiding error.
- Maximum error and useful percentiles such as P95.
- Lock retention rate.
- Target loss percentage.
- Detection confidence and valid-detection count.
- Average and maximum processing time per frame.
- Pan/tilt commands and saturation count.
- Number of acquisition, loss and re-acquisition events.

### 9.2 Metric definitions

Let `g_t` be ground-truth target position and `p_t` the estimated position. Per-frame Euclidean error is:

- `d_t = ||p_t - g_t||₂`

Then:

- **Mean error:** `mean(d_t)` over valid detections or over all frames, but state which one is used.
- **RMSE:** `sqrt(mean(d_t²))`.
- **Maximum error:** `max(d_t)`.
- **Tracking error pass condition:** choose and document whether it means mean error, RMSE or a specified percentile ≤10 px. Report all three to avoid ambiguity.
- **Target loss rate:** `frames_without_valid_lock / total_frames × 100`.
- **Lock retention:** `locked_frames / eligible_frames × 100`.
- **Acquisition time:** elapsed time from experiment start or target introduction until the first stable lock. Define a stable lock, for example, as N consecutive valid detections within the error threshold.
- **Re-acquisition time:** elapsed time from declared loss until stable lock is restored.
- **FPS:** processed frames divided by elapsed processing time; also show real-time ratio against input FPS.

Ground-truth evaluation is possible in generated scenarios. For external benchmark videos, use the predefined reference error values or an annotation protocol supplied by the evaluator.

## 10. GUI and user experience

The application should make success visible in seconds. Recommended layout:

### Main viewport

- Current camera frame.
- Image centre reticle.
- Detected centroid marker.
- Predicted centroid marker, if different.
- Bounding box or blob outline.
- Current pan/tilt angles and commanded rates.
- State label: SEARCHING, ACQUIRING, LOCKED, LOST or RE-ACQUIRING.

### Side panel

- Scenario selector.
- Target trajectory and speed.
- Camera resolution, FOV and update rate.
- Pan/tilt limits.
- Noise and atmospheric presets.
- Platform motion and jitter controls.
- Random seed.
- Start, pause, reset and replay controls.
- Input mode: generated scene or `.mp4`.

### Metrics panel

- Current error, mean error, RMSE and maximum error.
- Acquisition/re-acquisition timers.
- Lock retention and loss percentage.
- FPS and processing time.
- Event counters.

Include an export button for CSV/JSON and a human-readable summary report.

## 11. External video mode

Benchmark Performance-2 is important: the evaluator may provide a complete-screen `.mp4` at 30 fps, containing noise and a moving beacon. The software must bypass the virtual PTZ camera and send decoded frames directly into the coarse pointing pipeline.

Design the pipeline with a common interface:

```
FrameSource
  ├── SyntheticSceneSource
  └── VideoFileSource
          |
          v
Disturbance/normalization adapter if required
          |
          v
Detector -> tracker -> metrics -> GUI/logging
```

In video mode:

- preserve frame order;
- handle videos whose dimensions differ from 640 × 480;
- report the original FPS and actual processing FPS;
- avoid silently resizing in a way that changes the reference error scale;
- allow calibration of the image centre and pixel coordinates;
- clearly separate camera-control commands from measurement-only evaluation when no PTZ camera is present.

## 12. Testing and validation plan

### Phase A — unit tests

- Coordinate conversion and FOV-to-pixel calculations.
- Pan/tilt sign convention.
- Speed saturation and timestep handling.
- Target trajectory equations.
- Noise generators and severity bounds.
- Centroid calculation on synthetic shapes.
- Metric formulas and event timing.

### Phase B — controlled integration tests

- Static target, no noise.
- Target moving in each mandatory trajectory.
- Target starting at centre, edge and far corner.
- Controller gain sweep.
- Target speeds below and near camera limits.

### Phase C — disturbance tests

Run a matrix across noise, atmosphere, jitter and platform motion. Use fixed seeds, repeated trials and confidence intervals where practical.

### Phase D — video benchmark tests

- Test different resolutions and aspect ratios.
- Verify 30 fps ingestion.
- Compare estimated error against predefined reference values.
- Confirm logs are generated automatically.
- Check behaviour when the target is briefly obscured or leaves the field of view.

### Phase E — stress and usability tests

- Long-duration run.
- Maximum disturbance settings.
- Multiple targets if implemented.
- Start/stop/reset/replay.
- Malformed or missing video input.
- Exported log inspection.

## 13. Deliverables checklist

- **Standalone software application:** complete mandatory functionality.
- **Source code:** modular, documented and adequately commented.
- **Technical report, approximately 10–15 pages:** problem understanding, architecture, modules, tracking and AI methods, test methodology, performance analysis and future improvements.
- **User manual:** installation, operation, configuration and GUI description.
- **Optional 3–5 minute demonstration video.**
- **Automatically generated performance report:** duration, FPS, acquisition time, average/max error, lock retention, processing time and related metrics.

## 14. Evaluation structure

### 14.1 Problem-statement evaluation

| Stage | Weight | What must be demonstrated |
| --- | --- | --- |
| Functional verification | 20% | Mandatory functions, operational success and GUI in a 10–15 minute demonstration. |
| Benchmark Performance-1 | 30% | Scenario execution, centroiding-error log and automatically generated performance logs. |
| Benchmark Performance-2 | 30% | `.mp4` input at 30 fps, comparison with predefined centroiding errors and performance under varying parameters. |
| Technical evaluation | 20% | Problem understanding, architecture, algorithms, AI/CV, innovation, documentation, presentation and Q&A. |

### 14.2 Additional competition evaluation rubric from the supplied image

#### Round 1 — Idea & Design Validation: 50 marks

| Criterion | Marks | What to prepare |
| --- | --- | --- |
| Innovation & Novelty | 10 | Explain what is distinctive: hybrid detector, realistic simulator, adaptive recovery, reproducible evaluation or other defensible contribution. |
| Technical Feasibility & Architecture | 10 | Show modules, data flow, chosen stack, constraints and why the design can meet real-time targets. |
| Approach & Strategy | 10 | Present methodology, milestones, risk controls and execution plan. |
| UI/UX & Product Design | 10 | Show wireframes, operator workflow and usability decisions. |
| Plan & Potential | 10 | Show scope, timeline, deployment path, scalability and future hardware integration. |

#### Round 2 — Prototype & Final Demo: 50 marks

| Criterion | Marks | What to prepare |
| --- | --- | --- |
| Working Prototype & Progress | 10 | Demonstrate completeness, reliability and visible progress. |
| Technical Integration & Performance | 10 | Show integrated modules, code quality, stability and API/backend implementation where relevant. |
| Solution Effectiveness & Demo | 10 | Use live scenarios that directly prove the problem is solved. |
| Usability & UX Realization | 10 | Demonstrate responsive UI and ease of use with minimal operator steps. |
| Team Contribution & Impact | 10 | Present roles, collaboration, quality of presentation and future impact/roadmap. |

### Strategic implication

The project has two simultaneous success definitions:

1. **Engineering pass:** meet the numerical tracking and real-time requirements.
2. **Competition pass:** communicate novelty, feasibility, usability, progress and impact.

A technically strong but opaque demo can lose marks. Build the evaluation dashboard and demo flow from the beginning, not at the end.

## 15. Suggested implementation roadmap

### Milestone 1 — Deterministic simulator

- World canvas, target and camera viewport.
- Straight-line target motion.
- Ground-truth overlays.
- Reproducible seeds.

### Milestone 2 — Baseline closed loop

- Bright-spot detector.
- Centroiding.
- Proportional pan/tilt controller.
- Centre-lock demonstration with no disturbance.

### Milestone 3 — Required trajectories and state machine

- Circular, figure-eight and random motion.
- SEARCHING, ACQUIRING, LOCKED and RE-ACQUIRING states.
- Acquisition, loss and recovery metrics.

### Milestone 4 — Disturbances and robustness

- Noise models, jitter, platform motion and atmospheric presets.
- Prediction/Kalman filter.
- Gain tuning, dead zone and anti-windup if needed.

### Milestone 5 — Benchmark mode and logging

- `.mp4` input adapter.
- Consistent metric definitions.
- CSV/JSON export and summary report.
- Automated test matrix.

### Milestone 6 — AI enhancement and polish

- Add learned candidate validation or motion prediction only if it improves measured performance.
- Final GUI, documentation, packaging and demo rehearsal.

## 16. Key risks and mitigations

| Risk | Consequence | Mitigation |
| --- | --- | --- |
| Threshold detector fails under changing brightness | Missed beacon or false lock | Adaptive threshold, intensity normalization and candidate scoring. |
| Controller overshoots | High error and target loss | Gain tuning, dead zone, derivative damping and speed saturation. |
| Noise creates bright false blobs | Wrong target selected | Shape/area/brightness gates, prediction-based gating and temporal confirmation. |
| Target leaves FOV | Long recovery time | Explicit search pattern, motion prediction and bounded re-acquisition. |
| Synthetic mode works but video mode fails | Benchmark failure | Design a shared frame-source interface and test external videos early. |
| Metrics are ambiguous | Disputed performance | Define formulas, valid-frame policy and stable-lock criteria in the report. |
| Heavy AI model reduces FPS | Fails ≥20 FPS requirement | Prefer lightweight inference or hybrid classical/AI pipeline. |
| GUI consumes processing budget | Poor real-time performance | Separate acquisition, processing, rendering and logging; profile end to end. |
| Random experiments cannot be reproduced | Difficult debugging and comparison | Persist seed, configuration and version with every log. |

## 17. Recommended demo narrative

1. State the FSOC alignment problem in one sentence.
2. Show the clean baseline: target appears, camera acquires and locks.
3. Display the live error and camera motion overlay.
4. Increase noise and platform motion; show that the lock is retained.
5. Force a target loss; show re-acquisition within one second.
6. Switch to an external `.mp4` benchmark and demonstrate bypass mode.
7. Export and open the performance log.
8. Explain the architecture, AI contribution and measured results.
9. Close with hardware-in-the-loop integration as the next step.

## 18. Bottom line

The strongest solution is a **deterministic, measurable, real-time hybrid tracking platform** rather than a black-box detector. Start with a reliable classical beacon detector and constrained feedback controller; add prediction and AI where they improve robustness under noise and occlusion. Make every result reproducible, expose the metrics live, support both synthetic and `.mp4` inputs, and align the product demo directly with both evaluation rubrics.

## 19. Final recommended approach: Adaptive Hybrid EKF–IMM–PID Tracker

### 19.1 Design objective

Use a simple, explainable detector together with three layers of estimation and control:

1. **Adaptive beacon detection** finds candidate bright spots without access to ground truth.
2. **Extended Kalman Filter (EKF)** estimates the beacon’s angular position and motion.
3. **Interacting Multiple Model (IMM)** selects the most suitable motion model as the target changes from straight to accelerating or manoeuvring motion.
4. **PID pan–tilt control** drives the estimated angular error toward zero while respecting camera speed limits.

This architecture is intended to perform consistently across straight-line, circular, figure-eight, random-motion, noisy, jittered, low-contrast and temporary-loss scenarios.

### 19.2 Complete processing loop

```
Frame source
    ↓
Brightness/contrast normalization and denoising
    ↓
Adaptive bright-spot segmentation
    ↓
Connected components and candidate scoring
    ↓
Centroid measurement + confidence
    ↓
IMM of EKFs
    ↓
Fused angular position, velocity and covariance
    ↓
PID pan/tilt controller with saturation and anti-windup
    ↓
Virtual camera update
    ↓
ROI selection, state machine and performance logging
```

The ground-truth position must be available only to the evaluation logger. The detector, EKF, IMM and PID controller must receive image frames and camera-state information only.

## 20. Measurement layer: simple adaptive beacon detector

### 20.1 Preprocessing

For every frame:

1. Convert to grayscale.
2. Apply a small median or Gaussian filter.
3. Normalize local brightness and contrast.
4. Estimate background intensity and noise level.
5. Apply an adaptive threshold rather than a fixed threshold.

A practical threshold is:

```
threshold = local_background + k × estimated_noise
```

Keep `k` configurable and clamp the threshold to a safe range.

### 20.2 Candidate generation

Find connected components or contours in the thresholded image. Reject candidates using:

- minimum and maximum area;
- width and height limits;
- aspect ratio;
- compactness;
- local contrast;
- peak and average brightness;
- distance from the predicted position.

Score each remaining candidate using brightness, shape, expected size, temporal consistency and distance from the IMM prediction.

### 20.3 Centroid measurement

Use the intensity-weighted centroid rather than the bounding-box centre:

```
x_meas = sum(intensity × x) / sum(intensity)
y_meas = sum(intensity × y) / sum(intensity)
```

The detector should return:

```
measurement = [x_meas, y_meas]
confidence = [0, 1]
valid = true or false
```

Use the confidence to adapt the measurement covariance. High confidence produces a small covariance; low confidence produces a large covariance.

## 21. EKF design

### 21.1 Why an EKF is appropriate

A standard Kalman filter is sufficient if tracking is performed entirely in pixel coordinates with a linear motion model. An EKF is justified here because the final controller operates in angular pan/tilt space and the camera projection from angle to pixel location is nonlinear, especially near the edge of the FOV.

### 21.2 State vector

Use a common six-state vector for every IMM model:

```
x = [α, β, α_dot, β_dot, α_ddot, β_ddot]ᵀ
```

where:

- `α` = horizontal angular beacon error relative to the camera optical axis;
- `β` = vertical angular beacon error;
- `α_dot`, `β_dot` = angular velocity;
- `α_ddot`, `β_ddot` = angular acceleration.

The camera pan and tilt rates are known inputs. In a physical system they come from encoders; in the virtual system they come from the camera simulator.

### 21.3 Nonlinear measurement model

For focal lengths `f_x`, `f_y` and principal point `(c_x,c_y)`:

```
u = c_x + f_x × tan(α)
v = c_y + f_y × tan(β)
```

Therefore:

```
z = h(x) = [u, v]ᵀ
```

The EKF linearizes `h(x)` around the current predicted state using its Jacobian. Near the optical axis, this behaves approximately like a linear pixel-to-angle conversion; near the FOV boundary, the nonlinear model is more accurate.

### 21.4 EKF prediction and correction

For each frame:

1. Predict the next state using the selected motion model and timestep.
2. Predict the pixel measurement through the nonlinear projection.
3. Compute the innovation:

```
innovation = measured_pixel - predicted_pixel
```

1. Reject the measurement if the innovation is outside the confidence gate.
2. Otherwise, perform the EKF correction.
3. Increase covariance when measurements are missing.

Use the normalized innovation squared as an additional outlier test. This prevents bright noise blobs from pulling the estimate away from the actual trajectory.

## 22. IMM motion models

The target may move in a straight line, accelerate, follow a circle, follow a figure-eight or change direction randomly. A single motion model will either be too slow to respond or too noisy. Use three simple EKF modes.

### Model 1: Constant velocity — CV

Best for:

- straight-line motion;
- steady target velocity;
- stable tracking periods.

Use low process noise and drive acceleration toward zero.

### Model 2: Constant acceleration — CA

Best for:

- accelerating targets;
- the beginning of circular or figure-eight motion;
- changes in target speed.

Allow acceleration to persist for several frames.

### Model 3: Manoeuvre/high-process-noise — MN

Best for:

- random motion;
- sudden direction changes;
- platform disturbance;
- target motion that does not match CV or CA.

Use larger process noise so the filter can respond quickly, accepting slightly noisier estimates.

A coordinated-turn model may replace MN if circular motion is a primary benchmark requirement, but CV, CA and MN are simpler to implement and usually more robust for mixed trajectories.

### 22.1 IMM operation

At each frame the IMM:

1. Mixes the previous model states according to the model-transition probabilities.
2. Runs one EKF for each model.
3. Calculates each model’s innovation likelihood.
4. Updates the model probabilities.
5. Combines the model states and covariances into one fused estimate.

Example initial transition matrix:

```
[ 0.90  0.08  0.02 ]
[ 0.08  0.90  0.02 ]
[ 0.05  0.10  0.85 ]
```

Rows and columns correspond to CV, CA and MN. Keep the diagonal probabilities high so the system does not switch models unnecessarily. Increase transition probability toward MN when detector residuals or target manoeuvres increase.

The IMM output is:

```
fused_state
fused_covariance
model_probabilities = [P_CV, P_CA, P_MN]
```

Display the model probabilities in the GUI. This makes the tracker explainable during technical evaluation.

## 23. Confidence and loss handling

The estimator must not claim a lock when it is only predicting.

### Measurement available

- Run candidate gating.
- Update all EKF models.
- Update IMM model probabilities.
- Reset or reduce the loss counter.

### Measurement missing briefly

- Run prediction only.
- Increase covariance.
- Keep the last valid model probabilities.
- Continue control at reduced aggressiveness.

### Measurement missing for too long

- Declare the target lost.
- Stop integrating the PID error.
- Enter re-acquisition mode.
- Expand the ROI and begin spiral/raster search.

A practical state policy is:

```
1–3 missed frames      → prediction-only tracking
4–10 missed frames     → TEMPORARILY_LOST
beyond timeout         → RE_ACQUIRING
stable detections       → LOCKED again
```

Tune the thresholds to the actual frame rate and disturbance level.

## 24. PID pan–tilt controller

### 24.1 Control error

Use the fused IMM angular estimate rather than a noisy raw centroid:

```
error_pan  = α_hat
error_tilt = β_hat
```

The desired value for both errors is zero: the beacon should be at the optical axis.

### 24.2 PID law

For each axis:

```
command = Kp × error
        + Ki × integral(error)
        + Kd × derivative(error)
```

Apply the controller independently to pan and tilt, with separate gains.

Recommended practical improvements:

- Use a small dead zone around zero.
- Calculate derivative from the filtered EKF estimate, not raw measurements.
- Clamp the integral term.
- Freeze or reset the integral during target loss.
- Saturate the final command to the maximum pan/tilt speed.
- Apply slew-rate limiting to avoid unrealistic camera jumps.
- Add optional feed-forward from the IMM angular velocity estimate.

A useful implementation is:

```
PID command = feedback PID(error) + feedforward × estimated_angular_velocity
```

The feed-forward term helps the camera follow a moving target without waiting for a large image error to develop.

### 24.3 Controller safety logic

```
if target_confidence is low:
    reduce PID aggressiveness
    freeze integral term

if target_is_lost:
    set PID integral to zero
    disable normal tracking control
    switch to search controller

if command is saturated:
    apply anti-windup
```

This prevents integral wind-up and large overshoot after re-acquisition.

## 25. Search and re-acquisition controller

Use a separate search controller instead of asking the PID to recover a completely lost target.

### Stage 1: local recovery

- Search around the IMM predicted location.
- Increase the ROI size progressively.
- Use a high-process-noise MN model.

### Stage 2: expanding spiral

- Move the virtual camera through an expanding spiral.
- Pause briefly at each search position.
- Use full-frame candidate scoring at each position.

### Stage 3: raster/global scan

- Scan the remaining field of view in horizontal strips.
- Stop immediately after several consecutive valid detections.

This separation improves the re-acquisition-time metric and avoids unstable PID behaviour when the target is not visible.

## 26. Operating modes

### Synthetic-scene mode

- The virtual camera renders the scene.
- The EKF–IMM–PID loop controls the virtual pan/tilt camera.
- Ground truth is logged separately for evaluation.

### External-video mode

- The `.mp4` decoder supplies frames directly to the detector.
- The virtual PTZ renderer is bypassed.
- EKF–IMM still estimates the beacon motion.
- PID commands can be displayed or applied to a virtual viewport if required by the test.
- Measurement and processing metrics are calculated without using hidden annotations.

The detector and estimator should not know which frame source is active.

## 27. Tuning sequence

Do not tune all parameters simultaneously.

### Step 1: detector tuning

Use clean images and verify that the centroid is stable within the target blob.

### Step 2: EKF tuning

Tune measurement covariance using detector noise. Then tune process noise for CV, CA and MN models.

### Step 3: IMM tuning

Start with high self-transition probabilities. Verify that:

- CV dominates straight motion;
- CA becomes more probable during acceleration;
- MN becomes more probable during random or sudden motion.

### Step 4: PID tuning

1. Set `Ki = 0` and `Kd = 0`.
2. Increase `Kp` until the camera responds quickly but does not oscillate.
3. Add `Kd` to reduce overshoot.
4. Add only a small `Ki` if steady-state bias remains.
5. Test saturation and target loss before enabling integral action.

### Step 5: disturbance sweep

Run automated tests across noise, jitter, atmospheric degradation and platform motion. Select parameters using the worst-case benchmark results, not only the clean scenario.

## 28. Recommended acceptance dashboard

Show these values live and write them to the performance log:

- current tracking state;
- raw centroid and fused EKF–IMM estimate;
- current pan/tilt error in pixels and degrees;
- model probabilities for CV, CA and MN;
- acquisition time;
- re-acquisition time;
- lock retention rate;
- target-loss percentage;
- mean error, RMSE, maximum error and P95 error;
- input FPS, processing FPS and frame latency;
- PID commands and saturation count;
- active disturbance settings and random seed.

## 29. Why this final approach is strong

- **Simple detector:** fast and explainable for a beacon spot.
- **EKF:** handles nonlinear camera projection and angular estimation.
- **IMM:** adapts to straight, accelerating and unpredictable motion.
- **PID:** provides familiar, controllable pan/tilt behaviour.
- **Prediction and gating:** reject false blobs and bridge short losses.
- **Separate search controller:** improves recovery instead of overloading PID.
- **Hidden-ground-truth safe:** the tracker uses only observations and known camera state.
- **Benchmark-friendly:** works with both generated scenes and external videos.
- **Real-time capable:** the computationally expensive work is limited to candidate detection; EKF, IMM and PID are lightweight.

## 30. Final implementation rule

Use the following priority order:

```
Reliable measurement first
→ EKF prediction and correction
→ IMM model selection
→ PID control
→ bounded search when confidence falls
→ metrics and logging on every frame
```

Do not allow AI, prediction or control logic to conceal failed detection. A frame is counted as successfully tracked only when a valid image measurement passes the confidence and innovation gates. This keeps the system honest, measurable and suitable for benchmark evaluation.

## 31. Recommended project folder structure

Use a modular **source–tests–configuration–documentation** structure. Keep simulation, perception, estimation, control, evaluation and presentation separate so that each module can be tested independently and the same tracker can process both synthetic frames and external videos.

```
fsoc-virtual-tracker/
│
├── README.md
├── LICENSE
├── pyproject.toml                    # or CMakeLists.txt for C++
├── requirements.txt                  # runtime dependencies
├── requirements-dev.txt              # testing, linting and profiling tools
├── .gitignore
├── .env.example
│
├── src/
│   └── fsoc_tracker/
│       ├── __init__.py
│       ├── main.py                   # application entry point
│       ├── version.py
│       │
│       ├── config/
│       │   ├── schema.py             # configuration validation
│       │   ├── defaults.py           # safe default parameters
│       │   └── loader.py             # YAML/JSON loading and overrides
│       │
│       ├── common/
│       │   ├── types.py              # Frame, Detection, Estimate, Command
│       │   ├── enums.py              # tracking states and source modes
│       │   ├── constants.py
│       │   ├── clock.py              # simulation and real-time clocks
│       │   └── random_state.py       # reproducible random seeds
│       │
│       ├── input/
│       │   ├── base.py               # FrameSource interface
│       │   ├── synthetic_source.py   # frames from virtual scene
│       │   ├── video_source.py       # external .mp4 input
│       │   └── frame_adapter.py      # resize, timing and format handling
│       │
│       ├── simulation/
│       │   ├── world.py              # full virtual environment
│       │   ├── target.py             # beacon geometry and appearance
│       │   ├── trajectories.py       # line, circle, figure-eight, random
│       │   ├── platform_motion.py    # linear and optional disturbances
│       │   ├── virtual_camera.py     # FOV, pan, tilt and projection
│       │   ├── atmosphere.py         # haze, fog, rain and low light
│       │   ├── noise.py              # Gaussian, Poisson, salt-and-pepper
│       │   └── ground_truth.py      # evaluator-only truth; never tracker input
│       │
│       ├── perception/
│       │   ├── preprocess.py         # grayscale, denoise, normalization
│       │   ├── threshold.py          # adaptive thresholding
│       │   ├── candidates.py         # contours and connected components
│       │   ├── scoring.py            # brightness, size and shape scores
│       │   ├── centroid.py           # intensity-weighted centroid
│       │   ├── template_fallback.py  # optional fallback detector
│       │   └── detector.py           # main detector facade
│       │
│       ├── tracking/
│       │   ├── ekf.py                # single Extended Kalman Filter
│       │   ├── motion_models.py      # CV, CA and manoeuvre models
│       │   ├── imm.py                # Interacting Multiple Model filter
│       │   ├── gating.py              # innovation and candidate gates
│       │   ├── confidence.py          # confidence and covariance policy
│       │   ├── state_machine.py      # SEARCH, LOCK, LOST, RECOVERY
│       │   └── tracker.py             # tracking pipeline facade
│       │
│       ├── control/
│       │   ├── pid.py                # pan and tilt PID controllers
│       │   ├── feedforward.py        # optional IMM velocity feed-forward
│       │   ├── saturation.py         # speed and slew-rate limits
│       │   ├── anti_windup.py        # integral protection
│       │   ├── search_controller.py  # spiral and raster re-acquisition
│       │   └── camera_controller.py  # controller facade
│       │
│       ├── evaluation/
│       │   ├── metrics.py            # error, RMSE, loss and lock metrics
│       │   ├── events.py             # acquisition and re-acquisition timing
│       │   ├── benchmark_runner.py   # repeatable scenario execution
│       │   ├── report.py              # CSV, JSON and summary reports
│       │   └── ground_truth_bridge.py # evaluator-only comparison layer
│       │
│       ├── ui/
│       │   ├── app.py                # GUI application shell
│       │   ├── viewport.py           # live frame and overlays
│       │   ├── controls.py           # parameters and experiment controls
│       │   ├── dashboard.py           # metrics and IMM probabilities
│       │   └── plots.py               # live error and FPS plots
│       │
│       └── infrastructure/
│           ├── logging_setup.py      # application and event logging
│           ├── profiling.py          # frame latency and FPS profiling
│           ├── storage.py            # experiment folder management
│           └── exceptions.py         # controlled error handling
│
├── configs/
│   ├── default.yaml
│   ├── clean_baseline.yaml
│   ├── high_noise.yaml
│   ├── platform_jitter.yaml
│   ├── low_light.yaml
│   └── benchmark_video.yaml
│
├── tests/
│   ├── unit/
│   │   ├── test_centroid.py
│   │   ├── test_trajectories.py
│   │   ├── test_projection.py
│   │   ├── test_ekf.py
│   │   ├── test_imm.py
│   │   ├── test_pid.py
│   │   └── test_metrics.py
│   ├── integration/
│   │   ├── test_detector_tracker.py
│   │   ├── test_tracker_controller.py
│   │   └── test_video_pipeline.py
│   ├── scenarios/
│   │   ├── test_straight_motion.py
│   │   ├── test_circular_motion.py
│   │   ├── test_figure_eight.py
│   │   ├── test_random_motion.py
│   │   └── test_reacquisition.py
│   └── fixtures/
│       ├── clean_frames/
│       ├── noisy_frames/
│       └── small_test_videos/
│
├── scripts/
│   ├── run_simulation.py
│   ├── run_video_benchmark.py
│   ├── run_parameter_sweep.py
│   ├── tune_pid.py
│   ├── tune_filter.py
│   └── export_report.py
│
├── data/
│   ├── input_videos/                 # benchmark videos; keep large files external
│   ├── sample_scenarios/
│   └── annotations/                  # only when annotations are officially available
│
├── outputs/
│   ├── runs/                         # timestamped experiment results
│   ├── reports/
│   ├── plots/
│   └── logs/
│
├── docs/
│   ├── architecture.md
│   ├── algorithms.md
│   ├── configuration.md
│   ├── testing.md
│   ├── user_manual.md
│   ├── technical_report.md
│   └── demo_script.md
│
└── models/
    └── README.md                     # optional AI models and model metadata
```

### 31.1 Responsibility of each major layer

| Layer | Responsibility | Must not do |
| --- | --- | --- |
| `input` | Deliver timestamped frames through one common interface. | Detect or track the target. |
| `simulation` | Generate scenes, disturbances and evaluator-only ground truth. | Expose ground truth to the tracker. |
| `perception` | Produce candidate measurements and confidence. | Control the camera. |
| `tracking` | Fuse measurements, predict motion and manage lock state. | Directly update GUI widgets. |
| `control` | Convert estimated angular error into bounded commands. | Decide whether a blob is a valid target. |
| `evaluation` | Calculate metrics and generate reports. | Change tracking decisions using ground truth. |
| `ui` | Display frames, states, controls and metrics. | Contain algorithmic business logic. |
| `infrastructure` | Handle logging, timing, storage and profiling. | Hide failures or silently repair invalid data. |

### 31.2 Important shared data contracts

Define small typed objects in `common/types.py` so modules do not exchange unstructured dictionaries.

```
Frame
  timestamp
  image
  frame_id
  source_name

Detection
  valid
  centroid_px
  bounding_box
  confidence
  candidate_score

Estimate
  position_angle
  velocity_angle
  covariance
  model_probabilities
  tracking_state

ControlCommand
  pan_rate
  tilt_rate
  saturated
  search_mode

MetricsFrame
  error_px
  error_angle
  processing_ms
  fps
  lock_valid
```

This prevents interface drift and makes unit testing straightforward.

### 31.3 Recommended experiment output structure

Every run should create a unique directory, for example:

```
outputs/runs/2026-09-24T153323Z_straight_high_noise_seed42/
├── config_used.yaml
├── run_metadata.json
├── frame_metrics.csv
├── events.json
├── summary_report.json
├── summary_report.html
├── error_plot.png
├── trajectory_plot.png
└── optional_recording.mp4
```

Always save:

- exact configuration;
- software version or commit identifier;
- random seed;
- input source and video properties;
- disturbance settings;
- detector, EKF, IMM and PID parameters;
- start/end time;
- final metrics;
- failure or exception information.

### 31.4 Simplicity rules for implementation

1. Keep one public facade per subsystem: `Detector`, `Tracker`, `CameraController`, `MetricsCollector`.
2. Keep numerical algorithms free of GUI dependencies.
3. Keep ground truth in a separate evaluator-only module.
4. Use the same `FrameSource` interface for synthetic and external video input.
5. Put all tunable parameters in configuration files, not scattered through code.
6. Make every experiment reproducible with a saved seed.
7. Prefer explicit data flow over global variables.
8. Fail loudly on invalid configuration or missing input.
9. Keep generated videos, logs and reports out of version control.
10. Add a unit test before changing EKF, IMM or PID equations.

### 31.5 Minimum viable implementation order

Build the repository in this order:

1. `common/` data contracts and configuration validation.
2. `input/` synthetic and video frame sources.
3. `simulation/` clean beacon and camera viewport.
4. `perception/` adaptive detector and centroiding.
5. `tracking/ekf.py` and one CV model.
6. `control/pid.py` and camera saturation.
7. `tracking/imm.py` with CA and MN models.
8. `control/search_controller.py` and loss recovery.
9. `evaluation/` metrics and automatic reports.
10. `ui/` dashboard and demo polish.

This order keeps the first working prototype small while preserving the final architecture. Each new layer can be benchmarked against the previous one instead of being introduced as one large untestable system.

## 32. Simple and intuitive GUI design

### 32.1 GUI objective

The GUI should allow an evaluator or operator to understand the system within seconds:

- What the camera currently sees.
- Where the beacon is estimated to be.
- Whether the system is searching, acquiring, locked or recovering.
- How accurately it is tracking.
- Whether the camera commands are saturated.
- Which motion model the IMM currently trusts.
- Which disturbances are active.
- How to change parameters without navigating through complex menus.

Use a **single main workspace**, two synchronized visual screens and one clearly labelled **Control Deck** button. Avoid opening many independent windows.

## 33. Main application layout

```
┌─────────────────────────────────────────────────────────────────────────┐
│ FSOC Virtual Camera Tracker   [Synthetic / MP4] [RUN] [PAUSE] [RESET]  │
│ Scenario: High Noise   Seed: 42   State: LOCKED   FPS: 29.8             │
├───────────────────────────────┬─────────────────────────────────────────┤
│ CAMERA FOV                     │ WORLD FOV                               │
│                               │                                         │
│ Live camera image             │ Full virtual scene / world map          │
│ Reticle and beacon overlays   │ Target, camera footprint and boresight  │
│ Pixel error and confidence    │ Platform path and target trajectory     │
│                               │                                         │
├───────────────────────────────┴─────────────────────────────────────────┤
│ LIVE DASHBOARD                                                        │
│ State | Confidence | Error | RMSE | Lock | FPS | PID | IMM probabilities │
├─────────────────────────────────────────────────────────────────────────┤
│ [CONTROL DECK] [EXPORT REPORT] [REPLAY] [SCREENSHOT] [HELP]            │
└─────────────────────────────────────────────────────────────────────────┘
```

### 33.1 Top bar

The top bar must always show:

- application name and software version;
- input mode: `SYNTHETIC` or `MP4`;
- active scenario/preset;
- random seed;
- run state: `IDLE`, `RUNNING`, `PAUSED`, `ERROR`;
- tracking state: `SEARCHING`, `ACQUIRING`, `LOCKED`, `LOST`, `RE-ACQUIRING`;
- `Start`, `Pause`, `Reset` and `Stop` actions.

Use large, unambiguous buttons. Do not hide the emergency stop or reset action inside the settings panel.

## 34. Screen 1 — Camera FOV

The Camera FOV screen represents exactly what the virtual sensor or external video source provides to the tracking algorithm.

### Required overlays

- Live monochrome camera frame.
- Camera image centre reticle.
- Detected centroid, for example, yellow.
- Fused EKF–IMM estimate, for example, green.
- Predicted location, for example, cyan.
- Candidate bounding box or connected component outline.
- Pixel error vector from image centre to beacon estimate.
- Current ROI/search region.
- Confidence score.
- Current state label.
- Optional short trajectory tail showing recent estimated motion.

### Camera FOV controls

- Zoom in/out.
- Fit-to-window.
- Toggle overlays.
- Toggle pixel grid.
- Freeze current frame.
- Save screenshot.
- Show raw, normalized or thresholded image.

The default view should be uncluttered. Advanced overlays should be available through checkboxes rather than shown permanently.

### Camera FOV information strip

Display at the bottom of the screen:

```
Centroid: (x, y) px     Error: (ex, ey) px     Confidence: 0.94
Angular error: (α, β)   State: LOCKED          ROI: 120 × 120 px
```

## 35. Screen 2 — World FOV

The World FOV screen shows the complete virtual environment and explains the relationship between the moving target and the camera viewport.

### Required elements

- Full world boundary, for example, 2000 × 2000 pixels.
- Target position and path history.
- Current virtual camera location.
- Camera FOV footprint or viewport rectangle.
- Camera boresight direction.
- Pan and tilt orientation.
- Platform-motion path.
- Search spiral or raster path during re-acquisition.
- Target trajectory type and direction of motion.

Use a visually distinct camera footprint so the operator can immediately see whether the target is inside or outside the camera FOV.

### Ground-truth protection

The true target marker may be shown in **simulation debug mode** for development, but it must be:

- hidden by default during benchmark operation;
- unavailable to the detector, EKF, IMM and PID modules;
- clearly labelled as `DEBUG ONLY` when enabled;
- disabled automatically in external-video mode.

This preserves the hidden-ground-truth requirement while still making simulator debugging practical.

### World FOV controls

- Pan/zoom world map.
- Centre on camera.
- Centre on target in debug mode only.
- Toggle target path.
- Toggle camera footprint.
- Toggle platform path.
- Toggle search path.
- Show world coordinates and angular orientation.

## 36. Live dashboard

The live dashboard should use compact cards with clear units and colour-coded status.

### Card 1: Tracking state

```
LOCKED
Confidence: 94%
Valid measurement: YES
Missed frames: 0
```

Suggested colours:

- Green: `LOCKED` and healthy.
- Blue: `ACQUIRING` or `SEARCHING`.
- Amber: `TEMPORARILY_LOST` or degraded confidence.
- Red: `FAILED`, invalid input or safety limit exceeded.

### Card 2: Accuracy

```
Current error: 3.4 px
Angular error: 0.021°
Mean error: 4.8 px
RMSE: 6.1 px
P95: 9.3 px
Maximum: 14.7 px
```

### Card 3: Timing and processing

```
Input FPS: 30.0
Processing FPS: 29.8
Frame latency: 8.6 ms
Dropped frames: 0
```

### Card 4: Acquisition and lock

```
Acquisition: 0.84 s
Re-acquisition: 0.43 s
Lock retention: 98.7%
Target loss: 1.3%
```

### Card 5: Estimator status

```
IMM model probabilities
CV: 0.72   CA: 0.18   MN: 0.10
Innovation: 1.8 σ
Covariance: NORMAL
```

### Card 6: Controller status

```
Pan command:  1.8°/s
Tilt command: -0.6°/s
Pan saturation: NO
Tilt saturation: NO
Integral clamp: INACTIVE
```

### Card 7: Active conditions

```
Noise: Gaussian + Poisson
Atmosphere: Haze
Camera jitter: ±8 px/frame
Platform motion: Linear
Seed: 42
```

The dashboard must display both current values and pass/fail thresholds. For example, show `RMSE 6.1 px / limit 10 px` rather than only `RMSE 6.1 px`.

## 37. Control Deck

The **Control Deck** is the main configuration panel. It should open as a right-side drawer or focused modal without closing the two main screens.

Use a tabbed layout with progressive disclosure. Show essential parameters first and place advanced EKF/IMM settings under expandable sections.

```
CONTROL DECK
├── Presets & Run
├── Target
├── Camera
├── Estimator & Controller
├── Environment
├── Disturbances
└── Input, Logging & Display
```

### 37.1 Presets & Run tab

Controls:

- Preset selector: `Clean`, `High Noise`, `Low Light`, `Platform Jitter`, `Video Benchmark`.
- Load preset.
- Save current configuration.
- Restore safe defaults.
- Random seed.
- Simulation duration.
- Start, pause, reset and stop.
- Record video.
- Export configuration and results.

Show a concise summary before starting:

```
640 × 480 | FOV 4° × 3° | 30 FPS | Gaussian noise | CV/CA/MN | PID enabled
```

### 37.2 Target tab

Required parameters:

- Number of targets.
- Target type: beacon spot.
- Shape: square or user-defined.
- Width and height.
- Intensity/brightness.
- Initial position: centre, random, manual coordinates.
- Motion type: straight, circular, figure-eight or random.
- Optional spiral, sinusoidal or custom trajectory.
- Target speed.
- Acceleration or turn rate.
- Visibility schedule for forced-loss tests.

Validate target size and speed immediately. Show units and acceptable ranges beside every field.

### 37.3 Camera tab

Required parameters:

- Resolution.
- Screen/world size.
- Horizontal and vertical FOV.
- Camera update rate.
- Initial pan and tilt.
- Maximum pan speed.
- Maximum tilt speed.
- Camera jitter amplitude.
- Monochrome/colour mode if supported.
- Display scale and viewport zoom.

Show a small preview of the resulting camera footprint in the World FOV screen.

### 37.4 Estimator & Controller tab

#### EKF settings

- State model selection.
- Initial state covariance.
- Measurement covariance.
- Process-noise scale.
- Innovation gate threshold.
- Prediction-only timeout.

#### IMM settings

- Enable/disable IMM for controlled comparisons.
- Models: CV, CA, MN.
- Model-transition matrix.
- Initial model probabilities.
- Minimum model probability.
- High-manoeuvre process-noise scale.

#### PID settings

- Pan `Kp`, `Ki`, `Kd`.
- Tilt `Kp`, `Ki`, `Kd`.
- Dead-zone width.
- Integral limit.
- Anti-windup mode.
- Derivative filter coefficient.
- Velocity feed-forward gain.
- Maximum command and slew-rate limits.

Every parameter should include a tooltip explaining its effect. For example:

```
Kp: increases response speed but too much may cause oscillation.
Ki: removes steady-state bias but can wind up during target loss.
Kd: reduces overshoot but may amplify noisy measurements.
```

### 37.5 Environment tab

Controls:

- World width and height.
- Background type and brightness.
- Target and platform initial conditions.
- Platform motion type: linear, circular, random, spiral or figure-eight.
- Platform speed and maximum displacement.
- Simulation time scale.
- Coordinate-grid visibility.
- Deterministic/realtime execution mode.

### 37.6 Disturbances tab

Use independent enable switches and severity sliders for:

- Salt-and-pepper noise and percentage of affected pixels.
- Gaussian noise and standard deviation.
- Poisson noise strength.
- Camera jitter in pixels per frame.
- Blur or turbulence strength.
- Haze.
- Fog.
- Rain.
- Low-light brightness reduction.
- Contrast reduction.
- Platform motion.

Show a small live preview of the disturbance effect before starting. Prevent invalid combinations and warn when the selected settings exceed the benchmark envelope.

### 37.7 Input, Logging & Display tab

Controls:

- Input source: synthetic scene or `.mp4`.
- Video path and frame range.
- Native-FPS processing or maximum-speed processing.
- Image-centre calibration.
- Output directory.
- CSV/JSON/HTML report selection.
- Frame recording.
- Overlay visibility.
- Ground-truth debug switch, disabled automatically for benchmark mode.
- Log level: normal, detailed or diagnostic.

## 38. GUI interaction rules

1. **One-click start:** the operator should be able to select a preset and begin a run immediately.
2. **Safe defaults:** every new experiment starts with validated parameters.
3. **Apply/Cancel:** Control Deck edits are staged until `Apply` is clicked.
4. **Lock during run:** parameters that would invalidate a run become read-only while running.
5. **Clear units:** always show `px`, `px/frame`, `°`, `°/s`, `Hz`, `FPS`, `ms` or `%`.
6. **Inline validation:** invalid values are highlighted beside the field, not reported only after starting.
7. **Tooltips:** explain technical parameters in plain language.
8. **Preset protection:** never overwrite a preset without explicit confirmation.
9. **Reset visibility:** provide both `Reset View` and `Reset Parameters` so they are not confused.
10. **No hidden state:** always display the active configuration, seed and input source.

## 39. GUI state and colour language

Use the same colours everywhere:

| Meaning | Colour | Use |
| --- | --- | --- |
| Healthy lock | Green | Locked state, valid measurement, passing metric |
| Active estimate | Cyan | EKF/IMM prediction or fused estimate |
| Raw detection | Yellow | Detector centroid and candidate |
| Search/acquisition | Blue | Camera scanning or acquiring |
| Warning/degraded | Amber | Low confidence, missed frames or saturation |
| Failure | Red | Lost target, invalid input or benchmark failure |
| Ground truth | Magenta, debug only | Simulator truth marker; never shown by default |

The same state colours must appear in the top bar, Camera FOV overlay, World FOV camera marker and dashboard cards.

## 40. Recommended operator workflow

1. Open the application; the default preset is shown.
2. Select `Synthetic` or `MP4` input.
3. Open **Control Deck** and confirm target, camera, estimator, controller and disturbance settings.
4. Click `Apply` and review the configuration summary.
5. Click `Start`.
6. Watch the Camera FOV for acquisition and the World FOV for camera/target geometry.
7. Use the live dashboard to verify error, FPS, lock retention and IMM mode probabilities.
8. Increase disturbance severity or trigger target loss for recovery testing.
9. Click `Stop` or wait for completion.
10. Export the automatic report and configuration used.

The operator should never need to inspect internal logs during the normal demo.

## 41. GUI-to-code folder alignment

Extend the `ui/` portion of the project structure as follows:

```
src/fsoc_tracker/ui/
├── app.py                    # application shell and event loop
├── theme.py                 # colours, typography and status styles
├── layout.py                # main two-screen layout
├── camera_fov_view.py       # Camera FOV rendering and overlays
├── world_fov_view.py        # World FOV map and camera footprint
├── live_dashboard.py        # metric cards and status indicators
├── control_deck/
│   ├── __init__.py
│   ├── panel.py              # drawer/modal shell
│   ├── presets_tab.py
│   ├── target_tab.py
│   ├── camera_tab.py
│   ├── estimator_controller_tab.py
│   ├── environment_tab.py
│   ├── disturbances_tab.py
│   └── input_logging_tab.py
├── overlays.py               # reticles, vectors, labels and paths
├── plots.py                  # live error, FPS and model-probability plots
└── ui_state.py               # selected tab, toggles and display state
```

The UI should consume read-only `Estimate`, `ControlCommand`, `MetricsFrame` and configuration snapshots. It must not modify EKF, IMM, PID or ground-truth state directly.

## 42. GUI acceptance checklist

The GUI is ready for demonstration when:

- both Camera FOV and World FOV screens update smoothly;
- the beacon, prediction, camera footprint and state are visible;
- the dashboard updates at least once per processed frame or at a stable display rate;
- the Control Deck configures all required parameters;
- invalid inputs are caught before a run begins;
- the active seed and configuration are visible;
- synthetic and `.mp4` modes use the same main tracking workflow;
- ground truth is hidden in benchmark mode;
- target loss and re-acquisition are visually obvious;
- the performance report can be exported without manual data collection;
- the interface remains usable at the required processing rate.