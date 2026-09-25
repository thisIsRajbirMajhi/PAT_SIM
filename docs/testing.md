# Testing Methodology — FSOC Virtual Camera Tracking PAT Simulator

> **Scope:** Unit, integration, scenario, disturbance, video-benchmark, stress and robustness testing. All tests are repeatable via fixed seeds and validated against spec thresholds: acquisition <= 2 s, re-acquisition <= 1 s, RMSE <= 10 px, loss < 5 %, FPS >= 20.

---

## 1. Test Philosophy

1. **Deterministic first:** every test uses a fixed `seed` and saves `config_used.yaml` so results are replayable.
2. **Ground-truth separation:** tests assert that `perception`, `tracking`, `control` never import or access `simulation/ground_truth.py`; only `evaluation/metrics.py` may compare against truth.
3. **Layered verification:** unit -> controlled integration -> disturbance -> video benchmark -> stress/usability (Implementation Plan section 12).
4. **Threshold-driven:** pass/fail is defined numerically against spec limits, not subjectively.

### Metrics and Definitions (used in all tests)

```
Let g_t = ground-truth image position, p_t = estimated (or detected) position
d_t = ||p_t - g_t||_2                           # per-frame Euclidean error (px)

mean(d)          = mean(d_t) over valid frames
RMSE            = sqrt(mean(d_t^2))
max(d)           = max(d_t)
P95              = 95th percentile of d_t
lock_retention   = locked_frames / total_frames * 100
target_loss_pct  = frames_without_valid_lock / total_frames * 100
                (loss counted per TrackingState; LOCKED/ACQUIRING are lock)
acquisition_time = elapsed from start until first stable LOCKED (>=5 consecutive valid)
reacq_time       = elapsed from LOST until stable LOCKED restored
FPS (end-to-end) = total_frames / duration_s     # also rolling fps and processing_ms
saturation_count = frames where |pan|==max_pan or |tilt|==max_tilt
```

Valid frames: `Detection.valid==True` and `GroundTruth.image_pos != None`; all frames count toward loss/fps. All definitions match `evaluation/metrics.py:MetricsCollector.summary()`.

---

## 2. Test Structure

```
tests/ (recommended — see Implementation Plan section 31)
+-- unit/
|   +-- test_centroid.py          # intensity-weighted centroid accuracy
|   +-- test_trajectories.py       # 7 trajectory equations, bounce, bounds
|   +-- test_projection.py         # world<->image<->angle, px_per_deg, clamp
|   +-- test_ekf.py                # predict/update, NIS gating, confidence scaling
|   +-- test_imm.py                # transition, likelihood, fuse, clamp
|   +-- test_pid.py                # deadzone, saturation, anti-windup, search spiral
|   +-- test_metrics.py            # error formulas, acquisition/reacq timing
|   +-- test_noise.py              # Gaussian/S&P/Poisson/jitter/atmosphere bounds
|   +-- test_config.py             # validate_config rejects out-of-spec values
+-- integration/
|   +-- test_detector_tracker.py   # detector -> tracker -> estimate closes under clean
|   +-- test_tracker_controller.py # estimate -> command drives camera to centre
|   +-- test_video_pipeline.py     # VideoFileSource -> same detector/metrics pipeline
+-- scenarios/
|   +-- test_straight_motion.py
|   +-- test_circular_motion.py
|   +-- test_figure_eight.py
|   +-- test_random_motion.py
|   +-- test_reacquisition.py      # forced loss + timed recovery
+-- fixtures/
    +-- clean_frames/
    +-- noisy_frames/
    +-- small_test_videos/         # 640x480 30fps clips for video benchmark tests
```

Actual headless regression is driven by `Benchmark Dialog` and by `MetricsCollector` summaries in `outputs/runs/`.

---

## 3. Unit Tests (Phase A)

### 3.1 Coordinate Conversion and Projection

| Test | Input | Expected | Assertion |
|------|-------|----------|-----------|
| `test_world_to_image_centre` | `world_pos = (1000,1000)`, `VirtualCamera` at centre | image_pos `(320,240)` +- 0.5 px | `world_to_image` |
| `test_image_to_angle_centre` | `(320,240)` | `(0,0) deg` | `image_to_angle_error` |
| `test_angle_roundtrip` | `alpha=1.2, beta=-0.8` deg | `angle_to_image -> image_to_angle` recovers within 1e-4 | `angle_to_image` inv |
| `test_fov_to_pixel` | `HFOV=4, W=640` | `ex=320 -> alpha=2 deg`, `ex=1 -> 0.00625 deg` | scaling |
| `test_viewport_clamp` | `pan=100 deg` | viewport centre clamped to `W-world_w` bounds, pan synced | `apply_command` + `_update_center` |
| `test_extract_viewport_size` | world 2000x2000, cam 640x480 | crop exactly 640x480, resized if mismatched | `extract_viewport` |

```python
# Example: projection unit test
def test_image_to_angle_centre():
    from fsoc_tracker.simulation.virtual_camera import VirtualCamera
    cam = VirtualCamera(world_size=(2000,2000), resolution=(640,480), fov_deg=(4,3), max_pan_speed=5, max_tilt_speed=5)
    assert cam.image_to_angle_error((320,240)) == (0.0, 0.0)
    alpha, beta = cam.image_to_angle_error((640,240))  # right edge
    assert 1.9 < alpha < 2.1
```

### 3.2 Pan/Tilt Sign Convention

Verify that moving the beacon to positive `x` (right) yields `alpha>0` and pan command is negative (or documented sign), and tilt inverts `y`. Calibration scene: beacon at known offset, assert controller sign moves camera toward it.

### 3.3 Speed Saturation and Timestep

| Test | Condition | Expected |
|------|-----------|----------|
| `test_pid_saturation` | `Kp*error = 12` with `max_pan=5` | command clipped to 5, `saturated=True` |
| `test_pid_dt_scaling` | `dt=1/30 vs 1/60` | integral `+= error*dt` scales correctly |
| `test_virtual_camera_clamp` | `tilt_rate=20` | `apply_command` clips to `max_tilt_speed` |

### 3.4 Target Trajectory Equations

For each trajectory class, step 0..T and assert:

- Positions stay within `[50, W-50]x[50, H-50]` (bounce bounds).
- Circular radius stays within `r +- 1 px`.
- Random `step(t)` and `step(t+1)` differ by `~speed +- 3 sigma`.
- Straight with angle 0 moves only in +x.

```python
def test_circular_radius():
    from fsoc_tracker.simulation.trajectories import CircularTrajectory
    traj = CircularTrajectory(center=(1000,1000), radius=200, speed_px_per_frame=3.0)
    for t in range(300):
        x,y = traj.step(t)
        assert abs(((x-1000)**2+(y-1000)**2)**0.5 - 200) < 1.2
```

### 3.5 Noise Generators and Severity Bounds

| Test | Config | Check |
|------|--------|-------|
| `test_gaussian_std_bound` | `gaussian_std=20` | output in [0,255], distortion present |
| `test_salt_pepper_prob` | `prob=0.04`, 640x480 -> ~12288 affected | count of pure 0/255 within 20% of expected |
| `test_poisson_range` | `poisson=True` | output uint8 [0,255] |
| `test_jitter_max` | `jitter=20` | shift `dx,dy in [-20,20]` |
| `test_atmosphere_strength` | `haze strength 0/0.5/1.0` | monotonic contrast reduction |

### 3.6 Centroid Calculation

Generate a synthetic patch: square beacon 10x10, intensity 255 on background 18, with Gaussian blur 3. Assert `BeaconDetector.detect` returns centroid within 0.6 px of true centre, confidence > 0.6, area within 20% of 100.

### 3.7 Metric Formulas and Event Timing

```python
def test_metrics_formulas():
    from fsoc_tracker.evaluation.metrics import MetricsCollector
    m = MetricsCollector()
    m.start_run()
    for err in [2.0, 4.0, 4.0]:
        m.errors.append(err)
    s = m.summary()
    assert abs(s["mean_error_px"] - 3.333) < 0.01
    assert abs(s["rmse_px"] - ( (4+16+16)/3 )**0.5) < 0.01

def test_acquisition_timing():
    # feed frames: 20 SEARCHING, then LOCKED — assert acquisition_time ~ 20/fps
    ...
```

### 3.8 Config Validation

`validate_config` must accept `default.yaml` and reject out-of-range values (e.g., `gaussian_std=21`, `jitter=21`, `size=4`, `fov=0.5`). Tests cover both positive and negative paths.

---

## 4. Controlled Integration Tests (Phase B)

### 4.1 Static Target, No Noise

- Target fixed at centre, platform none, all disturbances off.
- Expect `LOCKED` within 10 frames, RMSE < 1 px, no saturation, P95 < 2 px.

### 4.2 Each Mandatory Trajectory

| Trajectory | Speed | Platform | Disturbance | Pass Criteria |
|------------|-------|----------|-------------|---------------|
| straight (30 deg) | 3.0 | none | none | acq <= 2 s, RMSE <= 5 px, loss 0% |
| circular (r=180) | 2.8 | none | none | RMSE <= 6 px, IMM CA rises |
| figure_eight (r=350) | 2.8 | none | none | RMSE <= 7 px |
| random | 3.5 | none | none | RMSE <= 8 px, MN spikes, reacq <= 1 s if loss |

### 4.3 Edge Initialization

Target starting at FOV edge and at corner; camera at centre. Verify bounded acquisition (SEARCH -> CANDIDATE -> LOCKED) without overshoot.

### 4.4 Controller Gain Sweep

Sweep `Kp in [0.4, 0.8, 1.2, 1.8]`, `Kd in [0, 0.15, 0.3]` on straight motion, record RMSE and saturation count. Select params minimizing `RMSE + 0.1*saturation`.

### 4.5 Target Speed Sweep

Speeds `[1, 3, 6, 10, 15]` px/frame; with `max_pan=5` (~ 11 px/frame at 30 Hz) expect graceful degradation beyond ~10 px/frame: RMSE grows, loss appears, but re-acquisition logic keeps `reacq <= 1 s`.

---

## 5. Disturbance Tests (Phase C)

Run a matrix with **fixed seeds** (e.g., 42 and 1337), repeated 3 trials each, reporting mean and 95% CI.

| Matrix | Variables | Baseline |
|--------|-----------|----------|
| Noise isolate | Gaussian std 0/5/20; S&P 0/0.02/0.04; Poisson on/off | speed 3, straight |
| Combined noise | low (5,0.01,off), med (10,0.02,on), max (20,0.04,on) | same |
| Jitter | 0, 8, 20 px/frame | Gaussian 0 |
| Atmosphere | clear, haze 0.35, fog 0.5, rain 0.35, low_light 0.5 | same |
| Platform | none, linear 4, circular 4, random 4, figure_8 4 | speed 12 for stress variant |
| Speed x disturbance | speed 3 vs 8 crossed with haze 0 vs 0.35 | — |
| Edge cases | beacon at edge, temporarily outside FOV, size 5 vs 20, multi-target count 3 | — |

**Example automated matrix runner:**

```python
# pseudo — mirrors Benchmark Dialog logic
import itertools
from fsoc_tracker.config.loader import load_config
from fsoc_tracker.evaluation.metrics import MetricsCollector

cases = list(itertools.product(
    [0, 14],          # gaussian_std
    [0, 0.04],        # s_p
    ["clear","haze"], # atmosphere
    [0, 8],           # jitter
))
for std, sp, atmo, jit in cases:
    cfg = load_config("configs/presets/classical_baseline.yaml")
    cfg["noise"]["gaussian_std"] = std
    cfg["noise"]["salt_pepper_prob"] = sp
    cfg["atmosphere"]["type"] = atmo
    cfg["camera"]["jitter_px"] = jit
    cfg["experiment"]["seed"] = 42
    # run 600 frames headless, collect MetricsCollector.summary()
    # assert summary["rmse_px"] <= 10 or record degradation curve
```

Acceptance per cell: if `rmse>10` or `loss>=5` the cell is flagged; the worst-case curve (not just clean) drives tuning. Curated operating points live under `configs/presets/`; detailed cells remain in `configs/benchmarks/`.

### 5.1 Expected Behaviour Under Disturbances

- **AI — Robustness** (moderate Gaussian/S&P/ Poisson noise, jitter, haze, and platform motion) should exercise the identity safety path without a false primary lock.
- The detailed P01–P12 disturbance cells remain in `configs/benchmarks/` and are run by the headless regression suite.
- Beyond max envelope (e.g., `gaussian 20 + fog 0.7 + jitter 20` simultaneously) loss will exceed 5% — correctly exposing the operating boundary.
- IMM `P_MN` should dominate in random/jitter/platform cells; `P_CV` in straight/clean cells. Dashboard logs verify.

---

## 6. Video Benchmark Tests (Phase D)

Benchmark Performance-2 uses evaluator `.mp4` at **30 fps** containing noise and a moving beacon. The `VideoFileSource` bypasses PTZ.

| Test | Action | Check |
|------|--------|-------|
| Different resolutions | 640x480 native, 1280x720 downscaled/letterboxed | detector handles native res; metrics scale accordingly, no silent stretch that changes error scale |
| 30 fps ingestion | play 10 s clip | `input_fps=30`, `processing_fps >= 20`, `dropped ~ 0`, frame order preserved |
| Reference error comparison | compare `MetricsCollector.errors` vs evaluator-provided `reference_error.csv` if available | mean difference < 1 px or documented bias |
| Occlusion / exit FOV | clip where beacon leaves frame for 0.5 s | state goes REACQUIRING, re-locks within 1 s on return, loss counted correctly |
| Codec handling | H.264 mp4 with/without spaces in path | `VideoFileSource` opens or shows actionable error, no crash |
| Log generation | any video run with valid path | `outputs/runs/.../config_used.yaml`, `frame_metrics.csv`, `events.json`, `summary_report.{json,html}` produced automatically |

```python
# src/fsoc_tracker/input/video_source.py (existing) — tested interface
from fsoc_tracker.input.video_source import VideoFileSource
src = VideoFileSource(path="data/benchmark.mp4", cfg=cfg)
frame = src.read()
assert frame is not None and frame.image.shape[0] > 0
# downstream is identical:
det = BeaconDetector(cfg).detect(frame.image)
est = Tracker(cfg).step(det, frame)
```

---

## 7. Stress and Usability Tests (Phase E)

| Area | Test | Pass |
|------|------|------|
| Long-duration | 10 min synthetic random 4.5 + jitter 12, seed 99 | no memory leak, error drift < 1 px, FPS stable |
| Maximum disturbance | `gaussian 20 + s_p 0.04 + poisson + jitter 20 + fog 0.6 + platform 20` | system stays in REACQUIRING/SEARCHING without crash; logs complete |
| Multiple targets | `count=3`, random distractors | tracker follows primary (seed 42); loss < 10 % (higher clutter acceptable) |
| Start/stop/reset/replay | Rapid RUN/PAUSE/RESET/seed change mid-run | state machine resets, trajectories regenerate correctly, no stale estimates |
| Malformed input | missing `video_path`, corrupt mp4, `size=4` (invalid) | `validate_config` or `VideoFileSource` shows error dialog; app stays alive |
| Exported log inspection | any 30 s run, EXPORT REPORT | JSON valid, HTML renders, CSV row count == `total_frames`, events monotonic |
| Performance regression | headless 600 frames, clean | `avg_processing_ms < 33` (30 fps budget) and `e2e_fps >= 20` on reference laptop |

---

## 8. Test Execution and Automation

### 8.1 Running Tests

```bash
# Unit tests (when pytest present)
pytest tests/unit -v
pytest tests/integration -v

# Headless scenario matrix via UI
python -m fsoc_tracker.main  # -> BENCHMARK DIALOG -> select cases -> Run

# Manual
python src/fsoc_tracker/main.py  # observe dashboard thresholds live (green/red)
```

### 8.2 Continuous Metrics

`MetricsCollector.summary()` is the single source of pass/fail. Thresholds from `common/constants.py` are shown live vs limits (`RMSE 6.1 / 10 px`), so a human demo and an automated log apply the same rules.

### 8.3 Reproducibility Checklist (per run)

- [ ] `config_used.yaml` saved with full resolved config
- [ ] `run_metadata.json` contains seed, version/commit, input source, video properties, disturbance settings
- [ ] `frame_metrics.csv` row per frame (monotonic `frame_id`, `timestamp`)
- [ ] `events.json` records `SEARCHING->CANDIDATE->LOCKED`, `LOCKED->TEMP_LOST`, `REACQUIRING->LOCKED` with timestamps and reacq durations
- [ ] Software version from `version.py` logged
- [ ] Random seed alone suffices to replay the trajectory + noise sequence

---

## 9. Pass/Fail Summary Template

Every scenario cell produces a row like:

| Scenario | Seed | Acq (s) | Re-acq mean (s) | RMSE (px) | Mean (px) | Max (px) | P95 (px) | Loss % | Lock % | FPS | Valid det % | Result |
|----------|------|---------|----------------|-----------|-----------|----------|----------|--------|--------|-----|-------------|--------|
| straight clean | 42 | 0.6 | — | 3.1 | 2.4 | 7.2 | 5.1 | 0.0 | 99.2 | 29.3 | 99.0 | PASS |
| random + high_noise | 42 | 0.9 | 0.6 | 6.8 | 5.2 | 18.4 | 10.2 | 1.8 | 96.1 | 28.1 | 93.0 | PASS |
| circular + fog 0.5 | 42 | 1.1 | 0.7 | 8.9 | 7.1 | 22.0 | 13.5 | 3.9 | 92.0 | 27.4 | 89.0 | PASS (flag P95) |

Flagging `P95 > 10` even when `RMSE < 10` is recommended to avoid ambiguity (Implementation Plan section 9.2).

---

## 10. References

- Implementation Plan.md section 9 (metrics definitions), section 12 (testing plan)
- `src/fsoc_tracker/evaluation/metrics.py`, `common/constants.py`
- `src/fsoc_tracker/config/schema.py` for acceptance bounds
