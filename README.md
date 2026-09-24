# FSOC Virtual Camera Tracking — PAT Simulator

Coarse pointing, acquisition & tracking (PAT) simulator for mobile Free-Space Optical Communication terminals. Controls a virtual pan–tilt camera to find, center and follow a moving beacon under disturbances.

## Quick start
```bash
pip install -r requirements.txt
python -m fsoc_tracker.main
# or
python src/fsoc_tracker/main.py
```

## Layout
- **Top bar**: mode (SYNTHETIC/MP4), state, seed, FPS, RUN/PAUSE/RESET/CONTROL DECK
- **Camera FOV**: live sensor feed, reticle, detection (yellow), estimate (green/cyan), error vector
- **World FOV**: full 2000×2000 world, beacon trail, cyan camera footprint & boresight
- **Dashboard**: state, accuracy (RMSE/mean/max/P95), timing, lock/acq, IMM probs, PID, conditions
- **Control Deck** (drawer): Presets, Target, Camera, Estimator/Controller, Environment, Disturbances, Input/Logging

## Presets
Clean Baseline / High Noise / Platform Jitter / Low Light-Fog / Custom

## Thresholds (per spec)
Acquisition ≤2s, Re-acquisition ≤1s, RMSE ≤10px, Loss <5%, FPS ≥20

## Input modes
- **Synthetic**: procedural world + trajectories (straight, circular, figure-8, random, spiral, sinusoidal) + platform motion + noise/atmosphere + virtual PTZ
- **Video**: external .mp4 @30fps bypasses PTZ; same detector/tracker/metrics pipeline

## Reports
`EXPORT REPORT` writes `outputs/runs/<timestamp>_<trajectory>_seedN/` with:
`config_used.yaml`, `summary_report.json/.html`, `frame_metrics.csv`, `events.json`, `run_metadata.json`

## Architecture
`config → input (FrameSource) → simulation → perception (BeaconDetector) → tracking (EKF+IMM+StateMachine) → control (PID+search) → evaluation → ui`
Ground truth is evaluator-only and never leaks to detector/tracker.

