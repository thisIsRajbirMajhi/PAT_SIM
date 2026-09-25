# FSOC Virtual Camera Tracking — PAT Simulator

## Project Overview

This project implements a **software-only coarse pointing, acquisition and tracking (PAT) simulator** for mobile Free-Space Optical Communication (FSOC) terminals. It controls a virtual pan-tilt camera to find, centre and follow a moving optical beacon under realistic disturbances without requiring expensive hardware.

**Core Challenge:** Closed-loop control where the camera observes only its current field of view, detects the beacon, estimates its centroid, converts image error to pan/tilt commands, and moves within speed limits — repeating at ≥20 Hz while handling noise, jitter, platform motion and atmospheric effects.

## Deliverables (per Problem Statement)

| Deliverable | Path | Status |
|-------------|------|--------|
| Standalone Software Application | `python -m fsoc_tracker.main` or `python launch.py` | ✅ Complete, PyQt5 + OpenCV, light theme |
| Source Code (modular, commented) | `src/fsoc_tracker/` | ✅ 10 modules, docstrings, see `docs/architecture.md` |
| Technical Report (10-20 pages) | `docs/technical_report.md` | ✅ 611 lines, 12 sections, code snippets |
| User Manual | `docs/user_manual.md` | ✅ 494 lines, installation, GUI, workflow |
| Performance Log (auto) | `outputs/runs/<ts>_<traj>_seedN/` | ✅ `RobustPerfLogger` auto-generates |

## Quick Start

```bash
pip install -r requirements.txt
python launch.py
# or
python -m fsoc_tracker.main
# or headless batch:
python scripts/run_simulation.py --trajectory circular --duration 30 --seed 42
python scripts/run_video_benchmark.py --video data/input_videos/test.mp4
python scripts/run_parameter_sweep.py
```

## Documentation

- **Architecture:** `docs/architecture.md` — 10-layer module decomposition, data flow, folder structure
- **Algorithms:** `docs/algorithms.md` — detector, EKF, IMM, PID with equations and code
- **Configuration:** `docs/configuration.md` — all Sr.1-15 + disturbances with limits/defaults
- **Testing:** `docs/testing.md` — unit, integration, disturbance matrix, video benchmark
- **Technical Report:** `docs/technical_report.md` — 10-20 page comprehensive report
- **User Manual:** `docs/user_manual.md` — detailed operation guide
- **Demo Script:** `docs/demo_script.md` — 3-5 min timeboxed narrative

## Key Features

- **4 mandatory trajectories + 3 optional:** Straight, Circular, Figure-of-8, Random, Spiral, Sinusoidal, User-defined (CSV)
- **1-5 targets** with independent trajectories and 5 shapes: square, circle, gaussian, cross, user-defined polygon (5-point star fallback)
- **Environment:** Gradient (linear/radial/diagonal), Stars (density 0-0.006), Vignetting, Brightness — all configurable in Control Deck → Environment
- **Disturbances:** Gaussian (σ 0-20), Salt & Pepper (~10% =0.10, 0-0.15), Poisson, Jitter ±20, Atmosphere (clear/haze/fog/rain/low_light), Platform (linear/circular/random/spiral/figure_of_8 ±20)
- **Camera:** Monochrome/Colour, 640×480 (320-1920), FOV 4×3° (1-12°), FPS 30-60 (min 30), Pan/Tilt 5-10°/s, Initial position centre/user-defined with preview, Update ≥20 Hz
- **Detector:** Adaptive `bg + k·σ` (k=3) + p98, morphology, intensity-weighted centroid `ΣI·x/ΣI`
- **Tracker:** Hybrid EKF-IMM-PID (CV/CA/MN, 6-state, tan projection, NIS gating, 7-state machine)
- **GUI:** Light theme, Camera FOV (reticle, bbox, centroid, est trail, vel arrow), World FOV (cyan footprint, beacon trail, scale bar), Live Dashboard (58 own fields, 8 cards), two-portion Control Deck (AI + deterministic), Benchmark Results modal, Auto-logs

## Folder Structure (per Implementation Plan §31)

```
fsoc-virtual-tracker/
├── src/fsoc_tracker/        # main package (modular, commented)
│   ├── common/              # types, enums, constants, clock
│   ├── config/              # defaults, schema, loader
│   ├── input/               # FrameSource, synthetic/video adapters
│   ├── simulation/          # world, trajectories (7), platform, camera, noise
│   ├── perception/          # detector
│   ├── tracking/            # ekf, imm, state_machine, tracker
│   ├── control/             # pid, camera_controller
│   ├── evaluation/          # metrics, report, auto_logger
│   ├── ui/                  # app, viewport, dashboard, control_deck, theme
│   └── infrastructure/      # logging, profiling
├── configs/                 # presets/ (GUI), benchmarks/ (P01-P12), AI/training config
├── tests/                   # unit, integration, scenarios, fixtures
├── scripts/                 # run_simulation, run_video_benchmark, run_parameter_sweep
├── models/                  # optional AI models (README)
├── data/input_videos/       # benchmark videos
├── outputs/runs/            # timestamped auto-logs
└── docs/                    # all documentation
```

## Performance (example: 120 frames, circular, clear)

- RMSE ~0.95 px (≤10 PASS), Loss 3.3% (<5 PASS), Acq 0.09s (≤2.0 PASS), FPS ~30 (≥20 PASS)
- High-noise (jitter12): RMSE 7.49, combined (G8+jitter8+haze0.3): 5.48 — all <10

See `docs/technical_report.md` §9 for full matrix and analysis.

## License

MIT — See `LICENSE` if present.
