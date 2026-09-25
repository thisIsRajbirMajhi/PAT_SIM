#!/usr/bin/env python3
"""
Generate labelled training data — Prompt Phase 3 / Plan §9.2 Steps 1-5.

Uses the existing simulation.World + noise/atmosphere pipeline to render
synthetic frames with PRIMARY_TARGET / DECOY / NOISE / UNKNOWN.

Each frame saves: frame_id, timestamp, bounding boxes, centroid,
class label, primary/decoy identity, trajectory, noise/atmosphere,
camera jitter, platform motion, random seed, generator version.

Hard negatives (§9.2 Step 2 + §10):
  1. decoy brighter than primary, 2. nearer centre, 3. same size,
  4. same trajectory, 5. noise near EKF prediction, 6. primary under
  fog/haze/low-light, 7. partial occlusion, 8. crossing paths, etc.

Ground truth is used ONLY for labels and metrics — never passed
to the detector/GRU/EKF/PID at inference.

Usage:
  python scripts/generate_training_data.py --config configs/training.yaml --num-scenarios 100
"""
from __future__ import annotations

import argparse
import pathlib
import yaml

DEFAULTS = pathlib.Path("configs/training.yaml")


def parse_args():
    p = argparse.ArgumentParser(description="Generate AI training data")
    p.add_argument("--config", type=str, default=str(DEFAULTS))
    p.add_argument("--num-scenarios", type=int, default=100, help="one scenario per seed")
    p.add_argument("--frames-per-scenario", type=int, default=180)
    p.add_argument("--out", type=str, default="data/datasets")
    return p.parse_args()


def main():
    args = parse_args()
    cfg = {}
    if pathlib.Path(args.config).exists():
        cfg = yaml.safe_load(open(args.config)) or {}
    print(f"[generate_training_data] stub — would generate {args.num_scenarios} scenarios "
          f"({args.frames_per_scenario} frames each) into {args.out}")
    print("  Implement: World rendering → classical candidate generation → 64×64 patch crop "
          "with border padding → track-sequence builder (20-30 obs) → JSONL manifests.")
    print("  See docs/training_pipeline.md for full contract.")

if __name__ == "__main__":
    main()
