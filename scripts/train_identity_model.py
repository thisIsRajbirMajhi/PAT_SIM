#!/usr/bin/env python3
"""
Train Stage-2 GRU identity classifier — Prompt Phase 5 / Plan §9.2 Step 7.

Usage:
  python scripts/train_identity_model.py --config configs/training.yaml
"""
import argparse
import pathlib
import yaml


def main():
    p = argparse.ArgumentParser(description="Train GRU identity classifier")
    p.add_argument("--config", type=str, default="configs/training.yaml")
    args = p.parse_args()
    cfg = yaml.safe_load(open(args.config)) if pathlib.Path(args.config).exists() else {}
    from fsoc_tracker.ai.training.train_identity import train
    summary = train(cfg)
    print("[train_identity] summary:", summary)


if __name__ == "__main__":
    main()
