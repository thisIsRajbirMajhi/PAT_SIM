# Phased Implementation Plan — AI Primary Target Identification

> Branch: `feature/ai-primary-target-identification` (DO NOT MERGE until all gates approved)
> Source of truth: `Plan/AI Plan.md` (product/architecture) + `Plan/Prompt.md` (repo-specific instructions + branch protection)

---

## Goal

Extend the existing FSOC PAT simulator (EKF-IMM + PID + deterministic search) with an AI-enhanced pipeline that can **search**, **detect multiple beacon-like candidates**, **track each candidate independently**, **identify the designated primary beacon**, and **reject decoys/noise** — without replacing the estimator/controller with a black box, and without breaking the existing `ai.enabled == false` path.

---

## Gate policy (Prompt §11)

| Gate | After | Approval required before proceeding |
|------|-------|-------------------------------------|
| Gate 1 | Phase 0 discovery, architecture, phase plan | User |
| Gate 2 | Phase 1-3 baseline, data generation, initial tests | User |
| Gate 3 | Phase 4-6 model training, calibration, independent eval | User |
| Gate 4 | Phase 7-8 full integration, UI, docs, final verification | User |

Final report (§12) and explicit user approval are required before any merge to `main`.

---

## Phase 0 — Discovery & Gap Analysis ✅ (this branch scaffold)

**Deliverables (Prompt §6 Phase 0):**
- Current architecture summary, affected files, data contracts, dependency map, phase plan, risks, open questions.
- Branch `feature/ai-primary-target-identification` created from `master` (commit `c3868ce`).

**Key findings:**
- App entry: `src/fsoc_tracker/main.py` → `ui/app.py::MainWindow` (30 Hz timer tick).
- Current detector (`perception/detector.py`) returns a **single** `Detection` (brightest scored blob). No multi-candidate, no per-candidate track.
- `tracking/` has EKF (`ekf.py`) + IMM (`imm.py`) + single-track `Tracker` + `TrackingStateMachine` (SEARCHING/CANDIDATE/ACQUIRING/LOCKED/TEMP_LOST/REACQUIRING/FAILED) — needs extension to multi-target identity states.
- `simulation/world.py` already supports multi-target (`count` 1-5) with independent trajectories and encoded disturbances (Gaussian, S&P, Poisson, haze/fog/rain/low-light, gradient/stars/vignetting) — good substrate for hard-negative generation.
- `evaluation/metrics.py` + `auto_logger.py` handle per-frame CSV + summary + HTML; AI metrics should extend, not replace.
- `ui/` has CameraView + WorldView + LiveDashboardWindow (58 fields) + ControlDeck — needs target-tracks table + evidence panel + confirmation gating on PID.
- No `ai/` module existed; now scaffolded (see Phase 1).

**Affected files (existing, to be extended not rewritten):**
`common/types.py`, `common/enums.py`, `config/defaults.py`, `config/schema.py`, `perception/detector.py`, `tracking/*`, `simulation/*`, `control/camera_controller.py`, `evaluation/*`, `ui/*`, `main.py` tick loop, `requirements.txt`, `pyproject.toml`.

**Risks / open questions:**
- Need `torch`/`torchvision` for MobileNet + GRU; must stay optional so CI + headless runs without GPU still pass (heuristic fallback covers this).
- ONNX Runtime vs TFLite — default to ONNX (CPU) per Plan §9.2 Step 11.
- At least one observable signature must differ between primary and decoys (Plan §8) — currently synthetic only; hardware spectral/challenge-response is a hook, not required for first milestones.
- Hard negatives must dominate val/test, not just train (Plan §9.2 Step 2).

---

## Phase 1 — Interfaces & Configuration

**Scope (Prompt §5 + Plan §5-7):** Add typed structures + config (no behavior change).

- `src/fsoc_tracker/ai/types.py` — `Candidate`, `TrackState`, `IdentityEvidence`, `IdentityResult`, `ModelMetadata`, `AIInferenceResult`, enums `CandidateClass`, `IdentityClass`, `IdentityState`.
- `src/fsoc_tracker/ai/features.py` — 64×64 patch crop (border-padded), numerical features, GRU sequence builder (seq_len 20-30, mask).
- `src/fsoc_tracker/ai/signatures.py` — blink correlation, frequency error, aggregate `signature_score`.
- `src/fsoc_tracker/ai/thresholds.py`, `calibration.py` — operating regions + temperature scaling.
- `configs/ai.yaml`, `training.yaml`, `identity_signatures.yaml`, `model_thresholds.yaml` with safe defaults (`ai.enabled: false`).
- `src/fsoc_tracker/config/defaults.py` + `schema.py` extended to validate `ai.*`.

**Verification:** `pytest tests/unit/test_ai_types.py` passes; existing suite still green; app runs with `ai.enabled == false`.

---

## Phase 2 — Multi-Candidate Tracking

**Scope (Prompt Phase 2 / Plan Milestone 1):**

- Extend `perception/detector.py` to emit **all** valid blobs as `List[Candidate]` (keep single-`Detection` API for backward compat, add `detect_candidates()`).
- New `tracking/track_manager.py` (or extend `tracker.py`): per-candidate `TrackState`, Hungarian/nearest-neighbor association, missed-frame counters, decoy memory (never `brightest == primary`), creation/deletion.
- New `tracking/identity_state_machine.py` — Plan §7 states `SEARCHING → CANDIDATE_FOUND → IDENTITY_CHECKING → PRIMARY_CONFIRMED / DECOY_CONFIRMED / UNKNOWN`, gating PID.
- Safety: remember rejected decoys; prevent immediate re-selection.

**Verification:** unit tests for association + state transitions; scenario test "bright decoy ≠ primary"; `tests/integration/test_ai_pipeline.py` green; manual run shows multiple IDs in logs.

---

## Phase 3 — Training-Data Generation

**Scope (Plan §9.2 Steps 1-5 + Milestone 1):**

- `scripts/generate_training_data.py` drives `simulation.World` to render labelled frames/maps across noise/atmosphere/motion/occlusion axes.
- Outputs: `data/datasets/candidate_patches/*.jsonl + *.npy`, `data/datasets/track_sequences/*.jsonl`, `data/datasets/metadata/*` + `data/generated_scenarios/`.
- Each sample records seed, scenario, frame_id, timestamp, bbox, centroid, class label, primary/decoy identity, disturbance, trajectory, generator version (Prompt Phase 3).
- Scenario-level split by seed (1-70/71-85/86-100), no adjacent-frame leakage; reserve unseen disturbance conditions for testing.

**Verification:** dataset manifests exist; split integrity check; seed determinism test; no GT leaks to inference path (grep for `GroundTruth` in `ai/` must be empty).

---

## Phase 4 — MobileNetV3-Small Candidate Classifier

**Scope (Plan §9.1 Stage 1 / Milestone 2):**
- `src/fsoc_tracker/ai/candidate_model.py` (already scaffolded with heuristic) wired to real `torchvision` backbone when weights present.
- `src/fsoc_tracker/ai/training/train_candidate.py` + `scripts/train_candidate_classifier.py`: 64×64 + 9 num features → BEACON/DECOY/NOISE/UNKNOWN, weighted/focal loss, per-class metrics, confusion matrix, latency profiling.

**Verification:** val per-class precision/recall, false-primary rate, decoy rejection, UNKNOWN precision; model selection NOT on accuracy alone; inference latency budgeted.

---

## Phase 5 — GRU Temporal Identity Classifier

**Scope (Plan §9.1 Stage 2 / Milestone 3):**
- `src/fsoc_tracker/ai/identity_model.py` (1-layer GRU, hidden 64/128, 20-30 steps) + `training/train_identity.py` + `scripts/train_identity_model.py`.
- Initially freeze CNN, train GRU; optionally fine-tune jointly with lower LR. Sequence-level metrics: primary precision/recall, decoy rejection, false-lock, time-to-identify, switch count, calibration.

**Verification:** stable identity across sequence (low switch count); primary threshold ≥0.85 for N frames before `PRIMARY_CONFIRMED` (configurable, Prompt Phase 5).

---

## Phase 6 — Beacon Identity Characteristics

**Scope (Plan §8 / Prompt Phase 6):**
- Wire `signatures.py` (blink `10110010`, 12 Hz ±5%, shape/size, motion envelope, persistence) into GRU features + evidence panel.
- `configs/identity_signatures.yaml` governs primary vs decoy profiles; brightness alone never confirms.
- Optional spectral / challenge-response hooks (no hardware required for first cut).

**Verification:** ablation E (with vs without signature) shows false-lock reduction; UNKNOWN when evidence incomplete.

---

## Phase 7 — EKF-IMM & PID Integration

**Scope (Plan §11 / Prompt Phase 7 / Milestones 5-6):**
- `AIInferencePipeline` → `tracking/tracker.py`: confidence-aware `R` adaptation, innovation gating (`large innovation + low identity → reject`), IMM probs as GRU input, prediction-only during short loss, freeze/decay PID integral on `TARGET_LOST`, full PID only for `PRIMARY_CONFIRMED`, slew/saturation preserved.
- Timeout/failure fallback: high covariance + bounded search + log (never silent PRIMARY).
- Learned search-region ranking (optional, after deterministic spiral/raster baseline).

**Verification:** integration tests for pipeline → state machine → EKF → PID; acquire ≤2s, re-acquire ≤1s, RMSE ≤10px, loss <5% on independent test seeds; FPS ≥20 (30 native) profiling per Step 11.

---

## Phase 8 — UI Integration

**Scope (Plan §15-16 / Prompt Phase 8):**
- `ui/` updates: Camera FOV overlays per candidate (yellow raw / cyan predicted / green primary / red decoy / gray unknown / magenta GT debug-only), World FOV decoy trails, target-tracks table (ID/Class/Identity/Signature/State/Age/LastSeen), evidence panel (✓ reasons), live dashboard cards (Identity/Accuracy/Timing/Acquisition/Estimator/Controller), Control Deck tabs (Presets/Target/Decoys/Search/Detection/Identity/Camera/Estimator/Environment/Input-Logging).
- Top bar shows `TRACKING PRIMARY` vs `TRACKING UNCONFIRMED` vs `SEARCHING/RE-ACQUIRING/LOST` (never bare `LOCKED`), plus confidence, seed, FPS, model version; benchmark mode hides GT.

**Verification:** UI acceptance checklist (Plan §16.11) — smooth FOV, distinct colours, evidence visible, never show unconfirmed as primary, thresholds visible, exports work.

---

## Cross-cutting: Testing, Evaluation, Docs

- **Unit** — `tests/unit/test_ai_*.py` (features, signatures, thresholds, EKF gating, PID safety, config validation)
- **Model** — `tests/model/` (per-class, decoy rejection, UNKNOWN, calibration, false-lock, timeout)
- **Integration** — `tests/integration/test_ai_pipeline.py` (perception→tracker→MobileNet→GRU→state→EKF→PID, synthetic+MP4, UI snapshot, report export)
- **Scenarios** — `tests/scenarios/test_ai_decoy_rejection.py` (clean, multi-decoy, bright/centre-biased, crossing, bad signature, loss/FOV exit, fog/haze/low-light, jitter/platform/manoeuvre)
- **Docs** — `docs/ai_architecture.md`, `training_pipeline.md`, `identity_and_decoys.md`, `model_evaluation.md`, `deployment.md` (updated each phase); `README.md` installation + usage; `configs/*.yaml` documented.

---

## Execution order & dependencies

```
Phase 0 (done) → Phase 1 → Phase 2 → Phase 3 → Phase 4 ↔ Phase 5 → Phase 6 → Phase 7 → Phase 8
                        ↘ tests/docs continuous; model training (4-5) can overlap once data exists
```

No phase after Gate 1 starts implementation without the prior gate's approval when the prompt's gate policy is active.

---

## Branch workflow

- Active branch: `feature/ai-primary-target-identification`
- `main` is protected — no direct commits, no merge until user approves: implementation, test results, model results, benchmark results, documentation, known limitations, final change report (Prompt §4, §12).
- Every change is reproducible (fixed seeds, scenario-level splits, saved configs, metadata).

---

## Current status (all phases implemented)

- ✅ `src/fsoc_tracker/ai/` package with `types/features/signatures/candidate_model/identity_model/inference/thresholds/calibration/training/evaluation`
- ✅ `configs/ai.yaml`, `training.yaml`, `identity_signatures.yaml`, `model_thresholds.yaml`
- ✅ `scripts/generate_training_data.py`, `train_candidate_classifier.py`, `train_identity_model.py`, `evaluate_ai_models.py`, `calibrate_thresholds.py`, `export_models.py`
- ✅ `docs/ai_architecture.md`, `training_pipeline.md`, `identity_and_decoys.md`, `model_evaluation.md`, `deployment.md`
- ✅ `tests/unit/test_ai_types.py`, `tests/unit/test_ai_inference.py`, `tests/integration/test_ai_pipeline.py`, `tests/scenarios/test_ai_decoy_rejection.py`, `tests/model/test_ai_metrics.py`
- ✅ Phase 2-8 wired: multi-candidate detection + TrackManager + identity state machine + `ai.enabled` path in `ui/app.py` tick loop + EKF/PID safety integration
- ✅ Phase 4-5 training loops implemented (MobileNetV3-Small + GRU, focal/weighted losses, safety-aware model selection)
- ✅ Real dataset generated: 100 seeds (train 1-70 / val 71-85 / test 86-100), ~4.8k patches + 85 track sequences incl. hard negatives
- ✅ Models trained, calibrated and exported to ONNX (`models/*/​*.onnx`) — loaded by the runtime inference path when `ai.candidate_model_path` / `ai.identity_model_path` are configured
- ✅ Independent test-split metrics: primary precision/recall 1.0/1.0, decoy rejection 1.0, false-lock 0.0 (see `outputs/ai_eval/ai_metrics_test.json`)
- Remaining (Gate 4): full-scale dataset regeneration + retraining as hardware/data volume grows; larger val/test sequence pools; extended ablation automation
