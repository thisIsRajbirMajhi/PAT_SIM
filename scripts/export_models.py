#!/usr/bin/env python3
"""
Export trained models to ONNX / TFLite — Plan §9.2 Step 11.

 - Exports MobileNetV3-Small and GRU to ONNX Runtime format.
 - Applies INT8 quantization only after false-lock validation.
 - Profiles candidate-generation, MobileNet, GRU, EKF-IMM, PID, total latency.

If AI inference fails or times out, the deployed system must:
  increase measurement uncertainty, suppress PID, continue bounded search, log.

Usage:
  python scripts/export_models.py --config configs/training.yaml --format onnx
"""
import argparse
import pathlib
import yaml


def main():
    p = argparse.ArgumentParser(description="Export AI models")
    p.add_argument("--config", type=str, default="configs/training.yaml")
    p.add_argument("--format", type=str, default="onnx", choices=["onnx", "tflite"])
    p.add_argument("--quantize", action="store_true", help="apply INT8 quantization (validate first)")
    args = p.parse_args()
    cfg = yaml.safe_load(open(args.config)) if pathlib.Path(args.config).exists() else {}
    print(f"[export_models] stub — would export to {args.format} (quantize={args.quantize})")
    print("  See docs/deployment.md for FPS targets: ≥20 FPS, 30 FPS native where possible.")


if __name__ == "__main__":
    main()
