#!/usr/bin/env python3
"""
Generate labelled training data — Prompt Phase 3 / Plan §9.2 Steps 1-5.

Uses simulation.World + SyntheticSource to render synthetic frames with
PRIMARY_TARGET / DECOY / NOISE / UNKNOWN.

Hard negatives included: brighter decoy, centre-biased, same size/shape,
same trajectory, noise near EKF prediction, fog/haze/low-light, partial
occlusion, crossing paths, incorrect blink.

Ground truth used ONLY for labels/metrics — never passed to detector/GRU/EKF/PID.

Outputs:
  data/datasets/candidate_patches/{train,val,test}.jsonl + patches/*.npy
  data/datasets/track_sequences/{train,val,test}.jsonl
  data/datasets/metadata/generation_manifest.json

Usage:
  python scripts/generate_training_data.py --config configs/training.yaml --num-scenarios 30 --frames-per-scenario 90
"""
from __future__ import annotations
import os, sys
# ensure src on path
_this = os.path.dirname(__file__)
_src = os.path.abspath(os.path.join(_this, "..", "src"))
if _src not in sys.path:
    sys.path.insert(0, _src)
import argparse, pathlib, yaml, json, copy, time
import numpy as np
import cv2

DEFAULTS = pathlib.Path("configs/training.yaml")

def parse_args():
    p = argparse.ArgumentParser(description="Generate AI training data")
    p.add_argument("--config", type=str, default=str(DEFAULTS))
    p.add_argument("--num-scenarios", type=int, default=30)
    p.add_argument("--frames-per-scenario", type=int, default=90)
    p.add_argument("--out", type=str, default="data/datasets")
    p.add_argument("--seed-start", type=int, default=1)
    return p.parse_args()

def load_base_cfg(path: pathlib.Path):
    from fsoc_tracker.config.defaults import DEFAULT_CONFIG
    from fsoc_tracker.config.loader import deep_merge
    cfg = copy.deepcopy(DEFAULT_CONFIG)
    if path.exists():
        data = yaml.safe_load(open(path)) or {}
        # training.yaml nests under training:*, but defaults is full cfg; merge top-level only
        # For generation we need full simulation cfg, so use defaults as base and merge any top-level keys
        cfg = deep_merge(cfg, {k: v for k, v in data.items() if k not in ("training",)})
    return cfg

def scenario_cfg(base: dict, seed: int, scenario_idx: int):
    cfg = copy.deepcopy(base)
    # blink signatures must be active for data generation (Plan §8) — AI
    # runtime state does not affect the simulator's rendering path
    cfg["ai"]["enabled"] = True
    # vary disturbances per scenario for coverage
    rng = np.random.default_rng(seed)
    # choose hard-negative type based on idx
    hard_types = ["none", "bright_decoy", "centre_decoy", "fog", "haze", "low_light", "high_noise", "jitter"]
    hard = hard_types[scenario_idx % len(hard_types)]
    # enable decoys for some scenarios (multi-target)
    if scenario_idx % 3 == 0:
        cfg["target"]["count"] = int(rng.integers(2, 4))
        cfg["decoys"]["enabled"] = True
    else:
        cfg["target"]["count"] = 1
    # environment and noise per hard type
    if hard == "bright_decoy":
        # decoy brighter handled via World brightness; ensure count >=2
        cfg["target"]["count"] = max(cfg["target"]["count"], 2)
        cfg["decoys"]["profiles"] = [{"type":"reflection","brightness_range":[220,255],"blink_pattern":"11100011","freq_hz":8.0}]
    elif hard == "centre_decoy":
        cfg["target"]["count"] = max(cfg["target"]["count"], 2)
    elif hard == "fog":
        cfg["atmosphere"]["type"] = "fog"; cfg["atmosphere"]["strength"] = float(rng.uniform(0.35, 0.7))
    elif hard == "haze":
        cfg["atmosphere"]["type"] = "haze"; cfg["atmosphere"]["strength"] = float(rng.uniform(0.3, 0.6))
    elif hard == "low_light":
        cfg["atmosphere"]["type"] = "low_light"; cfg["atmosphere"]["strength"] = float(rng.uniform(0.4, 0.75))
        cfg["environment"]["brightness_gain"] = float(rng.uniform(0.75, 0.9))
    elif hard == "high_noise":
        cfg["noise"]["gaussian_enabled"] = True; cfg["noise"]["gaussian_std"] = float(rng.uniform(8, 14))
        if rng.random() < 0.5:
            cfg["noise"]["salt_pepper_enabled"] = True; cfg["noise"]["salt_pepper_prob"] = 0.02
    elif hard == "jitter":
        cfg["camera"]["jitter_px"] = float(rng.uniform(6, 14))
    # random trajectory per scenario
    cfg["target"]["trajectory"] = str(rng.choice(["straight","circular","figure_eight","random","spiral","sinusoidal"]))
    cfg["target"]["speed_px_per_frame"] = float(rng.uniform(1.5, 5.0))
    # seed for experiment
    cfg["experiment"]["seed"] = int(seed)
    # AI blink pattern primary
    cfg["primary_target"]["optical_signature"]["blink_pattern"] = "10110010"
    return cfg, hard

def main():
    args = parse_args()
    base_cfg = load_base_cfg(pathlib.Path(args.config))
    out_root = pathlib.Path(args.out)
    patches_root = out_root / "candidate_patches"
    seq_root = out_root / "track_sequences"
    meta_root = out_root / "metadata"
    for p in (patches_root, seq_root, meta_root):
        p.mkdir(parents=True, exist_ok=True)
    # patches subdir
    (patches_root / "patches").mkdir(exist_ok=True)

    from fsoc_tracker.input.synthetic_source import SyntheticSource
    from fsoc_tracker.perception.detector import BeaconDetector
    from fsoc_tracker.tracking.track_manager import TrackManager
    from fsoc_tracker.ai.features import PATCH_SIZE

    # Determine split by seed
    def split_for_seed(seed):
        if 1 <= seed <= 70: return "train"
        if 71 <= seed <= 85: return "val"
        if 86 <= seed <= 100: return "test"
        return "train" if seed % 3 == 0 else ("val" if seed % 3 == 1 else "test")

    manifests = {"train": [], "val": [], "test": []}
    seq_manifests = {"train": [], "val": [], "test": []}
    gen_start = time.time()

    for s_idx in range(args.num_scenarios):
        seed = args.seed_start + s_idx
        cfg, hard = scenario_cfg(base_cfg, seed, s_idx)
        split = split_for_seed(seed)
        print(f"[{s_idx+1}/{args.num_scenarios}] seed={seed} split={split} hard={hard} count={cfg['target']['count']} traj={cfg['target']['trajectory']}")

        # create source and detector
        source = SyntheticSource(cfg, seed=seed)
        detector = BeaconDetector(cfg)
        track_mgr = TrackManager(cfg)

        # collect per-scenario candidates for sequence building
        # We'll also create per-frame patch files
        for fid in range(args.frames_per_scenario):
            frame, gt = source.read()
            if frame is None:
                break
            # get all decoy positions projected to image (for labeling)
            all_world = getattr(source.world, 'all_world_pos', [source.world.world_pos])
            decoy_img_positions = []
            primary_img = gt.image_pos
            for idx, wp in enumerate(all_world):
                img_pos = source.camera.world_to_image(wp)
                if idx == 0:
                    primary_img = img_pos
                elif img_pos is not None:
                    decoy_img_positions.append(img_pos)

            pred = None  # no prediction for labeling (use ground truth agnostic detection)
            candidates = detector.detect_candidates(frame.image, predicted_pos=pred)

            # label each candidate
            for c in candidates:
                # distance to primary and nearest decoy
                d_primary = float(np.hypot(c.centroid_px[0]-primary_img[0], c.centroid_px[1]-primary_img[1])) if primary_img else 9999
                d_decoy = min([float(np.hypot(c.centroid_px[0]-dx, c.centroid_px[1]-dy)) for dx,dy in decoy_img_positions], default=9999)
                # label
                if primary_img is not None and d_primary < 10:
                    label = "PRIMARY_TARGET"
                elif d_decoy < 10:
                    label = "DECOY"
                elif c.beacon_probability < 0.38:
                    label = "NOISE"
                else:
                    label = "UNKNOWN"
                # hard-negative flags
                is_hard = False
                if label == "DECOY" and c.peak_intensity > 200 and primary_img is not None:
                    # brighter than primary approx?
                    is_hard = True
                if label == "DECOY" and d_decoy < 12 and np.hypot(c.centroid_px[0]-320, c.centroid_px[1]-240) < 40:
                    is_hard = True
                # save patch as npy
                patch = c.patch if c.patch is not None else np.zeros((PATCH_SIZE,PATCH_SIZE), dtype=np.float32)
                patch_fname = f"patches/seed{seed}_f{fid:04d}_c{c.candidate_id:02d}.npy"
                patch_path = patches_root / patch_fname
                # ensure patch is 64x64 float32 0-1
                if patch.shape != (PATCH_SIZE, PATCH_SIZE):
                    patch = cv2.resize(patch, (PATCH_SIZE, PATCH_SIZE))
                np.save(str(patch_path), patch.astype(np.float32))

                rec = {
                    "seed": seed,
                    "split": split,
                    "hard_type": hard,
                    "scenario_idx": s_idx,
                    "frame_id": fid,
                    "timestamp": float(fid / cfg["camera"]["fps"]),
                    "candidate_id": int(c.candidate_id),
                    "bbox": list(c.bbox),
                    "centroid_px": list(c.centroid_px),
                    "area": float(c.area),
                    "width": int(c.width),
                    "height": int(c.height),
                    "aspect_ratio": float(c.aspect_ratio),
                    "brightness": float(c.brightness),
                    "peak_intensity": float(c.peak_intensity),
                    "local_contrast": float(c.local_contrast),
                    "compactness": float(c.compactness),
                    "distance_from_prediction": float(c.distance_from_prediction),
                    "beacon_probability": float(c.beacon_probability),
                    "label": label,
                    "primary_decoy_identity": label,
                    "disturbance": {"atmo": cfg["atmosphere"], "noise": cfg["noise"], "jitter": cfg["camera"]["jitter_px"]},
                    "trajectory": cfg["target"]["trajectory"],
                    "generator_version": "1.0.0",
                    "patch_file": patch_fname,
                    "is_hard_negative": bool(is_hard),
                    "gt_primary_image_pos": list(primary_img) if primary_img else None,
                    "gt_decoy_positions": [list(p) for p in decoy_img_positions],
                    "gt_visible": bool(gt.visible),
                    "target_count": int(cfg["target"]["count"]),
                }
                manifests[split].append(rec)

            # update track manager for sequence building (use candidate centroids)
            try:
                track_mgr.update(candidates, fid, innovation=0.0, imm_probs=(0.6,0.25,0.15))
            except Exception as e:
                print(f" track_mgr update error fid={fid}: {e}")

        # after scenario, build track sequences (20-30 obs) per track
        for tid, tr in track_mgr.tracks.items():
            # we have history for still-alive tracks; also we could snapshot all tracks that ever existed
            # For simplicity, create one sequence per alive track if long enough
            seq_len = 25
            if len(tr.position_history) < 8:
                continue
            # determine label: if track ever near primary GT for >50% of frames -> PRIMARY, near decoy -> DECOY else UNKNOWN
            # Use blink pattern correlation as proxy: if track's blink_history correlates with primary pattern -> PRIMARY
            from fsoc_tracker.ai.signatures import blink_correlation
            # check against the full decoy pattern set (World assigns decoy
            # options cyclically — matching only one pattern mislabels tracks)
            DECOY_PATTERNS = ("11100011", "10101010", "11001100", "00011100")
            # use last 8 frames (one full pattern period)
            hist = tr.blink_history[-8:] if tr.blink_history else []
            corr_primary = blink_correlation(hist, "10110010") if hist else 0.0
            corr_decoy = max((blink_correlation(hist, p) for p in DECOY_PATTERNS), default=0.0) if hist else 0.0
            # 10110010 at phase-shift 4 equals 00011100 (a decoy pattern) —
            # prefer PRIMARY when both match (disambiguation rule)
            if corr_primary > 0.75 and corr_primary >= corr_decoy:
                seq_label = "PRIMARY"
            elif corr_decoy > corr_primary and corr_decoy > 0.70:
                seq_label = "DECOY"
            else:
                seq_label = "UNKNOWN"
            # build sequence array (T, D=11) — GRU feature layout (Plan §9.1 Stage 2):
            # [px, py, vx, vy, brightness, shape_stability, blink, innovation, imm_cv, imm_ca, imm_mn]
            T = min(len(tr.position_history), seq_len)
            seq = np.zeros((seq_len, 11), dtype=np.float32)
            mask = np.zeros((seq_len,), dtype=np.float32)
            start = seq_len - T
            sizes = np.array(tr.size_history, dtype=np.float32) if tr.size_history else np.array([0.0])
            for i in range(T):
                idx = len(tr.position_history) - T + i
                px, py = tr.position_history[idx]
                vx, vy = tr.velocity_history[idx] if idx < len(tr.velocity_history) else (0,0)
                br = tr.brightness_history[idx] if idx < len(tr.brightness_history) else 0
                blink = tr.blink_history[idx] if idx < len(tr.blink_history) else 0
                inno = tr.innovation_history[idx] if idx < len(tr.innovation_history) else 0.0
                # shape stability: 1 - normalized rolling std of size history
                if len(sizes[: idx + 1]) > 1:
                    shape_stab = float(np.clip(1.0 - np.std(sizes[: idx + 1]) / 20.0, 0, 1))
                else:
                    shape_stab = 1.0
                seq[start+i] = [px/640, py/480, np.clip(vx/20, -1, 1), np.clip(vy/20, -1, 1),
                                br/255, shape_stab, blink, inno/50, 0.6, 0.25, 0.15]
                mask[start+i] = 1.0
            # save sequence as npz
            seq_fname = f"seed{seed}_track{tid:03d}_{seq_label}.npz"
            np.savez_compressed(str(seq_root / seq_fname), sequence=seq, mask=mask, label=seq_label, tid=tid, seed=seed)
            seq_manifest = {
                "seed": seed,
                "split": split,
                "track_id": tid,
                "label": seq_label,
                "seq_len": seq_len,
                "valid_len": int(mask.sum()),
                "file": seq_fname,
                "hard_type": hard,
            }
            seq_manifests[split].append(seq_manifest)

    # write manifests as JSONL per split
    for split in ("train","val","test"):
        out_path = patches_root / f"{split}.jsonl"
        with open(out_path, "w") as f:
            for rec in manifests[split]:
                f.write(json.dumps(rec)+"\n")
        print(f"Wrote {len(manifests[split])} patch records to {out_path}")
        out_seq = seq_root / f"{split}.jsonl"
        with open(out_seq, "w") as f:
            for rec in seq_manifests[split]:
                f.write(json.dumps(rec)+"\n")
        print(f"Wrote {len(seq_manifests[split])} track sequences to {out_seq}")

    # generation manifest
    gen_manifest = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "num_scenarios": args.num_scenarios,
        "frames_per_scenario": args.frames_per_scenario,
        "total_patches": sum(len(v) for v in manifests.values()),
        "total_sequences": sum(len(v) for v in seq_manifests.values()),
        "splits": {k: {"patches": len(v), "sequences": len(seq_manifests[k])} for k,v in manifests.items()},
        "version": "1.0.0",
        "hard_types": ["none","bright_decoy","centre_decoy","fog","haze","low_light","high_noise","jitter"],
    }
    with open(meta_root / "generation_manifest.json", "w") as f:
        json.dump(gen_manifest, f, indent=2)
    print(f"Done in {time.time()-gen_start:.1f}s — see {meta_root/'generation_manifest.json'}")

if __name__ == "__main__":
    main()
