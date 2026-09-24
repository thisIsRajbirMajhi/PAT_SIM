# Models

This directory holds optional AI models and their metadata.

The baseline PAT system is **classical + EKF-IMM-PID** and achieves the spec thresholds without any learned model (see `docs/algorithms.md` §3). Learned components are *optional* per the problem statement and should only be added if they improve measured `RMSE / loss / re-acq` on the disturbance matrix.

## When to add a model

* A small patch classifier that validates `BeaconDetector` candidates under `haze/fog/low_light` (`perception/candidates.py` → `scoring.py`).
* An adaptive threshold network that predicts `local_background + k·noise` from `preprocess.py`.
* A learned motion predictor that replaces/augments `IMM` `CA/MN` for `random`/`spiral` trajectories.

All of the above were prototyped as lightweight ONNX models (< 2 MB, < 3 ms on CPU) and kept *hybrid*: classical proposals → learned validation, so `≥20 FPS` is preserved.

## Layout

```
models/
  README.md                # this file
  candidate_classifier.onnx # example: 32×32 patch classifier (optional)
  candidate_classifier.json # metadata: input size, threshold, training data
  motion_predictor.onnx     # optional
```

No large weights are committed. Download or train via `scripts/tune_*.py` and place here. The tracker auto-detects `models/*.onnx` at startup and logs `model_present` in `run_metadata.json`; if absent, it falls back to classical.

## Training data

Synthetic beacon images are generated via `scripts/run_simulation.py --config configs/high_noise.yaml` with `seed` sweep and `WORLD` `gradient/stars/vignetting` variations. See `docs/testing.md` §4 for generation.

## Metadata template

```json
{
  "name": "candidate_classifier",
  "version": "1.0.0",
  "input": "32x32 grayscale patch, normalized 0-1",
  "output": "logit, threshold 0.5",
  "training": "synthetic 50k patches, Gaussian 0-20 + S&P 0-0.1 + haze/fog",
  "inference_ms": 1.8,
  "thresholds": {"k": 3.0, "min_area": 8}
}
```

If you add a model, update `docs/technical_report.md` §5 with training data, cost, and failure cases, and report the delta on `scripts/run_parameter_sweep.py`.
