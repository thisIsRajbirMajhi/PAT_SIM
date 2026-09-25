# Model Evaluation (Plan §14)

## Detection metrics

precision, recall, false-positive rate, missed-detection rate, candidate processing time.

## Identification metrics

primary precision, primary recall, decoy rejection rate, **false-lock rate** (most important), time-to-identify, identity-switch count, unknown-decision rate, confidence calibration (ECE).

## End-to-end metrics (acceptance criteria — Prompt §9)

```
Acquisition time    ≤2s
Re-acquisition time ≤1s
Tracking error      ≤10px
Target loss         <5%
Processing speed    ≥20 FPS (30 FPS native where possible)
```

Also report: primary precision/recall, decoy rejection, false-lock rate, identity switches, AI latency, total frame latency, dropped frames.

## Ablation (Plan §9.2 Step 9)

```
A. Classical only
B. Detector + MobileNetV3-Small
C. B + motion features
D. +GRU temporal model
E. +coded blinking / modulation signature
F. Full + EKF-IMM integration
```

Do not claim success until metrics are measured on independent test scenarios (seeds 86-100) with unseen disturbance conditions.

Run: `python scripts/evaluate_ai_models.py --config configs/training.yaml --split test --out outputs/ai_eval`

## Current baseline (2026-09-25, 100×60 data)

- Candidate (val): `acc 0.72, BEACON P 0.80/R 0.77, DECOY P 0.59/R 0.64, NOISE/UNKNOWN 0.0, false_primary 0.127, decoy_reject 0.64` — below gate.
- Candidate (test): `P 0.66 R 1.0 (489 TP / 255 FP)` — below `≥0.85` preset target.
- Identity: `train 63 / val 8 / test 14` seqs, `1.0` scores statistically meaningless (tiny-dataset fallback).
- Gate before use: `BEACON F1 > 0.80`, `false_primary < 0.05`, `decoy_reject > 0.90`, GRU `primary_f1 > 0.90` on >30 val seqs. Retrain with `300×90` per `docs/training_pipeline.md`.

## AI ON vs learned models

`ai.enabled=true` (Control Deck AI mode) only activates the pipeline. Learned MobileNet+GRU
run only when `ai.candidate_model_path` and `ai.identity_model_path` point at real
`candidate_model.onnx` / `identity_model.onnx` files; otherwise the Dashboard shows
`model_ver=heuristic` (safe brightness/compactness + blink voter, conservative UNKNOWN).
