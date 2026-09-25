# Deployment

## Export

```bash
python scripts/export_models.py --format onnx          # CPU / edge
python scripts/export_models.py --format tflite --quantize   # only after false-lock validation
```

Exports go to `models/candidate_classifier/*.onnx` and `models/identity_classifier/*.onnx`.

## Profiling (per Plan §9.2 Step 11)

Profile separately:

```
candidate-generation time
MobileNet inference time
GRU inference time
EKF-IMM time
PID time
total frame latency
```

Targets: ≥20 FPS, 30 FPS native where possible.

## Runtime fallback (safety)

If AI inference fails or times out:

```
increase measurement uncertainty
stop aggressive PID action
maintain bounded search or prediction
log the AI failure
```

Never treat an AI failure as PRIMARY_CONFIRMED.

## Enabling AI

Set in `configs/ai.yaml`:

```yaml
ai:
  enabled: true
  candidate_model_path: "models/candidate_classifier/best.onnx"
  identity_model_path: "models/identity_classifier/best.onnx"
```

With `enabled: false` the system runs exactly as before (classical detector → EKF-IMM → PID).
