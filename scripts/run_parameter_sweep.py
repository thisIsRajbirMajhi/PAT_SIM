#!/usr/bin/env python3
"""
Parameter sweep for robustness testing — runs disturbance matrix and reports pass/fail.

Matrix per Implementation Plan §8: clear baseline, each noise separately, combined lows/medium/max,
jitter 0/moderate/±20, platform speeds, atmosphere presets, target speeds near limit, edge starts.

Saves a summary CSV in outputs/runs/sweep_<timestamp>/sweep_summary.csv
"""
import argparse, os, sys, itertools, csv, time, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from fsoc_tracker.config.loader import load_config
from fsoc_tracker.input.synthetic_source import SyntheticSource
from fsoc_tracker.perception.detector import BeaconDetector
from fsoc_tracker.tracking.tracker import Tracker
from fsoc_tracker.control.camera_controller import CameraController
from fsoc_tracker.evaluation.metrics import MetricsCollector

def run_one(cfg, frames=180):
    src = SyntheticSource(cfg, seed=cfg["experiment"]["seed"])
    det = BeaconDetector(cfg)
    trk = Tracker(cfg)
    ctrl = CameraController(cfg)
    mc = MetricsCollector()
    mc.start_run()
    mc.input_fps = float(cfg["camera"]["fps"])
    import time as tm
    for i in range(frames):
        f, gt = src.read()
        t0 = tm.perf_counter()
        d = det.detect(f.image, predicted_pos=trk.get_predicted_pixel())
        est = trk.step(d, f)
        cmd = ctrl.step(est, dt=1/float(cfg["camera"]["fps"]))
        src.apply_camera_command(cmd.pan_rate, cmd.tilt_rate, 1/float(cfg["camera"]["fps"]))
        proc_ms = (tm.perf_counter() - t0)*1000
        mc.update(f.frame_id, f.timestamp, d.valid, est, gt, proc_ms, 30, cmd.pan_rate, cmd.tilt_rate, detection_confidence=d.confidence, saturated=cmd.saturated)
    return mc.summary()

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=str, default="outputs/runs")
    parser.add_argument("--frames", type=int, default=180)
    args = parser.parse_args()

    base = load_config()
    # Define sweep: list of (name, overrides)
    sweeps = [
        ("clear_baseline", {}),
        ("gauss_10", {"noise": {"gaussian_enabled": True, "gaussian_std": 10}}),
        ("gauss_20", {"noise": {"gaussian_enabled": True, "gaussian_std": 20}}),
        ("snp_10pct", {"noise": {"salt_pepper_enabled": True, "salt_pepper_prob": 0.10}}),
        ("poisson", {"noise": {"poisson": True}}),
        ("combined_low", {"noise": {"gaussian_enabled": True, "gaussian_std": 5, "salt_pepper_enabled": True, "salt_pepper_prob": 0.02}}),
        ("combined_max", {"noise": {"gaussian_enabled": True, "gaussian_std": 14, "salt_pepper_enabled": True, "salt_pepper_prob": 0.04, "poisson": True}}),
        ("jitter_0", {"camera": {"jitter_px": 0}}),
        ("jitter_8", {"camera": {"jitter_px": 8}}),
        ("jitter_20", {"camera": {"jitter_px": 20}}),
        ("haze_03", {"atmosphere": {"type": "haze", "strength": 0.3}}),
        ("fog_05", {"atmosphere": {"type": "fog", "strength": 0.5}}),
        ("rain_04", {"atmosphere": {"type": "rain", "strength": 0.4}}),
        ("platform_linear_5", {"platform": {"type": "linear", "speed_px_per_frame": 5}}),
        ("platform_spiral_5", {"platform": {"type": "spiral", "speed_px_per_frame": 5}}),
        ("target_fast_8", {"target": {"speed_px_per_frame": 8}}),
        ("stars_on", {"environment": {"stars_enabled": True, "stars_density": 0.001}}),
        ("vignetting_on", {"environment": {"vignetting_enabled": True}}),
    ]

    import datetime
    ts = datetime.datetime.now().strftime("%Y-%m-%dT%H%M%SZ")
    out_dir = os.path.join(args.output, f"sweep_{ts}")
    os.makedirs(out_dir, exist_ok=True)
    csv_path = os.path.join(out_dir, "sweep_summary.csv")
    print(f"[Sweep] {len(sweeps)} scenarios → {csv_path}")

    with open(csv_path, "w", newline="") as csvf:
        fieldnames = ["scenario","rmse","mean","max","p95","loss_pct","lock_pct","acq_s","reacq_mean","fps","frames","pass_rmse","pass_loss","pass_acq","overall"]
        w = csv.DictWriter(csvf, fieldnames=fieldnames)
        w.writeheader()
        for name, over in sweeps:
            cfg = load_config()
            # deep merge overrides
            for k, v in over.items():
                if isinstance(v, dict):
                    cfg[k].update(v)
                else:
                    cfg[k] = v
            summ = run_one(cfg, frames=args.frames)
            row = {
                "scenario": name,
                "rmse": f"{summ['rmse_px']:.2f}",
                "mean": f"{summ['mean_error_px']:.2f}",
                "max": f"{summ['max_error_px']:.2f}",
                "p95": f"{summ['p95_error_px']:.2f}",
                "loss_pct": f"{summ['target_loss_pct']:.1f}",
                "lock_pct": f"{summ['lock_retention_pct']:.1f}",
                "acq_s": f"{summ['acquisition_time_s']:.3f}" if summ['acquisition_time_s'] else "—",
                "reacq_mean": f"{summ['reacquisition_mean_s']:.3f}" if summ['reacquisition_mean_s'] else "—",
                "fps": f"{summ['avg_fps']:.1f}",
                "frames": summ['total_frames'],
                "pass_rmse": summ['rmse_px'] <= 10,
                "pass_loss": summ['target_loss_pct'] < 5,
                "pass_acq": (summ['acquisition_time_s'] or 999) <= 2.0,
                "overall": (summ['rmse_px']<=10 and summ['target_loss_pct']<5)
            }
            w.writerow(row)
            print(f"  {name:20} rmse {row['rmse']:>5} loss {row['loss_pct']:>5}% acq {row['acq_s']:>6} {'PASS' if row['overall'] else 'FAIL'}")

    print(f"[Sweep] Done → {csv_path}")

if __name__ == "__main__":
    main()
