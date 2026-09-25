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

Run: `python scripts/evaluate_ai_models.py --split test`
