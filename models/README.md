# Models

- `candidate_classifier/` — Stage-1 MobileNetV3-Small weights (`.pt` / `.onnx`), `metadata.json`, `train_summary.json`
- `identity_classifier/` — Stage-2 GRU weights, same companion files
- `metadata/` — cross-model manifests (dataset version, thresholds, FPS profile)

All files are populated by `scripts/train_*` and `scripts/export_models.py`.
Tracked as `.gitkeep` until first training run.

Enable in `configs/ai.yaml` (or Control Deck → AI System → §8 AI Runtime → Apply Active Mode):

```yaml
ai:
  enabled: true
  candidate_model_path: "models/candidate_classifier/candidate_model.onnx"
  identity_model_path: "models/identity_classifier/identity_model.onnx"
```

File names are `candidate_model.onnx` / `identity_model.onnx` (not `best.onnx`).
Empty path = safe heuristic fallback (`model_version="heuristic"`, Dashboard shows `heuristic`).
`ai.enabled=true` alone only activates the pipeline; learned weights load only when both paths point at existing `.onnx`/`.pt` files.
