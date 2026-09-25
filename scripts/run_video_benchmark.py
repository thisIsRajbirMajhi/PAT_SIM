#!/usr/bin/env python3
"""
Run benchmark on external mp4 video(s) — PTZ bypass mode.

Usage:
    python scripts/run_video_benchmark.py --video data/input_videos/test.mp4 --output outputs/runs
    python scripts/run_video_benchmark.py --video-dir data/input_videos --output outputs/runs

For each video at 30 fps, the pipeline bypasses the virtual PTZ camera and feeds decoded frames
directly to the detector → tracker → metrics. No hidden annotations are used; if a JSON
annotation file with same basename exists (e.g., test.json with [{"frame_id":0,"x":123,"y":456}]), 
centroiding error is computed against it, otherwise only detection/tracking status is logged.
"""
import argparse, os, sys, glob, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from fsoc_tracker.config.loader import load_config
from fsoc_tracker.input.video_source import VideoSource
from fsoc_tracker.perception.detector import BeaconDetector
from fsoc_tracker.tracking.tracker import Tracker
from fsoc_tracker.evaluation.metrics import MetricsCollector
from fsoc_tracker.evaluation.auto_logger import RobustPerfLogger
from fsoc_tracker.common.types import GroundTruth, Detection
from fsoc_tracker.common.enums import TrackingState
from fsoc_tracker.ai.inference import AIInferencePipeline
from fsoc_tracker.tracking.track_manager import TrackManager
import time

def load_annotations(video_path):
    """Try to load JSON annotations for benchmark comparison. Returns dict frame_id -> (x,y) or None."""
    base = os.path.splitext(video_path)[0]
    for ext in [".json", ".csv"]:
        ann_path = base + ext
        if os.path.exists(ann_path):
            try:
                if ext == ".json":
                    with open(ann_path) as f:
                        data = json.load(f)
                    # Support list of dicts or dict
                    if isinstance(data, list):
                        return {int(d["frame_id"]): (float(d["x"]), float(d["y"])) for d in data if "x" in d}
                    elif isinstance(data, dict):
                        return {int(k): (float(v[0]), float(v[1])) for k,v in data.items()}
                else:
                    # CSV: frame_id,x,y
                    import csv
                    d = {}
                    with open(ann_path) as f:
                        r = csv.DictReader(f)
                        for row in r:
                            d[int(row["frame_id"])] = (float(row["x"]), float(row["y"]))
                    return d
            except Exception as e:
                print(f"[VideoBench] Failed to load {ann_path}: {e}")
    return None

def run_one_video(video_path, output_base, cfg_override=None):
    cfg = load_config(cfg_override) if cfg_override else load_config()
    cfg["experiment"]["input_mode"] = "VIDEO"
    cfg["experiment"]["video_path"] = video_path
    annotations = load_annotations(video_path)
    if not annotations:
        print(f"[VideoBench] FAIL: No annotations found for {os.path.basename(video_path)}. Annotations are required for RMSE benchmark.")
        return None, None
    if annotations:
        print(f"[VideoBench] Loaded {len(annotations)} annotations for {os.path.basename(video_path)}")
    else:
        print(f"[VideoBench] No annotations for {os.path.basename(video_path)} — metrics only (no error vs truth)")

    vs = VideoSource(video_path)
    print(f"[VideoBench] {video_path} — {vs.resolution[0]}x{vs.resolution[1]} @ {vs.fps:.1f}Hz")
    # Adjust detector to video resolution if different from config (avoid silent resize that changes error scale)
    cfg["camera"]["resolution"] = [vs.resolution[0], vs.resolution[1]]
    # Keep FOV proportional: assume same angular FOV, so pixel scale changes automatically via detector's thresholds (area gates are pixel-based, but we keep them)
    det = BeaconDetector(cfg)
    trk = Tracker(cfg)
    tm = TrackManager(cfg)
    pipeline = AIInferencePipeline(cfg)
    metrics = MetricsCollector()
    logger = RobustPerfLogger(base_dir=output_base, metrics_collector=metrics)
    metrics.start_run()
    logger.begin_run(cfg)
    metrics.input_fps = float(vs.fps or 30.0)

    frame_n = 0
    while True:
        f, _ = vs.read()
        if f is None:
            break
        # For benchmark, optionally compare against annotation
        gt = None
        if annotations and f.frame_id in annotations:
            x, y = annotations[f.frame_id]
            gt = GroundTruth(world_pos=(x,y), visible=True, image_pos=(x,y))
        else:
            # No truth — metrics will count as no error, but detection still logged
            gt = GroundTruth(world_pos=(0,0), visible=False, image_pos=None)
            # For video without annotations, we still want to log detection, but for error we need a proxy:
            # If no annotation, we don't compute error (metrics will skip). That's correct per spec: compare with predefined when available.

        t0 = time.perf_counter()
        
        ai_enabled = cfg.get("ai", {}).get("enabled", False)
        if ai_enabled:
            candidates = det.detect_candidates(f.image, predicted_pos=trk.get_predicted_pixel())
            tracks = tm.update(candidates, f.frame_id, innovation=float(trk.imm.last_nis), imm_probs=tuple(trk.imm.probs))
            results = pipeline.step(f.image, candidates, tracks)
            primary_id = pipeline.primary_track_id(results)
            
            for res in results:
                if res.identity:
                    tr = tracks.get(res.candidate.candidate_id)
                    if tr:
                        tr.current_identity = res.identity.identity_state
                        if res.identity.identity_state.value == "DECOY_CONFIRMED":
                            tm.mark_rejected(tr.track_id)
            
            if primary_id is not None:
                c_primary = next((r.candidate for r in results if r.candidate.candidate_id == primary_id), None)
                ident_primary = next((r.identity for r in results if r.candidate.candidate_id == primary_id), None)
                d = Detection(valid=True, centroid_px=c_primary.centroid_px, bbox=c_primary.bbox, confidence=float(ident_primary.measurement_quality), score=float(ident_primary.primary_probability), area=c_primary.area)
                est = trk.step(d, f)
                est.tracking_state = TrackingState.LOCKED
            else:
                d = Detection(valid=False)
                est = trk.step(d, f)
                est.tracking_state = TrackingState.SEARCHING if not candidates else TrackingState.CANDIDATE
        else:
            d = det.detect(f.image, predicted_pos=trk.get_predicted_pixel())
            est = trk.step(d, f)
            
        proc_ms = (time.perf_counter() - t0) * 1000
        # No camera command in video mode (PTZ bypassed)
        logger.log_frame(f.frame_id, f.timestamp, d.valid, est, gt, proc_ms, float(vs.fps), 0, 0,
                         detection_confidence=d.confidence, saturated=False, input_fps=float(vs.fps))
        frame_n += 1
        if frame_n % 90 == 0:
            print(f"  Frame {frame_n} state={est.tracking_state.value} conf={d.confidence:.2f}")

    vs.release()
    summary, run_dir = logger.end_run()
    if summary:
        print(f"[VideoBench] Done {frame_n} frames -> {run_dir}")
        print(f"  RMSE {summary['rmse_px']:.2f} (vs annotations if provided)  Valid {summary['valid_detections']}/{frame_n} ({summary['valid_detection_pct']:.1f}%)")
    return summary, run_dir

def main():
    parser = argparse.ArgumentParser(description="Video Benchmark Runner (30 fps, PTZ bypass)")
    parser.add_argument("--video", type=str, help="Single video path")
    parser.add_argument("--video-dir", type=str, help="Directory of videos")
    parser.add_argument("--config", type=str, default=None)
    parser.add_argument("--ai", action="store_true", help="Enable AI inference pipeline")
    parser.add_argument("--output", type=str, default="outputs/runs")
    args = parser.parse_args()
    videos = []
    if args.video:
        videos.append(args.video)
    if args.video_dir:
        for ext in ("*.mp4","*.avi","*.mov"):
            videos.extend(glob.glob(os.path.join(args.video_dir, ext)))
    if not videos:
        print("No videos. Use --video <path> or --video-dir <dir>")
        return
        
    cfg_override = {}
    if args.config:
        import yaml
        with open(args.config, 'r') as f:
            cfg_override = yaml.safe_load(f)
    if args.ai:
        if "ai" not in cfg_override:
            cfg_override["ai"] = {}
        cfg_override["ai"]["enabled"] = True
        
    for vp in videos:
        run_one_video(vp, args.output, cfg_override)

if __name__ == "__main__":
    main()
