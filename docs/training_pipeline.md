# Training Pipeline

Reproducible two-stage pipeline (Plan §9.2):

```
Scenario generator (World + trajectories + disturbances)
  → Primary & decoy rendering
  → Classical candidate generation
  → Candidate labels + 64×64 patches  (labels: PRIMARY_TARGET / DECOY / NOISE / UNKNOWN)
  → MobileNetV3-Small training (weighted CE / focal loss)
  → Track-sequence construction (20-30 obs per track, with mask)
  → GRU identity training (PRIMARY / DECOY / UNKNOWN)
  → Threshold calibration (temperature scaling + sweep, Step 8)
  → EKF-IMM-PID integration tests
  → ONNX/TFLite export + FPS profiling (Step 11)
```

## Data split — no leakage

Split by scenario/seed, not by frame:

```
Training seeds   1-70
Validation seeds 71-85
Testing    seeds 86-100
```

Seeds >100 fall back to `seed % 3` distribution (distinct seeds, no frame reuse).
Reserve whole disturbance conditions for testing (e.g. train on Gaussian+haze, test on fog/rain).

## Hard negatives (substantial part of val/test)

Brighter decoy, centre-biased decoy, same size/shape, same trajectory, noise near EKF prediction, hidden primary under fog/haze/low-light, partial occlusion, crossing paths, decoy with nearly-correct blink pattern, short-lived noise blob.

## Commands — best-practice retrain

Do not use the `30×90` generator defaults (seeds 1-30 = train-only, no val/test).
Minimum viable is `100×60`; recommended for a non-tiny GRU dataset is `300×90`
(~14k patches / ~250 sequences, >100 train sequences so `train_identity.py` leaves
tiny-dataset mode):

```bash
python scripts/generate_training_data.py --config configs/training.yaml --num-scenarios 300 --frames-per-scenario 90 --seed-start 1
python scripts/train_candidate_classifier.py --config configs/training.yaml
python scripts/train_identity_model.py --config configs/training.yaml
python scripts/calibrate_thresholds.py --config configs/training.yaml
python scripts/evaluate_ai_models.py --config configs/training.yaml --split test --out outputs/ai_eval
python scripts/export_models.py --config configs/training.yaml --format onnx
# --quantize only after false_lock_rate < 0.02 is validated
```

Verify label balance before training:

```bash
python -c "import json,collections; [print(s,dict(collections.Counter(json.loads(l)['label'] for l in open(f'data/datasets/candidate_patches/{s}.jsonl')))) for s in ['train','val','test']]"
```

## Known data quirks

- `NOISE` patches are normally 0: the classical detector only emits bright blobs, so the
  `beacon_probability < 0.38 → NOISE` rule in `generate_training_data.py` rarely fires.
  Training runs as an effective 3-class problem; absent classes get neutral weight
  (`train_candidate.py` clipping) — this is expected, not a failure.
- GRU needs >100 train sequences. `100×60` yields only ~63/8/14 (train/val/test),
  forcing full-batch label-smoothing fallback with meaningless `1.0` val scores.
  Use `300×90` to exit tiny mode and require `val > 30` sequences before trusting metrics.

## Acceptance gates (before wiring models into the Deck)

- Candidate `BEACON F1 > 0.80`, `false_primary_rate < 0.05`, `decoy_rejection > 0.90`,
  `best_epoch > 10` (not 3), test `candidate precision ≥ 0.85`.
- GRU `primary_f1 > 0.90`, `false_lock_rate ≤ 0.02` on >30 val and >50 test sequences.
- Selection metric is safety-aware (`f1_beacon - 2*false_primary`), never accuracy alone.

Current baseline (2026-09-25, `100×60`): candidate `acc 0.72, BEACON P 0.80/R 0.77,
DECOY P 0.59/R 0.64, false_primary 0.127`; test `P 0.66 R 1.0 (489 TP / 255 FP)`.
Below gate — retrain per above before claiming `≥0.85` primary precision.

Each run saves config snapshot, random seed, data version, model version and evaluation results.
