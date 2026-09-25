# Configuration Guide — FSOC Virtual Camera Tracking PAT Simulator

> All tunable parameters live in `configs/` and `src/fsoc_tracker/config/defaults.py`. They are validated by `config/schema.py` and editable at runtime via the Control Deck drawer. The GUI reads curated files from `configs/presets/`; detailed regression scenarios live separately in `configs/benchmarks/`.

---

## 1. Configuration Files

| File | Purpose |
|------|---------|
| `configs/presets/*.yaml` | Four curated Control Deck presets; each declares `preset_meta.system` (`ai` or `deterministic`) and `preset_meta.ai_mode` (`ON` or `OFF`). |
| `configs/benchmarks/P*.yaml` | Detailed P01–P12 benchmark/regression scenarios; not shown in the GUI selector. |
| `src/fsoc_tracker/config/defaults.py` | `DEFAULT_CONFIG` dict — single source of truth for defaults, limits and types. |
| `src/fsoc_tracker/config/schema.py` | `validate_config()` — asserts spec ranges, fails fast. |
| `src/fsoc_tracker/config/loader.py` | Loads YAML, deep-merges with `DEFAULT_CONFIG`. |
| `src/fsoc_tracker/config/presets.py` | Discovers curated GUI presets independently of other YAML files. |

**Overlay pattern:** any YAML may contain only the keys to override; missing keys fall back to `DEFAULT_CONFIG`. Curated presets include explicit metadata so the Control Deck can explain their AI mode and purpose. For example, `configs/presets/03_ai_robustness.yaml` uses:

```yaml
ai: {enabled: true}
camera: {jitter_px: 2.0}
noise: {gaussian_enabled: true, gaussian_std: 5.0, salt_pepper_enabled: true, salt_pepper_prob: 0.01, poisson: true}
atmosphere: {type: haze, strength: 0.15}
```

---

## 2. Full Parameter Reference — Sr. Requirements 1-15 and Disturbances

Spec references: Implementation Plan section 4 and Detailed Requirements.pdf acceptance targets.

### 2.1 Sr.1-7 — Scene and Camera

| Sr. | Parameter | Key (`cfg[...]`) | Spec / Reference | Default | Allowed Range | Notes |
|-----|-----------|-----------------|-----------------|---------|---------------|-------|
| 1 | Screen / World size | `world.width`, `world.height` | Min 2000x2000 | 2000, 2000 | 2000-4000 each (validated; 1000-4000 supported for debug) | World canvas > camera viewport. `background` (Sr.1b) 0-80, default 18. |
| 2 | Camera type | `camera.type` | Monochrome focal-plane array | `monochrome` | `monochrome` / `colour` | VIDEO BGR auto-converted; colour mode optional. |
| 3 | Camera resolution | `camera.resolution` | 640x480 | `[640,480]` | W 320-1920, H 240-1080 | Larger -> more detail but ~W*H cost for detector. |
| 4 | Field of view | `camera.fov_deg` | Default 4 deg x 3 deg | `[4.0, 3.0]` | 1-12 deg each | Pixel-to-angle: `alpha = ex * HFOV/W`. Jointly tuned with `px_per_deg=220`. |
| 5 | Camera update rate | `camera.fps`, `camera.update_interval_hz` | At least 30 Hz camera, >= 20 Hz control | 30.0, 30.0 | 30-60 Hz camera, 20-60 Hz control | `dt = 1/fps` drives EKF and PID. 30 fps required for benchmark video. |
| 6 | Initial camera position | `camera.initial_position`, `initial_pan/tilt` | Screen centre | `centre`, 0, 0 | `centre` / `user-defined` with pan/tilt deg | Centre gives deterministic repeatability; user-defined pan/tilt in degrees. |
| 7 | Target type | `target.type` | Beacon spot | `beacon_spot` | `beacon_spot` | Bright localized source. |

### 2.2 Sr.8-12 — Target

| Sr. | Parameter | Key | Spec / Reference | Default | Allowed Range | Notes |
|-----|-----------|-----|-----------------|---------|---------------|-------|
| 8 | Number of targets | `target.count` | 1 mandatory | 1 | 1-5 | >1 creates independent trajectories (distractors with 0.7-1.3x speed, seed+1009). |
| 9 | Target shape | `target.shape` | Default square | `square` | `square` / `circle` / `gaussian` / `cross` / `user-defined` | `user-defined` uses `custom_polygon` (list of [dx,dy]) or fallback 5-point star. |
| 10 | Target size | `target.size` | 5-20 px per side, default 10 | 10 | 5-20 | Width/height or diameter; glow radius +2 px. |
| 11 | Initial target location | `target.initial_pos`, `initial_mode` | User-defined; default random | `None` / `random` | `None` means random 400..W-400 via seed; else `[x,y]` in world; modes `random`/`centre`/`user-defined` | Seed logs guarantee replay. |
| 12 | Target motion / Trajectory | `target.trajectory` | Straight, circular, figure-eight, random mandatory | `circular` | `straight` / `circular` / `figure_eight` / `random` / `spiral` / `sinusoidal` / `user-defined` | `user-defined` loads `custom_trajectory_file` CSV (`x,y` or `t,x,y`). |

**Sr.12 sub-parameters:**

| Key | Applies To | Default | Range | Description |
|-----|-----------|---------|-------|-------------|
| `speed_px_per_frame` | all | 2.8 | 0-20 | Linear speed per frame at 30 fps ( => ~84 px/s at 2.8). |
| `angle_deg` | straight | 30 | 0-360 | Direction angle. |
| `radius` | circular, figure-8 | 180 / 350 | 50-800 | Orbit radius. |
| `custom_trajectory_file` | user-defined | `null` | path string | CSV with coordinates per frame. |
| `intensity` | all | 255 | 0-255 | Beacon core brightness. |
| `custom_polygon` | user-defined shape | `null` | list of [dx,dy] | Normalized polygon offsets (scaled by half-size). |

### 2.3 Sr.13-14 — Camera Motion Limits

| Sr. | Parameter | Key | Spec / Reference | Default | Allowed Range | Notes |
|-----|-----------|-----|-----------------|---------|---------------|-------|
| 13 | Max pan speed | `camera.max_pan_speed` | Default 5 deg/s; user 5-10 deg/s (UI allows 1-15 for tuning) | 5.0 | 1-15 (spec 5-10, warn outside) | Clamps `pan_rate`; `apply_command` enforces. |
| 14 | Max tilt speed | `camera.max_tilt_speed` | Same | 5.0 | 1-15 | Independent limits. |

### 2.4 Sr.15 — Performance Thresholds (read-only in config, enforced in metrics)

| Parameter | Threshold | Config constant (`common/constants.py`) | How reported |
|-----------|-----------|------------------------------------------|-------------|
| Acquisition time | <= 2 s | `ACQUISITION_TIME_LIMIT = 2.0` | Time from start to first stable LOCKED (>=5 consecutive). Dashboard card + `summary_report`. |
| Re-acquisition time | <= 1 s | `REACQUISITION_TIME_LIMIT = 1.0` | Per loss event; mean/max; spiral search ensures ~0.4-0.8 s. |
| Tracking error (RMSE / mean / P95) | <= 10 px | `TRACKING_ERROR_LIMIT_PX = 10.0` | Per-frame ||est-gt||; report mean, RMSE, max, P95. |
| Target loss | < 5 % | `TARGET_LOSS_LIMIT_PCT = 5.0` | `100*(1 - locked/total)`. |
| Processing speed | >= 20 FPS (end-to-end) | `MIN_PROCESSING_FPS = 20.0` | `total_frames / duration` and rolling `fps`. Camera 30 Hz target. |

---

## 3. Disturbances and Environment

### 3.1 Noise

| Key | Type | Default | Range | Effect |
|-----|------|---------|-------|--------|
| `noise.gaussian_enabled` | bool | `false` | — | Enable Gaussian noise. |
| `noise.gaussian_std` | float | 0.0 | 0-20 | Standard deviation (px). Max 20 per spec; impl uses `rng.normal(0,std)`. |
| `noise.salt_pepper_enabled` | bool | `false` | — | Enable S&P. |
| `noise.salt_pepper_prob` | float | 0.0 | 0-0.15 (spec ~0.10 at max) | Fraction of pixels set to 0/255 each frame (`num=prob*H*W`). |
| `noise.poisson` | bool | `false` | true/false | Photon shot noise; scales image/255*30, `rng.poisson`. |

Noise pipeline order: Gaussian -> Poisson -> S&P -> jitter applied after atmosphere. All can be enabled simultaneously.

### 3.2 Atmosphere

| Key | Values | Default | Range | Model |
|-----|--------|---------|-------|-------|
| `atmosphere.type` | `clear`/`haze`/`fog`/`rain`/`low_light` | `clear` | enum | Haze/fog: contrast veil + Gaussian blur; rain: vertical streaks; low_light: multiplicative darken. |
| `atmosphere.strength` | float | 0.0 | 0-1 | 0 = none, 1 = severe. |

```python
# noise.py apply_atmosphere examples
# haze: out = out*(1-0.5*s) + 60*s + 0.15 blur blend
# fog:  out = out*(1-0.65*s)+ 90*s + 0.25 blur blend
# low_light: out = out*(0.45+0.55*(1-s))
```

### 3.3 Camera Jitter

| Key | Default | Range | Effect |
|-----|---------|-------|--------|
| `camera.jitter_px` | 0.0 | 0-20 (spec +-20 px/frame) | Per-frame random shift `dx,dy in [-jitter,+jitter]` via `warpAffine`. Applied after noise. |

### 3.4 Platform Motion

| Key | Values | Default | Range | Delta Model |
|-----|--------|---------|-------|-------------|
| `platform.type` | `none`/`linear`/`circular`/`random`/`spiral`/`figure_8` | `linear` | enum | Linear mandatory; others optional extensions. |
| `platform.speed_px_per_frame` | float | 0.0 | 0-20 (spec +-20) | Linear: constant `dx = cos(dir)*speed`; circular: `amp=speed*8, ang=0.02t`; random: `N(0,0.7*speed)`. Clipped +-20. |
| `platform.amplitude` | float | 0.0 | 0-~600 | Reserved for legacy configs. |

Platform returns a `(dx, dy)` delta added to world before viewport extraction; cumulative offset tracked for WorldFOV display.

### 3.5 World / Environment Effects

| Key | Default | Range | Description |
|-----|---------|-------|-------------|
| `world.background` | 18 | 0-80 | Base intensity. |
| `environment.gradient_enabled` | false | bool | Enable gradient world. |
| `environment.gradient_type` | `linear` | `linear`/`radial`/`diagonal` | Gradient shape. |
| `environment.gradient_top/bottom` | 22, 38 | 0-80 | Gradient extremes. |
| `environment.gradient_angle` | 90 | 0-360 | Linear gradient direction. |
| `environment.stars_enabled` | false | bool | Star field clutter (~0.0007 density). |
| `environment.stars_density` | 0.0007 | 0-0.006 | Star count = density*W*H. |
| `environment.stars_brightness` | 185 | 0-255 | Base brightness. |
| `environment.stars_min_mag/max_mag` | 90, 255 | 0-255 | Per-star magnitude range. |
| `environment.stars_twinkle` | false | bool | Per-frame +-6 jitter if true. |
| `environment.stars_seed` | 1337 | int | Separate seed so stars don't alter trajectory. |
| `environment.vignetting_enabled` | false | bool | Lens vignetting. |
| `environment.vignetting_strength/radius/falloff` | 0.42, 0.72, 2.0 | 0-0.95, 0.05-1, 0.3-6 | Power falloff mask. |
| `environment.vignetting_center_x/y` | 0.5 | 0-1 | Centre normalized. |
| `environment.brightness_gain/offset` | 1.0, 0 | gain 0.3-3, offset -60..60 | Pre-stars global scaling. |

---

## 4. Detector Parameters

| Key | Default | Range | Effect |
|-----|---------|-------|--------|
| `detector.threshold_k` | 3.0 | 1.0-6.0 | Adaptive threshold `bg + k*noise`. Lower = more sensitive, more false positives. |
| `detector.min_area` | 8 | 1-200 | Reject small fragments. |
| `detector.max_area` | 900 | 100-5000 | Reject large clutter. |
| `detector.blur_ksize` | 3 | 1,3,5,7 (odd) | Gaussian pre-blur. |
| `detector.adaptive_block` | 51 | 11-101 odd | Reserved (classical adaptive variant). |
| `detector.adaptive_C` | -5 | -20..20 | Reserved. |

---

## 5. Tracker Parameters

| Key | Default | Range | Effect |
|-----|---------|-------|--------|
| `tracker.process_noise` | 0.8 | 0.05-10.0 | Base `Q` scale; multiplied per IMM model (CV 0.6, CA 1.2, MN 3.0). Higher = more responsive, noisier. |
| `tracker.meas_noise` | 4.0 | 0.5-20.0 | `R = I*meas_noise^2`; scaled per frame by `1.5-0.8*confidence`. Higher = trusts measurement less. |
| `tracker.gate_sigma` | 5.0 | 2-10 | NIS gating threshold (approx `gate_sigma^2*2`); rejects outliers above. |
| `tracker.lost_timeout_frames` | 15 | 5-60 | Frames of dropout before TEMP_LOST->REACQUIRING. |
| `tracker.reacq_timeout_frames` | 30 | 10-120 | Frames before SEARCHING. |

State machine additionally uses `required_lock=5`, `required_candidate=3` (hardcoded, validated via long-press).

---

## 6. Controller (PID) Parameters

| Key | Default | Range | Effect |
|-----|---------|-------|--------|
| `controller.kp_pan`, `kp_tilt` | 1.2 each | 0-5.0 | Proportional gain (independent). Higher = faster centreing but risk oscillation. |
| `controller.ki` | 0.05 | 0-1.0 | Integral — removes steady-state bias; too high causes wind-up. |
| `controller.kd` | 0.15 | 0-2.0 | Derivative — damps overshoot; too high amplifies noise. |
| `controller.deadzone_px` | 2.0 | 0-20 | Deadzone suppresses jitter near centre; mapped to ~0.015 deg * (deadzone/2). |
| `controller.integral_limit` | 8.0 | 0-50 | Clamps `integral = sum(error*dt)`. Anti-windup key. |
| `controller.feedforward_gain` | 0.0 | 0-1.5 | `command += FF * vel_hat` from IMM velocity; helps track moving targets without large error. |

`saturation` is not configurable — derived from `camera.max_pan/tilt_speed`.

**Tuning tip:** Tune `Kp` first with `Ki=Kd=0`, then `Kd`, then tiny `Ki` if needed. See `docs/algorithms.md` section 6.5.

---

## 7. Experiment Parameters

| Key | Default | Range | Description |
|-----|---------|-------|-------------|
| `experiment.duration_s` | 30.0 | 1-600 | Auto-stop after this duration (Control Deck Presets tab). |
| `experiment.seed` | 42 | 0-2^31 | Reproducible RNG seed; saved in every `config_used.yaml`. Controls trajectory, platform, noise, stars. |
| `experiment.input_mode` | `SYNTHETIC` | `SYNTHETIC` / `VIDEO` | Input selector (top bar + Control Deck). |
| `experiment.video_path` | `""` | path string | Valid `.mp4` at 30 fps for VIDEO mode; `VideoFileSource` handles native res and codec errors. |

---

## 8. Complete Example Configuration

```yaml
# Resolved baseline (conceptual example; DEFAULT_CONFIG is the source of truth)
world: {width: 2000, height: 2000, background: 18}
camera: {type: monochrome, resolution: [640,480], fov_deg: [4.0,3.0], fps: 30.0,
         initial_position: centre, initial_pan: 0.0, initial_tilt: 0.0,
         max_pan_speed: 5.0, max_tilt_speed: 5.0, update_interval_hz: 30.0, jitter_px: 0.0}
target: {type: beacon_spot, count: 1, shape: square, size: 10, intensity: 255,
         initial_pos: null, initial_mode: random, trajectory: circular,
         speed_px_per_frame: 2.8, angle_deg: 30, radius: 180.0}
platform: {type: linear, speed_px_per_frame: 0.0, amplitude: 0.0}
noise: {gaussian_enabled: false, gaussian_std: 0, salt_pepper_enabled: false, salt_pepper_prob: 0, poisson: false}
atmosphere: {type: clear, strength: 0}
environment: {gradient_enabled: false, gradient_type: linear, gradient_top: 22, gradient_bottom: 38,
              gradient_angle: 90, stars_enabled: false, stars_density: 0.0007, vignetting_enabled: false,
              brightness_gain: 1.0, brightness_offset: 0}
detector: {threshold_k: 3.0, min_area: 8, max_area: 900, blur_ksize: 3, adaptive_block: 51, adaptive_C: -5}
tracker: {process_noise: 0.8, meas_noise: 4.0, gate_sigma: 5.0, lost_timeout_frames: 15, reacq_timeout_frames: 30}
controller: {kp_pan: 1.2, kp_tilt: 1.2, ki: 0.05, kd: 0.15, deadzone_px: 2.0, integral_limit: 8.0, feedforward_gain: 0.0}
experiment: {duration_s: 30, seed: 42, input_mode: SYNTHETIC, video_path: ""}
```

**AI robustness preset:** `configs/presets/03_ai_robustness.yaml` keeps the identity signature and decoy profiles together with moderate disturbances. The older P01–P12 variants remain under `configs/benchmarks/` for controlled detector/tracker regression; they are not GUI presets.

**Custom trajectory and shape:**

```yaml
target:
  trajectory: user-defined
  custom_trajectory_file: "data/my_path.csv"  # rows: x,y or t,x,y, # comments allowed
  shape: user-defined
  custom_polygon: [[0,5],[2,2],[5,0],[2,-2],[0,-5],[-2,-2],[-5,0],[-2,2]]  # 8-point
```

---

## 9. Limit Enforcement and Validation

`config/schema.py:validate_config(cfg)` asserts every spec range before a run starts; failures show an inline error dialog and block `RUN`. The Control Deck spin boxes are also clamped to valid ranges (e.g., jitter slider 0-20, size 5-20) so users cannot enter an invalid value without seeing an inline warning.

```python
# src/fsoc_tracker/config/schema.py excerpt
assert 2000 <= w <= 4000 and 2000 <= h <= 4000
assert 320 <= res[0] <= 1920 and 240 <= res[1] <= 1080
assert 1.0 <= fov[0] <= 12
assert 0 <= gaussian_std <= 20
assert 0 <= salt_pepper_prob <= 0.15
assert 0 <= jitter_px <= 20
assert 0 <= platform.speed <= 20
```

Preset loading merges `DEFAULT_CONFIG <- configs/presets/<selected>.yaml <- active-portion Control Deck edits`, validates, and then refreshes the active source, detector, tracker, and controller. Loading a preset switches to that preset’s owning portion. Applying the dialog sends only the active portion and synchronizes the runtime-mode indicator before resetting the run.

---

## 10. Recommended Performance Presets

| Preset | AI mode | Scenario | Expected outcome |
|--------|---------|----------|------------------|
| **AI — Primary + Decoys** | ON | One coded primary plus two decoys | Primary confirmation after five consistent observations; decoys remain out of PID control |
| **Classical — Clean Baseline** | OFF | Straight single target, clear conditions | Classical detector → EKF-IMM → PID baseline |
| **AI — Robustness** | ON | Primary plus decoys with moderate noise, haze, jitter, and platform motion | No false primary lock under the configured disturbance envelope |
| **Video — Benchmark** | OFF | External `.mp4` at 30 fps | PTZ bypass, detector/metrics/report path |

---

## 11. Reproducibility and Logging

Every run saves `outputs/runs/<timestamp>_<trajectory>_seedN/config_used.yaml` — the fully resolved config (defaults + overlays + Deck edits) plus seed, version, input source, disturbance settings, detector/IMM/PID parameters, video properties if any, timings and `run_metadata.json`. Re-running with the same YAML and seed reproduces the exact trajectory and noise sequence.

---

## 12. Quick Reference — Control Deck Mapping

Each portion below stages the same shared groups independently; the AI portion also stages the AI-only groups.

| Deck Group | Parameters Exposed |
|----------|-------------------|
| Presets & Run | portion-owned preset loader, portion-owned `seed`, portion-owned `duration_s`, save/reset active portion |
| Target | `count`, `shape`, `size`, `initial_pos/mode`, `trajectory`, `speed`, `angle`, `radius`, `intensity`, `custom_trajectory_file`, `custom_polygon` |
| Camera | `resolution`, `fov_deg`, `fps`, `initial_position/pan/tilt`, `max_pan/tilt_speed`, `jitter_px` |
| Estimator & Controller | `detector.threshold_k/min_area/max_area/blur_ksize`, `tracker.process_noise/meas_noise/gate_sigma/lost/reacq`, `controller.kp/ki/kd/deadzone/integral_limit/feedforward` |
| Environment | `world.*`, `environment.*`, `platform.type/speed` |
| Disturbances | `noise.*`, `atmosphere.*`, `camera.jitter_px` |
| Input/Logging | `experiment.input_mode/video_path`, FPS display, overlay toggles, `Debug GT` |
| AI / Identity (AI portion only) | `ai.*`, `primary_target.*`, `decoys.*`, AI search ranking, model paths |

