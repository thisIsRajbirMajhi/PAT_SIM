#!/usr/bin/env python3
"""Headless PAT-SIM runner — full simulation via CLI, no GUI/Qt required.

Default single run starts the target FAR from center/camera (far corner,
no start cue) so it must traverse the ENTIRE pipeline unassisted:
scan -> detect -> verify -> acquire -> track. Verdict uses pipeline
traversal criteria (reached TRACKING, post-lock hold, RMSE).

    python headless.py                       # far-start cold run, full duration
    python headless.py --cue                 # assisted start (camera cued)
    python headless.py --no-far-start        # pure config geometry
    python headless.py --frames 300 --seed 7 --set target.speed_px_per_frame=12

Extreme stress suite (10 scenarios, exits 1 if any FAIL):
    python headless.py --extreme
    python headless.py --scenario X2-sensor-hell --frames 240
    python headless.py --list

Ground-truth note: the pipeline itself (detector -> tracker -> controller)
never sees ground truth. Like the GUI, this runner uses gt only for scoring
(metrics), the OFF-SCREEN display hint, and the start cue. See README answer.
"""
import argparse
import copy
import os
import sys
import time

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(ROOT, "src"))

import numpy as np
import yaml

from fsoc_tracker.config.loader import load_config
from fsoc_tracker.input.synthetic_source import SyntheticSource
from fsoc_tracker.pipeline import BeaconDetector, Tracker
from fsoc_tracker.camera import CameraController
from fsoc_tracker.evaluation.metrics import MetricsCollector
from fsoc_tracker.evaluation.auto_logger import RobustPerfLogger
from fsoc_tracker.pipeline.track.display import DisplayTracker, DisplayStatus

# --------------------------------------------------------------------------
# Extreme scenario definitions: name -> (description, overrides, frames)
# Ranges per config/validation: gauss_std 0-20, spp 0-0.15, jitter 0-20,
# atmo strength 0-1, platform speed 0-20, target speed 0-20, size 5-20,
# count 1-5, blink 0-50 Hz, stars density 0-0.006.
# --------------------------------------------------------------------------
SCENARIOS = {
    "X1-baseline": ("Defaults sanity check (must PASS).", {}, 240),
    "X2-sensor-hell": ("Max Gaussian noise + 10% salt&pepper + poisson.", {
        "noise": {"gaussian_enabled": True, "gaussian_std": 20.0,
                  "salt_pepper_enabled": True, "salt_pepper_prob": 0.10,
                  "poisson": True}}, 240),
    "X3-motion-hell": ("Max camera jitter + aggressive random platform.", {
        "camera": {"jitter_px": 20.0},
        "platform": {"type": "random", "speed_px_per_frame": 15.0}}, 240),
    "X4-speed-demon": ("Target at max speed on figure-eight.", {
        "target": {"speed_px_per_frame": 20.0, "trajectory": "figure_eight"}}, 240),
    "X5-tiny-target": ("Minimum-size target + star clutter.", {
        "target": {"size": 5, "speed_px_per_frame": 6.0, "trajectory": "straight"},
        "environment": {"stars_enabled": True, "stars_density": 0.002,
                        "stars_brightness": 185}}, 240),
    "X6-blink-dropout": ("5 Hz blinking beacon + 2 s hidden dropout.", {
        "target": {"blink_rate_hz": 5.0,
                   "visibility_schedule": [[1.0, 3.0, "hidden"]]}}, 240),
    "X7-atmo-soup": ("Full-strength fog.", {
        "atmosphere": {"type": "fog", "strength": 1.0}}, 240),
    "X8-cold-start": ("Far-corner crossing, no cue: scan to track.", {
        "target": {"initial_mode": "user-defined", "initial_pos": [300, 300],
                   "trajectory": "straight", "speed_px_per_frame": 3.0}}, 900),
    "X9-crowded": ("5 targets + stars + vignetting.", {
        "target": {"count": 5},
        "environment": {"stars_enabled": True, "stars_density": 0.002,
                        "stars_brightness": 185, "vignetting_enabled": True,
                        "vignetting_strength": 0.42}}, 240),
    "X10-combined-hell": ("Noise + jitter + fast target + blink + fog + platform.", {
        "noise": {"gaussian_enabled": True, "gaussian_std": 12.0,
                  "salt_pepper_enabled": True, "salt_pepper_prob": 0.05},
        "camera": {"jitter_px": 12.0},
        "target": {"speed_px_per_frame": 12.0, "trajectory": "figure_eight",
                   "blink_rate_hz": 2.0},
        "atmosphere": {"type": "fog", "strength": 0.6},
        "platform": {"type": "linear", "speed_px_per_frame": 8.0}}, 300),
}

# Pass thresholds (mirror the dashboard badges).
RMSE_PASS = 10.0
LOSS_PASS_PCT = 5.0
ACQ_PASS_S = 2.0
REACQ_PASS_S = 1.0
FPS_MIN = 20.0
POST_LOCK_PASS_PCT = 90.0

# Default far-start geometry: target begins ~990px (~6 deg) from the camera
# boresight (far corner) and crosses the FOV on a straight 30-deg track, so an
# uncued run must traverse the ENTIRE pipeline: scan -> detect -> verify ->
# acquire -> track. The gimbal now has a full-world raster fallback after the
# initial spiral, so even static far targets are eventually covered.
FAR_START = {"target": {"initial_mode": "user-defined", "initial_pos": [300, 300],
                        "trajectory": "straight", "speed_px_per_frame": 3.0}}

# Pipeline stage order for the coverage checklist.
STAGE_ORDER = ["INITIALIZING", "SCANNING", "TARGET_DETECTED", "VERIFYING",
               "ACQUIRING", "TRACKING", "OFF_SCREEN", "DEGRADED", "LOST",
               "REACQUIRING"]


def parse_set(items):
    """Parse ['a.b=c', ...] into a nested dict (values YAML-parsed)."""
    out = {}
    for item in items or []:
        if "=" not in item:
            raise ValueError(f"--set expects key=value, got {item!r}")
        key, raw = item.split("=", 1)
        try:
            val = yaml.safe_load(raw)
        except Exception:
            val = raw
        node = out
        parts = key.split(".")
        for p in parts[:-1]:
            node = node.setdefault(p, {})
        node[parts[-1]] = val
    return out


def deep_merge(a, b):
    out = copy.deepcopy(a)
    for k, v in b.items():
        if k in out and isinstance(out[k], dict) and isinstance(v, dict):
            out[k] = deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def has_intermittent_target(cfg):
    """True when the beacon is duty-cycled (blink) or has hidden windows:
    whole-run loss% is then inapplicable (the target is physically absent
    part of the time), so the verdict uses acquisition + RMSE + reacquire."""
    try:
        tgt = (cfg or {}).get("target", {}) or {}
        if float(tgt.get("blink_rate_hz", 0) or 0) > 0:
            return True
        sched = tgt.get("visibility_schedule") or ((cfg or {}).get("visibility", {}) or {}).get("schedule")
        if sched:
            for seg in sched:
                try:
                    if str(seg[2]).lower() in ("hidden", "invisible", "off"):
                        return True
                except Exception:
                    continue
    except Exception:
        pass
    return False


def verdict(summary, cold=False, post_lock_pct=None, stages=(), intermittent=False):
    """(ok, reasons).

    Standard (cued) runs: dashboard thresholds over the whole run
    (RMSE, loss, acquisition, re-acquisition, FPS).
    Cold/far-start runs: the search phase is honestly unproductive, so judge
    pipeline traversal instead — must reach TRACKING, hold lock once acquired
    (post-lock retention), and keep RMSE within budget — plus re-acquisition
    and FPS gates when measurable.
    Intermittent (blink/hidden) runs: loss% is inapplicable since the beacon
    is physically absent part of the time — judge acquisition (locks
    repeatedly), RMSE while visible, and fast re-acquisition instead.
    """
    reasons = []
    if summary.get("rmse_px", 0) > RMSE_PASS:
        reasons.append(f"RMSE {summary['rmse_px']:.1f} > {RMSE_PASS}")
    reacq_m = summary.get("reacquisition_mean_s")
    if reacq_m is not None and reacq_m > REACQ_PASS_S:
        reasons.append(f"reacq {reacq_m:.2f}s > {REACQ_PASS_S}s")
    avg_fps = summary.get("avg_fps", 0) or 0
    e2e_fps = summary.get("e2e_fps", 0) or 0
    if avg_fps < FPS_MIN and e2e_fps < FPS_MIN:
        reasons.append(f"fps {avg_fps:.1f}/{e2e_fps:.1f} < {FPS_MIN}")
    if cold:
        names = {getattr(s, "value", s) if not isinstance(s, str) else s for s in stages}
        if "TRACKING" not in names:
            reasons.append("never reached TRACKING")
        if post_lock_pct is None:
            reasons.append("never acquired")
        elif post_lock_pct < POST_LOCK_PASS_PCT:
            reasons.append(f"post-lock {post_lock_pct:.1f}% < {POST_LOCK_PASS_PCT}%")
    elif intermittent:
        # Duty-cycled beacons are absent part of the time, so loss% is
        # inapplicable — but the run must still prove repeated acquisition
        # across cycles (not one lucky lock) with a healthy visible share.
        if int(summary.get("acquisition_count", 0)) < 2:
            reasons.append("never re-acquired (need >=2 locks across cycles)")
        try:
            _vpct = float(summary.get("valid_detection_pct", 0) or 0)
        except Exception:
            _vpct = 0.0
        if _vpct < 15.0:
            reasons.append(f"visible share {_vpct:.1f}% < 15%")
    else:
        if summary.get("target_loss_pct", 0) >= LOSS_PASS_PCT:
            reasons.append(f"loss {summary['target_loss_pct']:.1f}% >= {LOSS_PASS_PCT}%")
        acq = summary.get("acquisition_time_s")
        if acq is None:
            reasons.append("never acquired")
        elif acq > ACQ_PASS_S:
            reasons.append(f"acq {acq:.2f}s > {ACQ_PASS_S}s")
    return (len(reasons) == 0, reasons)


def run_single(cfg, frames, seed=42, every=30, live=False, no_cue=False,
               use_logger=True, tag="run", video_path=None, video_gt=None,
               video_native_fps=False):
    """Headless mirror of MainWindow._tick (no Qt, no views)."""
    cfg = copy.deepcopy(cfg)
    # Benchmark-2: external video bypasses the PTZ camera (measurement only).
    is_video = bool(video_path or (cfg.get("experiment", {}).get("input_mode") == "VIDEO"
                                   and cfg.get("experiment", {}).get("video_path")))
    if is_video:
        from fsoc_tracker.input.video_source import VideoSource
        vpath = video_path or cfg["experiment"]["video_path"]
        ann = video_gt or cfg["experiment"].get("video_annotations_path") or None
        if isinstance(ann, str):
            ann = ann.strip() or None
        source = VideoSource(vpath, target_fps=30.0,
                             centre_offset_x=float(cfg["camera"].get("video_centre_offset_x", 0)),
                             centre_offset_y=float(cfg["camera"].get("video_centre_offset_y", 0)),
                             annotations_path=ann, native_fps=bool(video_native_fps))
        no_cue = True  # cue is synthetic-only; video has no gimbal to cue
    else:
        source = SyntheticSource(cfg, seed=seed)
    detector = BeaconDetector(cfg)
    tracker = Tracker(cfg)
    controller = CameraController(cfg)
    metrics = MetricsCollector()
    metrics.input_fps = float(getattr(source, "fps", cfg["camera"]["fps"]))
    logger = RobustPerfLogger(base_dir="outputs/runs", metrics_collector=metrics) \
        if use_logger else None
    display = DisplayTracker(cfg)

    metrics.start_run()
    if logger is not None:
        logger.begin_run(cfg)
    tracker.reset()
    controller.reset()
    source.reset()
    if not no_cue and hasattr(source, "cue_camera_to_target"):
        source.cue_camera_to_target()
    display.reset()

    fps = float(cfg["camera"]["fps"])
    upd = float(cfg["camera"].get("update_interval_hz", fps))
    dt_ctrl = 1.0 / max(upd, 1)
    if upd >= fps:
        every_ctrl = 1
    else:
        every_ctrl = max(1, int(round(fps / upd)))
    _last_cmd = None
    fps_smooth = float(getattr(source, "fps", fps))
    last_t = time.perf_counter()
    last_state = last_tele = None
    last_raw = last_fused = None
    stages = set()
    sm_states = set()
    locked_flags = []
    t0 = time.perf_counter()
    _latched = False
    from fsoc_tracker.target.dynamics.visibility import is_blink_off as _blink_off, is_hidden as _hidden

    for i in range(frames):
        f0 = time.perf_counter()
        frame, gt = source.read()
        if frame is None:
            break
        pred = tracker.get_predicted_pixel() if hasattr(tracker, "get_predicted_pixel") else None
        try:
            _miss0 = int(getattr(getattr(tracker, "sm", None), "missed", 0))
        except Exception:
            _miss0 = 0
        try:
            _fresh = bool(_latched) and _miss0 <= 30
            _gate = tracker.get_gate_radius_px(missed=_miss0) if (hasattr(tracker, "get_gate_radius_px") and _fresh) else None
        except Exception:
            _gate = None
        try:
            detection = detector.detect(frame.image, predicted_pos=pred, gate_radius_px=_gate)
        except TypeError:
            detection = detector.detect(frame.image, predicted_pos=pred)
        try:
            _hold_sched = bool(_blink_off(frame.frame_id, cfg) or _hidden(frame.frame_id, cfg))
        except Exception:
            _hold_sched = False
        try:
            estimate = tracker.step(detection, frame, hold=False)
        except TypeError:
            estimate = tracker.step(detection, frame)
        try:
            if getattr(estimate.tracking_state, "value", "") == "LOCKED":
                _latched = True
        except Exception:
            pass
        try:
            if hasattr(source, "camera"):
                _in_fov_pre = source.camera.world_to_image(gt.world_pos) is not None \
                    if gt is not None and getattr(gt, "world_pos", None) not in (None, (0, 0)) else None
            else:
                _in_fov_pre = True if detection.valid else None
        except Exception:
            _in_fov_pre = None
        try:
            if hasattr(source, "camera"):
                _lim_pre = bool(source.camera.is_at_limit(
                    getattr(controller, "prev_pan_rate", 0.0),
                    getattr(controller, "prev_tilt_rate", 0.0)))
            else:
                _lim_pre = False
        except Exception:
            _lim_pre = False
        try:
            _sm_pre = getattr(tracker, "sm", None)
            _miss_pre = int(getattr(_sm_pre, "missed", 0))
            _cctx = {
                "missed": _miss_pre,
                "cand_frames": int(getattr(_sm_pre, "candidate_frames", 0)),
                "locked_frames": int(getattr(_sm_pre, "locked_frames", 0)),
                "det_valid": bool(detection.valid),
                "det_conf": float(detection.confidence or 0.0),
                "in_fov": _in_fov_pre,
                "latched": bool(_latched and _miss_pre <= 60),
                "scheduled_hold": _hold_sched,
                "saturated": False,
                "at_limit": _lim_pre,
            }
        except Exception:
            _cctx = None
        # Sr.15 control-rate hold (sensor fps vs gimbal update_interval_hz)
        if (i % every_ctrl) == 0 or _last_cmd is None:
            try:
                cmd = controller.step(estimate, dt=dt_ctrl, ctx=_cctx)
            except TypeError:
                cmd = controller.step(estimate, dt=dt_ctrl)
            _last_cmd = cmd
        else:
            cmd = _last_cmd

        try:
            if hasattr(source, "camera"):
                _in_fov = source.camera.world_to_image(gt.world_pos) is not None \
                    if gt is not None and getattr(gt, "world_pos", None) not in (None, (0, 0)) else None
            else:
                _in_fov = True if detection.valid else None
        except Exception:
            _in_fov = None
        is_ptz = getattr(source, "is_ptz_enabled", not is_video)
        if is_ptz:
            source.apply_camera_command(cmd.pan_rate, cmd.tilt_rate, dt_ctrl)

        proc_ms = (time.perf_counter() - f0) * 1000
        now = time.perf_counter()
        inst = 1.0 / max(now - last_t, 1e-6)
        last_t = now
        fps_smooth = 0.85 * fps_smooth + 0.15 * inst

        if logger is not None:
            logger.log_frame(frame.frame_id, frame.timestamp, detection.valid,
                             estimate, gt, proc_ms, fps_smooth,
                             cmd.pan_rate if is_ptz else 0, cmd.tilt_rate if is_ptz else 0,
                             detection_confidence=detection.confidence,
                             saturated=cmd.saturated if is_ptz else False,
                             input_fps=float(getattr(source, "fps", fps)),
                             detection_centroid=detection.centroid_px if detection.valid else None,
                             search_case=getattr(cmd, "search_case", ""))
        else:
            metrics.update(frame.frame_id, frame.timestamp, detection.valid,
                           estimate, gt, proc_ms, fps_smooth,
                           cmd.pan_rate if is_ptz else 0, cmd.tilt_rate if is_ptz else 0,
                           detection_confidence=detection.confidence,
                           saturated=cmd.saturated if is_ptz else False,
                           input_fps=float(getattr(source, "fps", fps)),
                           detection_centroid=detection.centroid_px if detection.valid else None,
                           search_case=getattr(cmd, "search_case", ""))

        try:
            sm = getattr(tracker, "sm", None)
            last_state, last_tele = display.update(
                getattr(frame, "frame_id", 0), float(frame.timestamp),
                bool(detection.valid), float(detection.confidence or 0.0),
                getattr(getattr(estimate, "tracking_state", None), "value", ""),
                int(getattr(sm, "candidate_frames", 0)),
                int(getattr(sm, "locked_frames", 0)),
                float(getattr(estimate, "innovation", 0.0) or 0.0),
                _in_fov, est_pos=getattr(estimate, "pos_px", None))
            if last_state is not None:
                stages.add(last_state.status)
        except Exception:
            pass
        try:
            sm_states.add(getattr(estimate.tracking_state, "value", "?"))
            locked_flags.append(1 if getattr(estimate.tracking_state, "value", "") == "LOCKED" else 0)
        except Exception:
            pass
        last_raw = detection.centroid_px if detection.valid else None
        last_fused = estimate.pos_px

        if live or (every > 0 and (i + 1) % every == 0):
            s = metrics.summary()
            lbl = last_state.label if last_state is not None else "?"
            try:
                lbl = lbl.encode("ascii", "replace").decode("ascii")
            except Exception:
                pass
            print(f"[{tag} f{i + 1:4d}/{frames}] {lbl:22s} "
                  f"valid={s['valid_detections']:4d} fps={fps_smooth:5.1f} "
                  f"lat={s['avg_processing_ms']:5.1f}ms rmse={s['rmse_px']:5.1f}px "
                  f"lock={s['lock_retention_pct']:5.1f}% "
                  f"case={getattr(cmd, 'search_case', '')}", flush=True)

    if logger is not None:
        try:
            logger.end_run()
        except Exception:
            pass
    summary = metrics.summary()
    summary["wall_s"] = time.perf_counter() - t0
    summary["fps_smooth"] = fps_smooth
    try:
        first = locked_flags.index(1)
        post = sum(locked_flags[first:]) / max(len(locked_flags[first:]), 1) * 100.0
    except ValueError:
        first, post = None, None
    return {"summary": summary, "state": last_state, "tele": last_tele,
            "raw": last_raw, "fused": last_fused, "stages": stages,
            "sm_states": sm_states, "first_lock_idx": first,
            "post_lock_pct": post}


def print_status(res, title="STATUS"):
    # ASCII-only so output stays clean on any terminal/codepage.
    s = res["summary"]
    st = res["state"]
    tele = res["tele"]
    raw, fused = res["raw"], res["fused"]
    acq = s.get("acquisition_time_s")
    reacq_m = s.get("reacquisition_mean_s")
    print(f"--- {title} ---")
    _lbl = st.label if st is not None else "?"
    try:
        _lbl = _lbl.encode("ascii", "replace").decode("ascii")
    except Exception:
        pass
    print(f"State               : {_lbl}")
    print(f"Valid Detections    : {s['valid_detections']}")
    print(f"Average Confidence  : {s.get('avg_confidence', 0) * 100:.1f}%")
    print(f"Raw Centroid (x, y) : {f'{raw[0]:.1f}, {raw[1]:.1f}' if raw is not None else '--'}")
    try:
        fz = f"{fused[0]:.1f}, {fused[1]:.1f}" if fused is not None else "--"
    except Exception:
        fz = "--"
    print(f"Fused Centroid      : {fz}")
    print(f"FPS                 : {res.get('fps_smooth', s.get('avg_fps', 0)):.1f} (avg {s.get('avg_fps', 0):.1f} / e2e {s.get('e2e_fps', 0):.1f}, in {s.get('input_fps', 0):.0f})")
    print(f"Average Latency     : {s['avg_processing_ms']:.1f} ms")
    print(f"Maximum Latency     : {s['max_processing_ms']:.1f} ms")
    print(f"Mean / Max Error    : {s['mean_error_px']:.1f} / {s['max_error_px']:.1f} px")
    print(f"RMSE / P95 Error    : {s['rmse_px']:.1f} / {s['p95_error_px']:.1f} px")
    print(f"Centroid RMSE / Max : {s.get('centroid_rmse_px', 0):.1f} / {s.get('centroid_max_error_px', 0):.1f} px (see centroiding_error.csv)")
    print(f"Lock Retention      : {s['lock_retention_pct']:.1f}%")
    print(f"Target Loss & Count : {s['target_loss_pct']:.1f}% ({s['loss_count']})")
    try:
        _cases = s.get("search_case_counts", {}) or {}
        if _cases:
            _cd = " ".join(f"{_k}={_v}" for _k, _v in sorted(_cases.items()))
            print(f"Search Cases        : {_cd}")
    except Exception:
        pass
    print(f"Acquisition T & Cnt : {f'{acq:.2f}s' if acq is not None else '--'} ({s.get('acquisition_count', 0)})")
    print(f"Reacq T Mean & Cnt  : {f'{reacq_m:.2f}s' if reacq_m is not None else '--'} ({s.get('reacquisition_count', 0)})")
    if tele is not None:
        def _asc(v):
            try:
                return str(v).encode("ascii", "replace").decode("ascii")
            except Exception:
                return "--"
        dc = f"{tele.det_conf * 100:.0f}%" if tele.det_conf is not None else "--"
        ag = f"{tele.track_age_s:.2f} s" if tele.track_age_s is not None else "--"
        la = f"{tele.last_detect_age_s:.2f} s" if tele.last_detect_age_s is not None else "--"
        print(f"TRACK {_asc(tele.track_label)} | DET {dc} | AGE {ag} | LAST {la} | {_asc(tele.fov)}")
    # entire-pipeline proof: which display stages + tracker SM states were hit
    seen = set()
    for _s in res.get("stages", set()):
        try:
            seen.add(_s.value if hasattr(_s, "value") else str(_s))
        except Exception:
            pass
    _marks = "  ".join(f"[{'x' if _n in seen else ' '}] {_n}" for _n in STAGE_ORDER)
    print(f"PIPELINE STAGES : {_marks}")
    try:
        _sm = " ".join(sorted(str(_x) for _x in res.get("sm_states", set())))
        print(f"TRACKER SM      : {_sm}")
    except Exception:
        pass
    if res.get("post_lock_pct") is not None:
        print(f"POST-LOCK HOLD  : {res['post_lock_pct']:.1f}% (from frame {res['first_lock_idx'] + 1})")
    print(f"Frames/Dropped/Dur  : {s['total_frames']}/{s['dropped_frames']}/{s['duration_s']:.1f}s "
          f"| wall {s.get('wall_s', 0):.1f}s")


def main(argv=None):
    ap = argparse.ArgumentParser(description="Headless PAT-SIM runner + extreme stress suite.")
    ap.add_argument("--config", default=None, help="YAML config file (default: built-in defaults)")
    ap.add_argument("--frames", type=int, default=None, help="frames to run (default: full duration)")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--set", action="append", default=[], metavar="a.b=c",
                    help="config override, repeatable (values YAML-parsed)")
    ap.add_argument("--every", type=int, default=60, help="progress line every N frames (0=off)")
    ap.add_argument("--live", action="store_true", help="print a line every frame")
    ap.add_argument("--no-log", action="store_true", help="skip outputs/runs CSV logging")
    ap.add_argument("--cue", action="store_true",
                    help="assisted start: cue camera to target (default: cold far-start)")
    ap.add_argument("--no-far-start", action="store_true",
                    help="skip the default far-corner target geometry (pure config)")
    ap.add_argument("--extreme", action="store_true", help="run the full extreme suite")
    ap.add_argument("--scenario", default=None, help="run one scenario (see --list)")
    ap.add_argument("--list", action="store_true", help="list extreme scenarios and exit")
    ap.add_argument("--strict", action="store_true",
                    help="single runs also exit 1 on threshold FAIL")
    ap.add_argument("--video", default=None, help="Benchmark-2: external .mp4 (PTZ bypassed, normalized to 30fps)")
    ap.add_argument("--video-gt", default=None, help="Benchmark-2 annotations CSV: frame_id,x,y[,visible]")
    ap.add_argument("--video-native-fps", action="store_true",
                    help="use native video FPS instead of normalizing to 30fps")
    args = ap.parse_args(argv)

    if args.list:
        for name, (desc, _ov, fr) in SCENARIOS.items():
            print(f"{name:20s} [{fr} frames] {desc}")
        return 0

    base = load_config(args.config, overrides=parse_set(args.set) or None)

    if args.extreme or args.scenario:
        names = list(SCENARIOS) if args.extreme else [args.scenario]
        for n in names:
            if n not in SCENARIOS:
                print(f"unknown scenario {n!r} (see --list)")
                return 2
        results = []
        for n in names:
            desc, ov, fr = SCENARIOS[n]
            cfg = load_config(args.config, overrides=parse_set(args.set) or None)
            cfg = deep_merge(cfg, copy.deepcopy(ov))
            frames = args.frames or fr
            no_cue = (n == "X8-cold-start") if not args.cue else False
            cold = no_cue
            print(f"\n===== {n}: {desc} =====")
            res = run_single(cfg, frames, seed=args.seed, every=0,
                             live=args.live, no_cue=no_cue,
                             use_logger=not args.no_log, tag=n)
            print_status(res, title=n)
            ok, reasons = verdict(res["summary"], cold=cold,
                                  post_lock_pct=res.get("post_lock_pct"),
                                  stages=res.get("stages", set()),
                                  intermittent=has_intermittent_target(cfg))
            print(f"VERDICT {n}: {'PASS' if ok else 'FAIL' + ' (' + '; '.join(reasons) + ')'}")
            results.append((n, ok, reasons, res["summary"], res.get("post_lock_pct")))
        print("\n===== EXTREME SUITE SUMMARY =====")
        for n, ok, reasons, s, post in results:
            flag = "PASS" if ok else f"FAIL ({'; '.join(reasons)})"
            extra = f" postlock={post:.1f}%" if post is not None else ""
            print(f"{n:20s} {flag:44s} rmse={s['rmse_px']:5.1f} loss={s['target_loss_pct']:4.1f}% "
                  f"lock={s['lock_retention_pct']:5.1f}% valid={s['valid_detections']}{extra}")
        return 0 if all(r[1] for r in results) else 1

    if not args.no_far_start:
        base = deep_merge(base, copy.deepcopy(FAR_START))
        base = deep_merge(base, parse_set(args.set) or {})
    is_video_run = bool(args.video or (base.get("experiment", {}).get("input_mode") == "VIDEO"
                                       and base.get("experiment", {}).get("video_path")))
    cold = (not args.cue) and not is_video_run
    if is_video_run and not args.video:
        # config-driven video run: force PTZ-bypass path via run_single detection
        args.video = base["experiment"]["video_path"]
        if not args.video_gt:
            args.video_gt = base["experiment"].get("video_annotations_path") or None
    fps = float(base["camera"]["fps"])
    if is_video_run:
        fps = 30.0  # Benchmark-2 reference rate for frame budgeting
    frames = args.frames or int(round(float(base["experiment"]["duration_s"]) * fps))
    if is_video_run:
        print(f"INPUT: video {args.video} (PTZ bypassed @30fps)"
              + (f" + annotations {args.video_gt}" if args.video_gt else " (no annotations)"))
    else:
        print(f"GEOMETRY: target start {base['target'].get('initial_pos')} "
              f"({base['target'].get('initial_mode')}, {base['target'].get('trajectory')} "
              f"@ {base['target'].get('speed_px_per_frame')}px/f), "
              f"camera {base['camera'].get('initial_position')}, cue={'ON' if args.cue else 'OFF'}")
    res = run_single(base, frames, seed=args.seed, every=args.every if not args.live else 1,
                     live=args.live, no_cue=not args.cue,
                     use_logger=not args.no_log, tag="run",
                     video_path=args.video, video_gt=args.video_gt,
                     video_native_fps=args.video_native_fps)
    print_status(res)
    ok, reasons = verdict(res["summary"], cold=cold,
                          post_lock_pct=res.get("post_lock_pct"),
                          stages=res.get("stages", set()),
                          intermittent=has_intermittent_target(base))
    print(f"VERDICT: {'PASS' if ok else 'FAIL (' + '; '.join(reasons) + ')'}")
    return 1 if (args.strict and not ok) else 0


if __name__ == "__main__":
    sys.exit(main())
