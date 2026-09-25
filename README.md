# FSOC Virtual Camera Tracking — PAT Simulator

Coarse pointing, acquisition & tracking (PAT) simulator for mobile Free-Space Optical Communication terminals. Controls a virtual pan–tilt camera to find, center and follow a moving beacon under disturbances and decoys.

## Quick start
```bash
pip install -r requirements.txt
python -m fsoc_tracker.main
# or
python src/fsoc_tracker/main.py
```

## Layout
- **Top bar**: mode (SYNTHETIC/MP4), state, seed, FPS, primary confidence, RUN/PAUSE/RESET/CONTROL DECK
- **Camera FOV**: live sensor feed, reticle, AI multi-candidate overlays (IDs, green primary / red decoy / gray unknown), detection (yellow classical), estimate (green/cyan), error vector
- **World FOV**: full 2000×2000 world, beacon + decoy trails, cyan camera footprint & boresight
- **Target Tracks**: live table ID/Class/Primary%/Signature/State/Age/Missed + evidence checklist
- **Dashboard**: state, accuracy (RMSE/mean/max/P95), timing, lock/acq, IMM probs, PID, conditions
- **Control Deck** (drawer): two independent portions — **AI System** and **Deterministic / Classical** — each with its own staged presets, Target, Camera, Estimator/Controller, Environment, Disturbances, Search, Detection, and Input/Logging settings. AI-only identity/decoy controls live only in the AI portion.

## Presets

The Control Deck exposes four curated, user-facing presets, split by owning portion:

- **AI — Primary + Decoys** (AI portion, AI ON): one coded primary plus two decoys; demonstrates multi-candidate identity confirmation and decoy rejection.
- **Classical — Clean Baseline** (deterministic portion, AI OFF): the original single-target detector → EKF-IMM → PID path with no AI controls active.
- **AI — Robustness** (AI portion, AI ON): the same identity workflow with moderate noise, haze, jitter, platform motion, and faster decoys.
- **Video — Benchmark** (deterministic portion, AI OFF): external MP4 input with virtual PTZ bypass; switch to the AI portion when testing coded video.

The detailed P01–P12 scenarios remain available as benchmark-only files in `configs/benchmarks/` for deterministic regression tests. They are intentionally not clutter in the GUI selector. Use **Save As** to add a custom preset under `configs/presets/`.

## Thresholds (per spec)
Acquisition ≤2s, Re-acquisition ≤1s, RMSE ≤10px, Loss <5%, FPS ≥20

## Input modes
- **Synthetic**: procedural world + trajectories (straight, circular, figure-8, random, spiral, sinusoidal) + platform motion + noise/atmosphere + virtual PTZ + coded blinking signatures
- **Video**: external .mp4 @30fps bypasses PTZ; same detector/tracker/metrics pipeline

## Reports
`EXPORT REPORT` writes `outputs/runs/<timestamp>_<trajectory>_seedN/` with:
`config_used.yaml`, `summary_report.json/.html`, `frame_metrics.csv`, `events.json`, `run_metadata.json`

## Architecture
`config → input (FrameSource) → simulation → perception (BeaconDetector multi-candidate) → AI (MobileNetV3-Small → GRU → IdentityStateMachine) → tracking (EKF+IMM confidence-aware) → control (PID bounded, decoy memory) → evaluation → ui`
Ground truth is evaluator-only and never leaks to detector/tracker/AI.

## AI — Primary Target Identification (Plan §1-18)
- **Search**: deterministic local→spiral→raster; AI region ranking hook (predicted pos/velocity, decoy memory, disturbances)
- **Detection**: classical threshold+MORPH+CC → `Candidate` (centroid/bbox/area/aspect/brightness/contrast/compactness/dist) + 64×64 patch + `BeaconDetector.detect_candidates()`
- **Track**: `TrackManager` nearest-gate + missed counters + decoy memory, never `brightest=primary`
- **Identity**: `Signatures` blink `10110010` vs decoy `11100011` (12 Hz ± tolerance), shape/size, motion envelope, persistence, EKF innovation/IMM; score `0.60*blink+0.20*freq+0.20*size`; confirm `≥0.85` for 5 frames → `PRIMARY_CONFIRMED` else `UNKNOWN`
- **Safety**: only `PRIMARY_CONFIRMED` drives full PID; `UNKNOWN/CHECKING` bounded motion; rejected decoys remembered; innovación gating (large NIS + low identity → reject); AI timeout → high covariance + prediction/bounded search

## Training
```bash
python scripts/generate_training_data.py --num-scenarios 100 --frames-per-scenario 60
python scripts/train_candidate_classifier.py --config configs/training.yaml
python scripts/train_identity_model.py --config configs/training.yaml
python scripts/calibrate_thresholds.py --config configs/training.yaml
python scripts/evaluate_ai_models.py --split test --out outputs/ai_eval
python scripts/export_models.py --format onnx
```
Data split seeds `1-70/71-85/86-100` no leakage. Hard negatives form substantial val/test. See `docs/training_pipeline.md`.

## Config
- `configs/presets/`: four curated GUI presets; each file declares its owning portion in `preset_meta.system` (`ai` or `deterministic`) and its AI mode in `preset_meta.ai_mode`.
- `configs/benchmarks/`: benchmark-only P01–P12 regression scenarios (not shown in the Control Deck).
- `configs/ai.yaml`: `enabled`, `patch_size 64`, `sequence_length 25`, `thresholds`, `signatures`, `model_paths`, `inference_timeout_ms`
- `configs/training.yaml`: data roots, split, candidate/identity hyperparams, export opset
- `configs/identity_signatures.yaml`: primary/decoy blink/freq profiles
- `configs/model_thresholds.yaml`: calibrated `primary 0.85`, `decoy 0.85`, `confirmation 5`, `temperature`

## Branch
Active development on `feature/ai-primary-target-identification` — do not merge to `main` until Gate 4 approval (implementation, tests, model, benchmark, docs, limitations, final report).

