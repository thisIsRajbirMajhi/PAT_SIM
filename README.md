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

The Control Deck exposes 33 curated, user-facing presets (16 AI + 17 deterministic), split by owning portion. Coverage per `Resources/PRESET_COVERAGE.json` and `Resources/README_PRESETS_FULL_SUITE.md`:

- **AI mode**: Primary + Decoys, Hard Negatives, Fast Acquisition, Circle/Gaussian/Cross targets, Random Motion, Multi-Target Scene (5 targets + 5 decoys), Signature Disabled, Model Path Test, Failure Fallback, Rain + Low Light, User-Defined Geometry (custom polygon + `trajectories/figure8_demo.json`), Linear/Spiral/Figure-8 Platform.
- **Deterministic mode**: Baseline, High Noise, All Noise, Circle/Gaussian/Cross targets, Custom Geometry, Environment Full (gradient + stars + vignetting), Linear/Random/Spiral/Figure-8 Platform, Raster/Hybrid Search, Video Benchmark, Video Calibrated (principal-point offsets).

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
- **AI ON ≠ learned models**: Control Deck `◉ AI System → Apply Active Mode` sets `ai.enabled=true` (pipeline on). Learned MobileNetV3-Small + GRU run only when `ai.candidate_model_path` / `ai.identity_model_path` point at real `models/*/candidate_model.onnx` + `identity_model.onnx` files; empty/missing path = heuristic fallback (`model_ver=heuristic` in Dashboard). All shipped AI presets use `null` paths (heuristic) until you wire exports.

## Training
```bash
# best-practice retrain (~14k patches / ~250 seqs, exits GRU tiny-dataset mode):
python scripts/generate_training_data.py --config configs/training.yaml --num-scenarios 300 --frames-per-scenario 90 --seed-start 1
python scripts/train_candidate_classifier.py --config configs/training.yaml
python scripts/train_identity_model.py --config configs/training.yaml
python scripts/calibrate_thresholds.py --config configs/training.yaml
python scripts/evaluate_ai_models.py --config configs/training.yaml --split test --out outputs/ai_eval
python scripts/export_models.py --config configs/training.yaml --format onnx
# then wire models/*/candidate_model.onnx + identity_model.onnx into Control Deck §8 AI Runtime
```
Current baseline (2026-09-25, `100×60`): candidate `acc 0.72, false_primary 0.127`, test `P 0.66`; GRU `63/8/14` seqs (`1.0` meaningless). Below `≥0.85` gate — retrain per above.
Data split seeds `1-70/71-85/86-100` no leakage (`>100` via `seed%3`). Hard negatives form substantial val/test. See `docs/training_pipeline.md`.

## Config
- `configs/presets/`: 33 curated GUI presets (16 AI + 17 deterministic); each file declares its owning portion in `preset_meta.system` (`ai` or `deterministic`) and its AI mode in `preset_meta.ai_mode`. Source bundle in `Resources/gui_presets/` with coverage in `Resources/PRESET_COVERAGE.json`.
- `configs/benchmarks/`: benchmark-only P01–P12 regression scenarios (not shown in the Control Deck).
- `configs/ai.yaml`: `enabled`, `patch_size 64`, `sequence_length 25`, `thresholds`, `signatures`, `model_paths`, `inference_timeout_ms`
- `configs/training.yaml`: data roots, split, candidate/identity hyperparams, export opset
- `configs/identity_signatures.yaml`: primary/decoy blink/freq profiles
- `configs/model_thresholds.yaml`: calibrated `primary 0.85`, `decoy 0.85`, `confirmation 5`, `temperature`

## Branch
Active development on `feature/ai-primary-target-identification` — do not merge to `main` until Gate 4 approval (implementation, tests, model, benchmark, docs, limitations, final report).

