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

Preferred: Control Deck → `◉ AI System` → §8 AI Runtime → set both model paths → `Apply Active Mode` → RUN.
`Apply` is required — just switching tabs does not send the staged config (`control_deck.py:_apply`,
`app.py` reads `cfg["ai"]["enabled"]` only after apply).

Equivalent file edit in `configs/ai.yaml`:

```yaml
ai:
  enabled: true
  candidate_model_path: "models/candidate_classifier/candidate_model.onnx"
  identity_model_path: "models/identity_classifier/identity_model.onnx"
```

Notes:
- Actual export names are `candidate_model.onnx` / `identity_model.onnx` (not `best.onnx`).
- `ai.enabled=true` alone only activates `AIInferencePipeline`; learned MobileNetV3-Small + GRU
  load only when both paths exist. Empty/missing path = heuristic fallback
  (`model_version="heuristic"`), never a silent PRIMARY.
- AI-portion checkbox `8 · AI Runtime → AI Identification Enabled` is the same `ai.enabled` flag.
  Unchecked shows `AI OFF (staged but disabled)` even with the AI tab active.
- Deterministic mode forces `ai.enabled=false` by design.
