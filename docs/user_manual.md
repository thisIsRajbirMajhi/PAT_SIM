# User Manual — FSOC Virtual Camera Tracker v1.0.0

## Installation
```bash
pip install -r requirements.txt
python -m fsoc_tracker.main
```
Tested on Python 3.10+, Windows 10/11. Requires opencv-python, PyQt5, numpy, PyYAML.

## First run
1. Launch app: `python src/fsoc_tracker/main.py`
2. Top bar shows SYNTHETIC, IDLE, Seed 42.
3. Click **CONTROL DECK** → select Preset **Clean Baseline** → **Apply**.
4. Click **RUN**. Camera FOV should acquire beacon within <2s, WORLD FOV shows cyan footprint following yellow trail.

## Controls
- **RUN / PAUSE / RESET**: control experiment.
- **CONTROL DECK tabs**:
  - Presets & Run: seed, duration, preset loader.
  - Target: trajectory (straight/circular/figure-8/random/spiral/sinusoidal), speed, size, angle/radius.
  - Camera: resolution (default 640×480), FOV 4°×3°, max pan/tilt 5–10°/s, jitter.
  - Estimator & Controller: Kp/Ki/Kd, deadzone, process/meas noise.
  - Environment: world 2000×2000, platform motion (none/linear/circular/random).
  - Disturbances: Gaussian/S&P/Poisson, atmosphere (clear/haze/fog/rain/low_light), strength sliders.
  - Input/Logging: SYNTHETIC vs VIDEO (.mp4 path), browse, FPS.

## Overlays
Camera FOV: reticle (center), yellow = detector centroid & bbox, green/cyan = EKF-IMM estimate, line = error vector.
World FOV: yellow beacon & trail, cyan camera footprint & boresight.
Toggle via **Overlays** checkbox; **Debug GT** shows hidden truth in magenta (debug only).

## Video Benchmark Mode
1. Set Input mode to VIDEO, Browse to `.mp4` @30fps.
2. Apply → RUN. PTZ is bypassed; detector → tracker → metrics runs directly on video frames.
3. Ensure video is 640×480 or will be processed at native resolution; metrics scale accordingly.

## Export
**EXPORT REPORT** creates `outputs/runs/<timestamp>_<traj>_seedN/` with:
- `config_used.yaml`, `summary_report.json/.html`, `frame_metrics.csv`, `events.json`.
Thresholds displayed live vs limits (RMSE ≤10px etc.).

## Troubleshooting
- No lock: reduce noise/jitter, lower target speed, check trajectory.
- Video not opening: verify codec (H264 mp4), path no spaces.
- Low FPS: reduce resolution or disable Poisson.

## Demo script (3 min)
1. Clean baseline lock (0–40s).
2. Switch to High Noise, show RMSE stays <10 (40–90s).
3. Force loss by pausing then random trajectory, show re-acq <1s (90–130s).
4. Load sample MP4, show same pipeline (130–160s).
5. Export report and open HTML (160–180s).
