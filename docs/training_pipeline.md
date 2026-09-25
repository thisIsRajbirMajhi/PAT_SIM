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

Reserve whole disturbance conditions for testing (e.g. train on Gaussian+haze, test on fog/rain).

## Hard negatives (substantial part of val/test)

Brighter decoy, centre-biased decoy, same size/shape, same trajectory, noise near EKF prediction, hidden primary under fog/haze/low-light, partial occlusion, crossing paths, decoy with nearly-correct blink pattern, short-lived noise blob.

## Commands

```bash
python scripts/generate_training_data.py   --config configs/training.yaml
python scripts/train_candidate_classifier.py
python scripts/train_identity_model.py
python scripts/calibrate_thresholds.py
python scripts/evaluate_ai_models.py --split test
python scripts/export_models.py --format onnx
```

Each run saves config snapshot, random seed, data version, model version and evaluation results.
