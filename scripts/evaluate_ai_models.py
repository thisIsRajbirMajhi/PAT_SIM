#!/usr/bin/env python3
"""
Evaluate AI models — Prompt Phase 7 / Plan §14.

Reports: candidate precision/recall, primary precision/recall,
decoy rejection, false-primary lock rate, identity switches,
time-to-identify, calibration (ECE), latency, FPS impact.

Also runs ablation variants A-F (Plan §9.2 Step 9):
  A classical only, B +MobileNet, C +motion, D +GRU, E +signature, F full+EKF-IMM

Usage:
  python scripts/evaluate_ai_models.py --config configs/training.yaml --split test
"""
import argparse
import pathlib
import yaml


def main():
    p = argparse.ArgumentParser(description="Evaluate AI models")
    p.add_argument("--config", type=str, default="configs/training.yaml")
    p.add_argument("--split", type=str, default="test", choices=["train", "val", "test"])
    p.add_argument("--out", type=str, default="outputs/ai_eval")
    args = p.parse_args()
    cfg = yaml.safe_load(open(args.config)) if pathlib.Path(args.config).exists() else {}
    print(f"[evaluate_ai_models] stub — would evaluate split={args.split} → {args.out}")
    print("  See docs/model_evaluation.md for metric definitions and pass/fail gates.")


if __name__ == "__main__":
    main()
