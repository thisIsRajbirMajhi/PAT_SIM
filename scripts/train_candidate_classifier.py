#!/usr/bin/env python3
"""
Train Stage-1 MobileNetV3-Small — Prompt Phase 4 / Plan §9.2 Step 6.

Usage:
  python scripts/train_candidate_classifier.py --config configs/training.yaml
"""
import argparse
import pathlib
import yaml


def main():
    p = argparse.ArgumentParser(description="Train candidate classifier")
    p.add_argument("--config", type=str, default="configs/training.yaml")
    args = p.parse_args()
    cfg = yaml.safe_load(open(args.config)) if pathlib.Path(args.config).exists() else {}
    from fsoc_tracker.ai.training.train_candidate import train
    summary = train(cfg)
    print("[train_candidate] summary:", summary)


if __name__ == "__main__":
    main()
