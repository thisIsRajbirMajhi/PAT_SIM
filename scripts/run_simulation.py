#!/usr/bin/env python3
"""
Run a synthetic PAT simulation with configurable scenario and auto-generated performance logs.

Usage:
    python scripts/run_simulation.py --trajectory circular --duration 30 --seed 42 --output outputs/runs/manual
    python scripts/run_simulation.py --config configs/high_noise.yaml

This script is headless (no GUI) and is suitable for batch evaluation and CI.
It uses the same pipeline as the GUI: World -> VirtualCamera -> Detector -> Tracker (EKF-IMM) -> PID -> Metrics -> AutoLogger.
"""
import argparse, os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from fsoc_tracker.config.loader import load_config
from fsoc_tracker.input.synthetic_source import SyntheticSource
from fsoc_tracker.perception.detector import BeaconDetector
from fsoc_tracker.tracking.tracker import Tracker
from fsoc_tracker.control.camera_controller import CameraController
from fsoc_tracker.evaluation.metrics import MetricsCollector
from fsoc_tracker.evaluation.auto_logger import RobustPerfLogger
import time

def main():
    parser = argparse.ArgumentParser(description="FSOC Synthetic Simulation Runner")
    parser.add_argument("--config", type=str, default=None, help="YAML config override")
    parser.add_argument("--trajectory", type=str, choices=["straight","circular","figure_eight","random","spiral","sinusoidal","user-defined"], default=None)
    parser.add_argument("--duration", type=float, default=None, help="seconds")
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument("--output", type=str, default="outputs/runs")
    parser.add_argument("--fps", type=int, default=None)
    args = parser.parse_args()

    overrides = {}
    if args.trajectory:
        overrides = {"target": {"trajectory": args.trajectory}}
    cfg = load_config(args.config, overrides=overrides)
    if args.duration is not None:
        cfg["experiment"]["duration_s"] = float(args.duration)
    if args.seed is not None:
        cfg["experiment"]["seed"] = int(args.seed)
    if args.fps is not None:
        cfg["camera"]["fps"] = int(args.fps)

    print(f"[Runner] Trajectory={cfg['target']['trajectory']} Duration={cfg['experiment']['duration_s']}s Seed={cfg['experiment']['seed']} FPS={cfg['camera']['fps']}")
    src = SyntheticSource(cfg, seed=cfg["experiment"]["seed"])
    det = BeaconDetector(cfg)
    trk = Tracker(cfg)
    ctrl = CameraController(cfg)
    metrics = MetricsCollector()
    logger = RobustPerfLogger(base_dir=args.output, metrics_collector=metrics)

    metrics.start_run()
    logger.begin_run(cfg)
    metrics.input_fps = float(cfg["camera"]["fps"])

    t0 = time.perf_counter()
    frame_n = 0
    while True:
        f, gt = src.read()
        if f is None:
            break
        det_start = time.perf_counter()
        d = det.detect(f.image, predicted_pos=trk.get_predicted_pixel())
        est = trk.step(d, f)
        cmd = ctrl.step(est, dt=1/float(cfg["camera"]["fps"]))
        src.apply_camera_command(cmd.pan_rate, cmd.tilt_rate, 1/float(cfg["camera"]["fps"]))
        proc_ms = (time.perf_counter() - det_start) * 1000
        # Smooth FPS is not needed headless, use input fps
        logger.log_frame(f.frame_id, f.timestamp, d.valid, est, gt, proc_ms, float(cfg["camera"]["fps"]), cmd.pan_rate, cmd.tilt_rate,
                         detection_confidence=d.confidence, saturated=cmd.saturated, input_fps=float(cfg["camera"]["fps"]))
        frame_n += 1
        if f.timestamp >= float(cfg["experiment"]["duration_s"]):
            break
        if frame_n % 90 == 0:
            print(f"  Frame {frame_n} t={f.timestamp:.1f}s state={est.tracking_state.value} err={metrics.errors[-1] if metrics.errors else 0:.1f}")

    summary, run_dir = logger.end_run()
    if summary:
        print(f"\n[Runner] Completed {frame_n} frames in {time.perf_counter()-t0:.1f}s")
        print(f"  RMSE {summary['rmse_px']:.2f} px (≤10 {'PASS' if summary['rmse_px']<=10 else 'FAIL'})")
        print(f"  Loss {summary['target_loss_pct']:.1f}% (<5 {'PASS' if summary['target_loss_pct']<5 else 'FAIL'})")
        print(f"  Acq {summary['acquisition_time_s']}")
        print(f"  Logs: {os.path.abspath(run_dir)}")
        print(f"  Overall: {'PASS' if summary['rmse_px']<=10 and summary['target_loss_pct']<5 else 'FAIL'}")
    else:
        print("[Runner] No summary (no frames)")

if __name__ == "__main__":
    main()
