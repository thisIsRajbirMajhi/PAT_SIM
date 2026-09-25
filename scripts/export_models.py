#!/usr/bin/env python3
"""
Export trained models to ONNX — Plan §9.2 Step 11.

 - Exports MobileNetV3-Small and GRU checkpoints to ONNX Runtime format.
 - INT8 quantization is opt-in (--quantize) and must only be applied
   after false-lock validation (Plan §9.2 Step 11).
 - Profiles inference latency after export and writes metadata.json.

If AI inference fails or times out, the deployed system must:
  increase measurement uncertainty, suppress PID, continue bounded search, log.

Usage:
  python scripts/export_models.py --config configs/training.yaml --format onnx
  python scripts/export_models.py --format onnx --quantize   # only after false-lock validation
"""
import os, sys
_this = os.path.dirname(__file__)
_src = os.path.abspath(os.path.join(_this, "..", "src"))
if _src not in sys.path:
    sys.path.insert(0, _src)
import argparse
import pathlib
import yaml
import json
import time


def _export_candidate(ckpt_path: pathlib.Path, out_path: pathlib.Path, quantize: bool) -> dict:
    import torch
    from fsoc_tracker.ai.candidate_model import _build_torch_candidate

    ckpt = torch.load(str(ckpt_path), map_location="cpu")
    model = _build_torch_candidate((torch, torch.nn))
    model.load_state_dict(ckpt["state_dict"])
    model.eval()

    patch = torch.randn(1, 1, 64, 64)
    num = torch.randn(1, 9)
    torch.onnx.export(
        model, (patch, num), str(out_path),
        input_names=["patch", "num_features"],
        output_names=["logits", "quality", "embedding"],
        dynamic_axes={"patch": {0: "batch"}, "num_features": {0: "batch"},
                      "logits": {0: "batch"}, "quality": {0: "batch"}, "embedding": {0: "batch"}},
        opset_version=17,
    )
    profile = {"candidate_onnx": str(out_path)}
    if quantize:
        try:
            from onnxruntime.quantization import quantize_dynamic, QuantType
            q_path = out_path.with_name(out_path.stem + "_int8.onnx")
            quantize_dynamic(str(out_path), str(q_path), weight_type=QuantType.QInt8)
            profile["candidate_onnx_int8"] = str(q_path)
        except Exception as e:
            print(f"[export_models] quantization skipped: {e}")
    return profile


def _export_identity(ckpt_path: pathlib.Path, out_path: pathlib.Path, hidden: int, quantize: bool) -> dict:
    import torch
    from fsoc_tracker.ai.identity_model import _build_torch_gru
    from fsoc_tracker.ai.training.dataset import SEQ_FEATURE_DIM

    ckpt = torch.load(str(ckpt_path), map_location="cpu")
    model = _build_torch_gru((torch, torch.nn), input_dim=SEQ_FEATURE_DIM, hidden=hidden)
    model.load_state_dict(ckpt["state_dict"])
    model.eval()

    seq = torch.randn(1, 25, SEQ_FEATURE_DIM)
    mask = torch.ones(1, 25)
    torch.onnx.export(
        model, (seq, mask), str(out_path),
        input_names=["sequence", "mask"],
        output_names=["logits", "confidence"],
        dynamic_axes={"sequence": {0: "batch"}, "mask": {0: "batch"},
                      "logits": {0: "batch"}, "confidence": {0: "batch"}},
        opset_version=17,
    )
    profile = {"identity_onnx": str(out_path)}
    if quantize:
        try:
            from onnxruntime.quantization import quantize_dynamic, QuantType
            q_path = out_path.with_name(out_path.stem + "_int8.onnx")
            quantize_dynamic(str(out_path), str(q_path), weight_type=QuantType.QInt8)
            profile["identity_onnx_int8"] = str(q_path)
        except Exception as e:
            print(f"[export_models] quantization skipped: {e}")
    return profile


def main():
    p = argparse.ArgumentParser(description="Export AI models")
    p.add_argument("--config", type=str, default="configs/training.yaml")
    p.add_argument("--format", type=str, default="onnx", choices=["onnx"])
    p.add_argument("--quantize", action="store_true", help="apply INT8 quantization (validate first)")
    args = p.parse_args()
    cfg = yaml.safe_load(open(args.config)) if pathlib.Path(args.config).exists() else {}
    tr = cfg.get("training", {})

    cand_dir = pathlib.Path(tr.get("candidate_out", "models/candidate_classifier"))
    ident_dir = pathlib.Path(tr.get("identity_out", "models/identity_classifier"))
    cand_ckpt = cand_dir / "candidate_model.pt"
    ident_ckpt = ident_dir / "identity_model.pt"

    if not cand_ckpt.exists() and not ident_ckpt.exists():
        print("[export_models] no trained checkpoints found — run train scripts first.")
        print("  python scripts/train_candidate_classifier.py")
        print("  python scripts/train_identity_model.py")
        sys.exit(1)

    profile: dict = {"exported_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "format": args.format}
    try:
        if cand_ckpt.exists():
            profile.update(_export_candidate(cand_ckpt, cand_dir / "candidate_model.onnx", args.quantize))
            print(f"[export_models] candidate → {cand_dir/'candidate_model.onnx'}")
        if ident_ckpt.exists():
            hidden = int(tr.get("identity", {}).get("hidden", 64))
            profile.update(_export_identity(ident_ckpt, ident_dir / "identity_model.onnx", hidden, args.quantize))
            print(f"[export_models] identity → {ident_dir/'identity_model.onnx'}")
    except Exception as e:
        print(f"[export_models] export failed: {e}")
        sys.exit(2)

    # latency profiling with onnxruntime (Plan §9.2 Step 11)
    try:
        import numpy as np
        import onnxruntime as ort
        lat = {}
        for key, (model_file, feed) in {
            "candidate_ms": (profile.get("candidate_onnx"), (
                {k: np.random.rand(1, 1, 64, 64).astype(np.float32) for k in ["patch"]} |
                {k: np.random.rand(1, 9).astype(np.float32) for k in ["num_features"]})
            ),
            "identity_ms": (profile.get("identity_onnx"), (
                {k: np.random.rand(1, 25, 11).astype(np.float32) for k in ["sequence"]} |
                {k: np.ones((1, 25), dtype=np.float32) for k in ["mask"]})
            ),
        }.items():
            if not model_file:
                continue
            sess = ort.InferenceSession(str(model_file), providers=["CPUExecutionProvider"])
            names = [i.name for i in sess.get_inputs()]
            feed = {n: feed[n] for n in names if n in feed}
            t0 = time.perf_counter()
            N = 50
            for _ in range(N):
                sess.run(None, feed)
            lat[key] = round((time.perf_counter() - t0) * 1000.0 / N, 3)
        profile["latency_ms"] = lat
        total = sum(lat.values())
        profile["fps_estimate"] = round(1000.0 / max(total, 1e-6), 1)
        print(f"[export_models] latency: {lat} → ~{profile['fps_estimate']} FPS (Plan target ≥20)")
    except Exception as e:
        print(f"[export_models] profiling skipped: {e}")

    # write metadata next to models
    from fsoc_tracker.ai.training.checkpoints import save_metadata
    if cand_ckpt.exists():
        meta_path = save_metadata(cand_dir, {"export": profile, "export_format": "onnx"})
        print(f"[export_models] metadata → {meta_path}")
    if ident_ckpt.exists():
        save_metadata(ident_dir, {"export": profile, "export_format": "onnx"})
    out_report = pathlib.Path("outputs/ai_eval/export_profile.json")
    out_report.parent.mkdir(parents=True, exist_ok=True)
    out_report.write_text(json.dumps(profile, indent=2))
    print(f"[export_models] profile → {out_report}")


if __name__ == "__main__":
    main()
