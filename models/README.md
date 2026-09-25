# Models

- `candidate_classifier/` — Stage-1 MobileNetV3-Small weights (`.pt` / `.onnx`), `metadata.json`, `train_summary.json`
- `identity_classifier/` — Stage-2 GRU weights, same companion files
- `metadata/` — cross-model manifests (dataset version, thresholds, FPS profile)

All files are populated by `scripts/train_*` and `scripts/export_models.py`.
Tracked as `.gitkeep` until first training run.

Enable in `configs/ai.yaml`:

```yaml
ai:
  enabled: true
  candidate_model_path: "models/candidate_classifier/best.onnx"
  identity_model_path: "models/identity_classifier/best.onnx"
```
