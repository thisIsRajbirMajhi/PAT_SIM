# AI Architecture — FSOC Virtual Camera Tracker

> Source of truth: `Plan/AI Plan.md`. This doc summarizes the implemented
> architecture and module responsibilities.

## Pipeline

```
Camera frame
  → Search planner (deterministic spiral/raster; later AI region ranking)
  → Classical candidate generation (grayscale → adaptive threshold → morphology → CC)
  → MobileNetV3-Small candidate classifier  (Stage 1, per-patch 64×64 + 9 num features)
  → Multi-target track manager (one TrackState per candidate_id)
  → GRU temporal identity classifier       (Stage 2, 20-30 obs per track)
  → Identity state machine (SEARCHING → CANDIDATE_FOUND → IDENTITY_CHECKING → PRIMARY_CONFIRMED / DECOY_CONFIRMED / UNKNOWN)
  → EKF-IMM (confidence-aware covariance + innovation gating) → PID
```

AI provides evidence and confidence; explicit state logic, EKF-IMM and bounded PID keep the system stable and explainable.

## AI ON vs learned weights

- `ai.enabled=true` (Control Deck `◉ AI System` + `Apply Active Mode`) only starts `AIInferencePipeline`.
- `CandidateClassifier` / `IdentityClassifier` load learned weights only when
  `ai.candidate_model_path` / `ai.identity_model_path` point at existing `.onnx`/`.pt`
  files (`models/candidate_classifier/candidate_model.onnx`,
  `models/identity_classifier/identity_model.onnx`).
- Empty/missing path, failed load, or per-frame timeout → deterministic heuristic
  fallback (brightness/compactness + blink voter, `model_version="heuristic"`),
  conservative UNKNOWN, never a silent PRIMARY. All shipped AI presets use `null`
  paths (heuristic) until exports are wired into Deck §8 AI Runtime.

## Module map

| Path | Responsibility |
|---|---|
| `src/fsoc_tracker/ai/types.py` | `Candidate`, `IdentityResult`, `TrackState`, `AIInferenceResult` contracts |
| `src/fsoc_tracker/ai/features.py` | 64×64 patch crop (border-padded), numerical features, GRU sequence builder |
| `src/fsoc_tracker/ai/signatures.py` | Blink correlation, frequency error, size/motion envelope scoring |
| `src/fsoc_tracker/ai/candidate_model.py` | Stage-1 MobileNetV3-Small + heuristic fallback |
| `src/fsoc_tracker/ai/identity_model.py` | Stage-2 GRU + heuristic voter |
| `src/fsoc_tracker/ai/inference.py` | `AIInferencePipeline` orchestrator with timeout/fallback |
| `src/fsoc_tracker/ai/thresholds.py` | Primary/decoy/UNKNOWN regions + confirmation-frame logic |
| `src/fsoc_tracker/ai/calibration.py` | Temperature scaling, ECE, threshold sweep |
| `src/fsoc_tracker/ai/training/*` | `dataset.py`, `augmentations.py`, `train_candidate.py`, `train_identity.py` |
| `src/fsoc_tracker/ai/evaluation/*` | `metrics.py`, `confusion.py`, `reports.py` |
| `src/fsoc_tracker/perception/` | Classical candidate generation (unchanged, extended to multi-candidate) |
| `src/fsoc_tracker/tracking/` | Track manager + identity state machine extension |
| `src/fsoc_tracker/simulation/` | Primary/decoy/disturbance generation (extended for hard negatives) |
| `src/fsoc_tracker/control/` | Search + PID (integrated with identity gating) |
| `src/fsoc_tracker/ui/` | Camera/World overlays, target-tracks table, evidence panel |

## Safety invariants

- `brightness` alone never confirms identity.
- Only `PRIMARY_CONFIRMED` drives full PID; `UNKNOWN`/`IDENTITY_CHECKING` use bounded motion.
- Rejected decoys are remembered and not immediately re-selected.
- AI failure → high covariance + log + bounded search (never silent PRIMARY).

## Performance targets

Acquisition ≤2s, re-acquisition ≤1s, RMSE ≤10px, loss <5%, ≥20 FPS (30 FPS native).
