# User Manual — FSOC Virtual Camera Tracking PAT Simulator v1.0.0

> **Purpose:** Coarse pointing, acquisition and tracking (PAT) simulator for mobile FSOC terminals — controls a virtual pan-tilt camera to find, centre and follow a moving beacon under disturbances.

---

## Table of Contents

1. System Requirements
2. Installation
3. First Run and Quick Start
4. Input Modes — SYNTHETIC and VIDEO (MP4)
5. GUI Overview
6. Top Bar
7. Camera FOV Viewport
8. World FOV Viewport
9. Live Dashboard
10. Control Deck — Drawer with 7 Tabs
11. Presets
12. Overlays and Display Controls
13. Operation Workflow
14. Export and Reports
15. Thresholds and Live Pass/Fail
16. Troubleshooting
17. Appendix — Configuration Reference

---

## 1. System Requirements

- **OS:** Windows 10/11 (tested), or Linux/macOS with Python 3.10+.
- **Python:** 3.10 or higher.
- **RAM:** 4 GB minimum (640x480 viewport); 8 GB recommended for larger resolutions and long runs.
- **CPU:** Dual-core 2 GHz minimum; EKF/IMM/PID are O(1) per frame, detector dominates at O(W*H) — typically 5-10 ms on 640x480.
- **GPU:** Not required. Optional if a learned detector extension is enabled.

Python dependencies (from `pyproject.toml` / `requirements.txt`):

```
numpy>=1.24
opencv-python>=4.8
PyQt5>=5.15
pyqtgraph>=0.12
PyYAML>=6.0
pillow>=10.0
```

World size defaults to 2000x2000; camera viewport 640x480 at FOV 4 deg x 3 deg, 30 Hz.

---

## 2. Installation

```bash
# Clone or unzip the project so PAT_SIM/ is your working directory
pip install -r requirements.txt

# Alternative (editable install)
pip install -e .

# Verify
python -m fsoc_tracker.main --help   # or
python launch.py
```

If you use a virtual environment:

```bash
python -m venv .venv
# Windows
.venv\Scripts\activate
# Linux/macOS
source .venv/bin/activate
pip install -r requirements.txt
```

Tested on Python 3.10+ and Windows 10/11. If OpenCV or PyQt5 fails to install, upgrade pip (`python -m pip install --upgrade pip`) and retry. No external hardware or services required.

---

## 3. First Run and Quick Start

```bash
python -m fsoc_tracker.main
# or
python src/fsoc_tracker/main.py
# or
python launch.py
```

What you should see on launch:

1. Top bar shows `SYNTHETIC` mode, `IDLE` application state and `Seed 42`.
2. Camera FOV (left viewport): dark 640x480 frame with central reticle.
3. World FOV (right viewport): 2000x2000 map with cyan camera footprint at centre.
4. Dashboard (bottom): cards for state, accuracy, timing, lock/acq, IMM probs, PID and conditions — mostly blank until a run starts.

Start your first experiment in 4 clicks:

1. Click **CONTROL DECK** (top bar, right) to open the drawer.
2. Select Presets tab → **Classical — Clean Baseline** → **Load Preset** → **Apply**.
3. Click **RUN** (top bar). The beacon (yellow) should appear and the Camera FOV should show detection (yellow bbox + centroid), estimate (green/cyan dot) and an error vector.
4. Within < 2 s the Dashboard state should turn `LOCKED` (green) with RMSE < 10 px.

Stop: click **PAUSE** to freeze, **RESET** to clear metrics and rebuild the trajectory with the same seed (replayable).

---

## 4. Input Modes — SYNTHETIC and VIDEO (MP4)

### 4.1 SYNTHETIC Mode (default)

Generates the virtual world + trajectory + platform motion + noise/atmosphere + virtual PTZ camera. The same detector/tracker/metrics pipeline that VIDEO uses processes SYNTHETIC frames.

- World centre (pan=0, tilt=0) maps to image centre.
- All 7 trajectories, 6 platform types, all disturbances and Sr.8 multi-target / Sr.9 shapes are available.
- Deterministic via Seed — same seed reproduces the exact beacon path and noise sequence.
- Ideal for tuning, scenario coverage and disturbance matrices.

### 4.2 VIDEO (Benchmark) Mode

External `.mp4` at **30 fps** bypasses the virtual PTZ camera; frames are decoded directly into the detector -> tracker -> metrics pipeline.

To use benchmark video:

1. Open Control Deck -> **Input/Logging** tab.
2. Change Input Mode to **VIDEO**.
3. Click **Browse**, select an `.mp4` at 30 fps (H.264 recommended). Path should avoid spaces if possible.
4. Click **Apply** -> **RUN**.
5. The Camera FOV now shows decoded video frames; World FOV may be blank or show a debug overlay when enabled. Metrics, acquisition timers and export behave identically.

**Resolution handling:** if video is not 640x480 it is processed at native resolution; error metrics scale accordingly. The system avoids silently stretching that would change the reference error scale. `input_fps` and `processing_fps` are reported separately.

**Codec:** ensure the `.mp4` uses H.264 (most common). If the file fails to open, check codec with VLC/MediaInfo and re-encode if needed; the app shows an actionable error instead of crashing.

**Ground truth:** benchmark video has no synthetic ground truth inside the app. For evaluation, externally-provided `reference_error.csv` can be compared to `frame_metrics.csv` after export (see `docs/testing.md` section 6).

---

## 5. GUI Overview

```
+-------------------------------------------------------------------------+
| FSOC Virtual Camera Tracker   [SYNTHETIC / MP4]  Seed: 42  State: LOCKED|
| [RUN] [PAUSE] [RESET]                     FPS: 29.8   [CONTROL DECK]    |
+-------------------------------+-----------------------------------------+
| CAMERA FOV                    | WORLD FOV                               |
|                               |                                         |
| Live sensor feed              | Full 2000x2000 world map                |
|  - reticle (centre)           |  - beacon trail (yellow)                |
|  - detection (yellow bbox+dot)|  - camera footprint & boresight (cyan)  |
|  - estimate (green/cyan dot)  |  - platform drift path                  |
|  - error vector (centre->est) |  - spiral search path when LOST         |
+-------------------------------+-----------------------------------------+
| LIVE DASHBOARD                                                          |
| State | Accuracy | Timing | Lock/Acq | IMM probs | PID | Conditions      |
+-------------------------------------------------------------------------+
| [EXPORT REPORT]  [BENCHMARK]  Overlays [x]  Debug GT [ ]  Help           |
+-------------------------------------------------------------------------+
```

Three interaction principles: **one-click start** (preset -> Apply -> RUN), **safe defaults** (validated before a run), and **no hidden state** (active config, seed and input source always visible).

---

## 6. Top Bar

| Element | Description |
|---------|-------------|
| Mode badge | `SYNTHETIC` or `MP4`. Colour: blue synthetic, amber video. |
| Preset label | Current preset name, e.g., `Classical — Clean Baseline` or `AI — Primary + Decoys`. |
| Seed | Active random seed (integer). Controls replay. |
| App state | `IDLE` / `RUNNING` / `PAUSED` / `ERROR`. |
| Tracking state | `SEARCHING` / `CANDIDATE` / `ACQUIRING` / `LOCKED` / `TEMP_LOST` / `REACQUIRING` / `FAILED`. Colour-coded (green/blue/amber/red). |
| FPS | Rolling processing FPS. Target >= 20 (spec), camera 30 Hz. |
| RUN | Start or resume the current experiment. Config is validated on click. |
| PAUSE | Freeze the current run (frames stop, timers pause). |
| RESET | Clear metrics, rebuild world and trajectory with the same seed, re-centre camera, reset EKF/IMM/PID and state machine. |
| CONTROL DECK | Opens/closes the sliding drawer. Glows when the drawer is open. |

---

## 7. Camera FOV Viewport (left)

Represents exactly what the sensor / external video provides to the tracking algorithm — the only place the operator evaluates detection quality.

### 7.1 Overlays (toggle via checkbox at bottom)

| Overlay | Colour | Meaning |
|---------|--------|---------|
| Reticle | white cross | Image centre `(W/2, H/2)` — the control setpoint (error zero). |
| Detector centroid & bbox | yellow dot + rectangle | Intensity-weighted centroid and bounding box from `BeaconDetector`. |
| EKF-IMM estimate | green (locked) / cyan (predicting) dot + small ellipse | Fused angular estimate projected to pixel space. |
| Error vector | red/amber line | From reticle to estimate — its length is proportional to angular error. |
| Confidence label | text | Detector confidence 0..1 beside the bbox. |

### 7.2 Information Strip (bottom of viewport)

```
Centroid: (342.1, 248.6) px   Error: (+22.1, +8.6) px   Confidence: 0.91
Angular error: (0.138 deg, -0.054 deg)   State: LOCKED   ROI: full frame
```

All units are explicit (`px`, `deg`, `deg/s`, `Hz`, `ms`, `%`).

### 7.3 Viewport Controls

- **Fit-to-window** toggle (top-right of viewport).
- **Overlays ON/OFF** (bottom bar).
- **Debug GT** checkbox (magenta dot) — shows hidden ground truth. **Disabled during benchmark mode** and labelled `DEBUG ONLY`; never feeds the tracker.
- Screenshot via OS shortcut or EXPORT REPORT recording (see section 14).

By default the view is uncluttered — advanced overlays via checkboxes, not permanently shown.

---

## 8. World FOV Viewport (right)

Shows the complete virtual environment to explain camera-beacon geometry.

| Element | Appearance |
|---------|-----------|
| World boundary | 2000x2000 outer rectangle. |
| Beacon | yellow filled circle + trails (recent path as thin yellow line). |
| Camera footprint | cyan rectangle — current viewport location on the world. |
| Boresight | cyan cross at footprint centre. |
| Platform path | faint line from world centre showing cumulative platform offset. |
| Search spiral | dashed cyan spiral when `REACQUIRING` / `SEARCHING`. |
| Ground truth (debug) | magenta dot — hidden by default. |

Use the World FOV to verify: the cyan footprint should follow the yellow trail when locked, and the spiral should expand then collapse upon re-acquisition.

---

## 9. Live Dashboard (bottom cards)

Each card updates at least once per processed frame. Values show `current / limit` with pass/fail colour (green pass, red fail).

| Card | Fields |
|------|--------|
| **1. Tracking state** | `LOCKED`/`SEARCHING` etc., confidence %, valid measurement YES/NO, missed frames count. Colour: green LOCKED, blue ACQUIRING/SEARCHING, amber TEMP_LOST, red FAILED. |
| **2. Accuracy** | Current error (px), angular error (deg), Mean, RMSE, Maximum, P95 (px). RMSE shown as `6.1 / 10 px`. |
| **3. Timing and processing** | Input FPS, Processing FPS, Frame latency (ms), Dropped frames. `Processing vs Input` reveals headroom. |
| **4. Acquisition and lock** | Acquisition (s), Re-acquisition mean/max/last (s), Lock retention %, Target loss %. Acquisition shown as `0.84 / 2.0 s`. |
| **5. Estimator status (IMM)** | Model probs `CV / CA / MN` (three bars summing to 1), Innovation (sigma), Covariance state. Explains which motion model is trusted. |
| **6. Controller status** | Pan/tilt commands (`1.8 deg/s`), saturation YES/NO per axis, integral clamp state. |
| **7. Active conditions** | Noise, atmosphere, jitter, platform motion, seed — the current disturbance set. |

Thresholds (spec section 9): acquisition <= 2 s, reacq <= 1 s, RMSE <= 10 px, loss < 5 %, FPS >= 20.

---

## 10. Control Deck — AI and Deterministic Portions

Click **CONTROL DECK** to open/close the drawer (right side, slides over the view without closing it). The dialog has two top-level portions: **AI System** and **Deterministic / Classical**. Each portion stages a complete, independent parameter set; switching portions does not overwrite the other portion. Click **Apply Active Portion** to send only the visible portion to the simulator. Parameters that would invalidate a run become read-only while `RUNNING`.

Inline validation: invalid values are highlighted beside the field (range, type) before a run can start, using `config/schema.py`.

Tooltips: hover any technical parameter (e.g., `Kp`) for a plain-language explanation.

### 10.1 Presets & Run in Each Portion

- **AI portion selector:** `AI — Primary + Decoys` / `AI — Robustness` / `Custom`.
- **Deterministic portion selector:** `Classical — Clean Baseline` / `Video — Benchmark` / `Custom`.
- **Load Preset** — loads the selected curated configuration into the active portion only and stages the AI mode shown in the description.
- **Save current configuration** — writes the active portion as a custom preset under `configs/presets/`; it is discovered on the next Control Deck open.
- **Reset Active Portion** — restores the AI portion to the curated AI primary/decoy preset, or the deterministic portion to validated defaults.
- **Random seed** (integer) — controls trajectory, noise, platform, stars. Saved with every run. Each portion keeps its own seed.
- **Simulation duration** (s) — auto-stop after this duration (1-600 s). Each portion keeps its own duration.
- Controls: **Apply Active Portion** / **Cancel** for staged edits.

The detailed P01–P12 files in `configs/benchmarks/` are regression scenarios and are intentionally not shown in these selectors. Every curated preset explicitly declares its owning portion and `AI ON`/`AI OFF`; the runtime-mode indicator follows the active portion.

Sections 10.2–10.7 describe the parameter groups available independently in each portion. The AI portion additionally contains the AI/Identity, primary-profile, and decoy-profile groups.

### 10.2 Target in Each Portion

| Field | Values | Default |
|-------|--------|---------|
| Number of targets (`count`) | 1-5 | 1 |
| Shape (`shape`) | square / circle / gaussian / cross / user-defined | square |
| Width/height (`size`) | 5-20 px per side | 10 |
| Intensity (`intensity`) | 0-255 | 255 |
| Initial position | random / centre / manual `[x,y]` | random (seeded) |
| Motion (`trajectory`) | straight / circular / figure_eight / random / spiral / sinusoidal / user-defined | circular |
| Speed (`speed_px_per_frame`) | 0-20 px/frame | 2.8 |
| Angle (`angle_deg`) | 0-360 (straight) | 30 |
| Radius (`radius`) | 50-800 (circular, figure_8) | 180 |
| Custom trajectory file | path to CSV (`x,y` or `t,x,y`, `#` comments) | blank |
| Custom polygon (`custom_polygon`) | list of [dx,dy] offsets for user-defined shape | blank |

Validate size/speed immediately; units shown beside every field.

### 10.3 Tab 3 — Camera

| Field | Values | Default |
|-------|--------|---------|
| Resolution (`resolution`) | W 320-1920, H 240-1080 | 640x480 |
| World/screen size (`world.width/height`, `background`) | 2000-4000, bg 0-80 | 2000x2000, bg 18 |
| FOV (`fov_deg`) | 1-12 deg each | 4 deg x 3 deg |
| Camera update rate (`fps`, `update_interval_hz`) | 30-60 Hz camera, 20-60 Hz control | 30 Hz |
| Initial pan/tilt (`initial_position`, `initial_pan/tilt`) | centre / user-defined deg | centre (0,0) |
| Max pan/tilt (`max_pan_speed`, `max_tilt_speed`) | 1-15 deg/s (spec 5-10, warn outside) | 5.0 each |
| Jitter (`jitter_px`) | 0-20 px/frame | 0.0 |
| Monochrome/colour (`camera.type`) | monochrome / colour | monochrome |

Shows a small footprint preview in World FOV.

### 10.4 Tab 4 — Estimator & Controller

**EKF settings:** `tracker.process_noise` (0.05-10.0, default 0.8), `meas_noise` (0.5-20.0, default 4.0), `gate_sigma` (2-10, default 5.0).
**IMM settings:** enable/disable IMM, models CV/CA/MN, transition matrix, initial probs `[0.6,0.25,0.15]`, minimum prob 0.02, process-noise scales 0.6/1.2/3.0.
**PID settings:** `controller.kp_pan/tilt` (0-5, default 1.2), `ki` (0-1, 0.05), `kd` (0-2, 0.15), `deadzone_px` (0-20, 2.0), `integral_limit` (0-50, 8.0), derivative filter alpha=0.2, `feedforward_gain` (0-1.5, 0.0), saturation/slew limits.

Tooltips: `Kp: increases response speed but too much may cause oscillation. Ki: removes bias but can wind up during loss. Kd: reduces overshoot but may amplify noisy measurements.`

### 10.5 Tab 5 — Environment

World width/height, background brightness, gradient (linear/radial/diagonal, top/bottom 22/38, angle 90), stars (density 0.0007, brightness, twinkle, vignetting strength/radius/falloff), brightness gain/offset, platform type none/linear/circular/random/spiral/figure_8 and speed.

### 10.6 Tab 6 — Disturbances

Independent toggles and sliders for: salt-and-pepper (`salt_pepper_prob` 0-0.15), Gaussian (`gaussian_std` 0-20), Poisson (on/off), camera jitter (0-20), haze/fog/rain/low_light (`atmosphere.type` + `strength` 0-1). A small live preview shows the effect before starting. Warnings appear when the combination exceeds the benchmark envelope.

### 10.7 Tab 7 — Input, Logging & Display

- Input source: `SYNTHETIC` or `VIDEO`.
- Video path and frame range (when VIDEO).
- Image-centre calibration.
- Output directory (`outputs/runs/`).
- Overlay visibility and **Debug GT** switch (auto-disabled in benchmark VIDEO mode).
- Log level: normal / detailed / diagnostic.

---

## 11. Presets

| Preset | AI mode | Scenario | Use |
|--------|---------|----------|-----|
| **AI — Primary + Decoys** | ON | One primary with two coded decoys, clean synthetic scene | Demonstrate candidate association, five-frame confirmation, and decoy rejection |
| **Classical — Clean Baseline** | OFF | One straight-moving target, no disturbances | Verify the original detector → EKF-IMM → PID path |
| **AI — Robustness** | ON | Primary plus decoys with moderate noise, haze, jitter, and platform motion | Exercise identity safety under realistic disturbances |
| **Video — Benchmark** | OFF | External MP4 with PTZ bypass | Verify ingestion, metrics, and reports; turn AI on for coded footage |
| **Custom** | Current state | User-saved YAML in `configs/presets/` | Reproducible experiments |

Selecting a preset loads it into the active portion’s staged edits — click **Load Preset**, then **Apply Active Portion**. The runtime-mode indicator follows the active portion; AI-specific fields exist only in the AI portion and are never applied from the deterministic portion. Benchmark-only P01–P12 scenarios remain under `configs/benchmarks/` and are not clutter in these lists.

---

## 12. Overlays and Display Controls

| Control | Location | Purpose |
|---------|----------|---------|
| Overlays checkbox | Bottom bar | Show/hide all detector/estimate overlays in Camera FOV. |
| Debug GT checkbox | Bottom bar | Magenta ground-truth dot — `DEBUG ONLY`, auto-off in benchmark mode, never feeds tracker. |
| Fit-to-window | Viewport corner | Letterbox or stretch; does not affect metrics. |
| Dashboard cards | Bottom | Live pass/fail colour; hover for limit definitions. |

Colour language (consistent everywhere):

| Meaning | Colour | Used For |
|---------|--------|----------|
| Healthy lock | Green | LOCKED state, passing metric |
| Active estimate | Cyan | EKF-IMM prediction/fused estimate |
| Raw detection | Yellow | Detector centroid and bbox |
| Search/acquisition | Blue | Searching, acquiring, spiral path |
| Warning/degraded | Amber | TEMP_LOST, low confidence, saturation |
| Failure | Red | LOST, invalid input, benchmark failure |
| Ground truth | Magenta, debug only | Never shown by default |

---

## 13. Operation Workflow

**Recommended operator workflow (10 steps):**

1. Open the application; the default preset is shown in the top bar.
2. Select `SYNTHETIC` or `VIDEO` input.
3. Open **CONTROL DECK** and confirm Target, Camera, Estimator, Controller, Disturbance settings.
4. Click **Apply** and review the summary line `640x480 | FOV 4 deg x 3 deg | 30 FPS | ...`.
5. Click **RUN**.
6. Watch Camera FOV for acquisition (yellow->green) and World FOV for footprint following the yellow trail.
7. Use the live Dashboard to verify error, FPS, lock retention and IMM probs.
8. Increase disturbance severity or trigger target loss to test recovery (re-acq should be <= 1 s).
9. Click **PAUSE** or wait for `duration_s` to complete.
10. Click **EXPORT REPORT** and inspect `outputs/runs/<timestamp>_<trajectory>_seedN/`.

The operator should never need to inspect internal logs during a normal demo.

**Hot actions during RUN:**

- Parameter edits that would invalidate a run (resolution, world size, trajectory type) are locked while RUNNING. Pause or Reset to edit.
- Gain sliders for PID and EKF (`Kp`, `process_noise`, `meas_noise`) can be tweaked live — `update_config` hot-swaps them and changes are logged.
- Seed changes require **RESET** to regenerate the trajectory deterministically.

---

## 14. Export and Reports

Click **EXPORT REPORT** at any time. The system creates:

```
outputs/runs/<timestamp>_<trajectory>_seedN/
  config_used.yaml        # fully resolved config (defaults + overlays + Deck edits)
  run_metadata.json       # seed, version/commit, input source, video properties, timings, disturbance set
  frame_metrics.csv       # one row per frame (frame_id, timestamp, error_px, tracking_state, confidence, FPS, saturation, model_probs, etc.)
  events.json             # SEARCHING->CANDIDATE->LOCKED, TEMP_LOST, REACQUIRING->LOCKED with timestamps and reacq durations
  summary_report.json     # duration, FPS, acquisition/reacq summaries, mean/RMSE/max/P95, lock/loss%, valid det %, saturation count
  summary_report.html     # human-readable rendering of the same summary
```

Reports are self-contained — the saved `config_used.yaml` plus seed reproduces the exact run via `Benchmark` or manual replay.

**Batch / headless:** use the `BENCHMARK` dialog (if visible) to queue scenarios and generate the same `outputs/runs/` folders without the GUI event loop; see `docs/testing.md` section 5 pseudo-code.

---

## 15. Thresholds and Live Pass/Fail

| Metric | Pass | Reported As |
|--------|------|-------------|
| Acquisition time | <= 2 s | Time from RUN until first stable `LOCKED` (>=5 consecutive valid). Card: `0.84 / 2.0 s` |
| Re-acquisition time | <= 1 s | Per loss event; Dashboard shows last/mean/max. |
| Tracking error (RMSE) | <= 10 px | `RMSE 6.1 / 10 px` plus mean, max, P95. |
| Target loss | < 5 % | `1.3 / 5 %` |
| Processing speed | >= 20 FPS | `29.3 / 20 FPS` (end-to-end `total/duration` and rolling `fps`). |

A metric turning red in the Dashboard indicates a spec violation for that run; the exported `summary_report.html` applies the same limits.

---

## 16. Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| No lock after RUN | Noise/jitter too high, speed too high, or target leaves FOV | Reduce `gaussian_std` / `jitter_px` / `speed_px_per_frame`, check trajectory `radius` or `count` clutter |
| Camera footprint not moving | State is `REACQUIRING/SEARCHING` with spiral | Wait; if stuck, reduce jitter or platform speed — large jitter desaturates the detector threshold |
| Dashboard RMSE red | Combined disturbances exceed operating envelope | Tests beyond `gaussian 14 + S&P 0.04 + haze 0.35 + jitter 8` are expected to degrade; see `docs/testing.md` matrix |
| Video not opening | Codec or path issue | Verify H.264 `.mp4`, path without spaces/unicode, file not locked by another app; check console error |
| Low FPS (< 20) | Large resolution or Poisson on weak CPU | Reduce `resolution` (e.g., 640x480), disable Poisson, close overlays that force redraw |
| `validate_config` error dialog | Config out of spec | Read the assertion message (e.g., `Target Size 5-20 px`), fix in Control Deck, click Apply |
| Seed seems to not change trajectory | Seed only applied on RESET or new RUN | Click RESET after changing seed; seed is logged per run so replays match |
| Overlays missing | Checkbox off | Enable **Overlays** in bottom bar |
| Star/Vignetting clutter confuses detector | Density too high or threshold_k too low | Lower `stars_density`, increase `min_area`, raise `threshold_k` to 3.5-4.0 |

---

## 17. Appendix — Configuration Reference

### Curated GUI presets

The four maintained GUI overlays are in `configs/presets/`:

| File | AI mode | Purpose |
|------|---------|---------|
| `01_ai_primary_decoys.yaml` | ON | Primary + two decoys, coded identity demonstration |
| `02_classical_baseline.yaml` | OFF | Clean single-target classical regression |
| `03_ai_robustness.yaml` | ON | Moderate disturbance and decoy stress test |
| `04_video_benchmark.yaml` | OFF | External MP4 ingestion benchmark |

The detailed P01–P12 scenarios are benchmark-only files under `configs/benchmarks/`; they are not selectable in the Control Deck.

### Example resolved classical configuration

```yaml
world: {width: 2000, height: 2000, background: 18}
camera: {type: monochrome, resolution: [640,480], fov_deg: [4.0,3.0], fps: 30.0,
         initial_position: centre, max_pan_speed: 5.0, max_tilt_speed: 5.0,
         update_interval_hz: 30.0, jitter_px: 0.0}
target: {type: beacon_spot, count: 1, shape: square, size: 10, intensity: 255,
         initial_pos: null, initial_mode: random, trajectory: circular,
         speed_px_per_frame: 2.8, angle_deg: 30, radius: 180.0}
platform: {type: linear, speed_px_per_frame: 0.0}
noise: {gaussian_enabled: false, gaussian_std: 0, salt_pepper_enabled: false, salt_pepper_prob: 0, poisson: false}
atmosphere: {type: clear, strength: 0}
environment: {gradient_enabled: false, stars_enabled: false, vignetting_enabled: false,
              brightness_gain: 1.0, brightness_offset: 0}
detector: {threshold_k: 3.0, min_area: 8, max_area: 900, blur_ksize: 3}
tracker: {process_noise: 0.8, meas_noise: 4.0, gate_sigma: 5.0,
          lost_timeout_frames: 15, reacq_timeout_frames: 30}
controller: {kp_pan: 1.2, kp_tilt: 1.2, ki: 0.05, kd: 0.15,
             deadzone_px: 2.0, integral_limit: 8.0, feedforward_gain: 0.0}
experiment: {duration_s: 30, seed: 42, input_mode: SYNTHETIC, video_path: ""}
```

### AI robustness preset

`configs/presets/03_ai_robustness.yaml` adds moderate combined disturbances to the coded primary/decoy scenario while keeping the AI safety threshold at five consistent observations.

### Custom trajectory and shape

```yaml
target:
  trajectory: user-defined
  custom_trajectory_file: "data/my_path.csv"   # rows: x,y  or  t,x,y  (# comments allowed)
  shape: user-defined
  custom_polygon: [[0,5],[2,2],[5,0],[2,-2],[0,-5],[-2,-2],[-5,0],[-2,2]]
```

Full parameter limits and descriptions: see `docs/configuration.md` section 2 (Sr.1-15 + disturbances) with ranges, defaults and examples for every key.

---

*For architecture, algorithms and testing detail see `docs/architecture.md`, `docs/algorithms.md`, `docs/testing.md` and the comprehensive `docs/technical_report.md`.*
