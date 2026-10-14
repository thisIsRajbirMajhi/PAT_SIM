#!/usr/bin/env python3
"""Headless PAT-SIM runner -- full simulation via CLI, no GUI/Qt required.

Default single run starts the target FAR from center/camera (far corner,
no start cue) so it must traverse the ENTIRE pipeline unassisted:
scan -> detect -> verify -> acquire -> track. Verdict uses pipeline
traversal criteria (reached TRACKING, post-lock hold, RMSE).

    python headless.py                       # far-start cold run, full duration
    python headless.py --cue                 # assisted start (camera cued)
    python headless.py --no-far-start        # pure config geometry
    python headless.py --frames 300 --seed 7 --set target.speed_px_per_frame=12

Extreme stress suite (10 scenarios, exits 1 if any dashboard FAIL):
    python headless.py --extreme
    python headless.py --scenario X2-sensor-hell --frames 240
    python headless.py --scenario X2                 # unique prefix is enough
    python headless.py --list

Randomized fuzzing (seeded, reproducible) against pat_pipeline:
    python headless.py --fuzz 20 --fuzz-seed 7
    python headless.py --fuzz 5 --fuzz-seed 7 --frames 300   # quick iteration
    python headless.py --fuzz 20 --fuzz-seed 7 --fuzz-pick 13  # re-run FUZZ-13 only

Full gauntlet (extreme suite + 20 fuzz scenarios, exits 1 on traversal FAIL):
    python headless.py --gauntlet
    python headless.py --gauntlet --fuzz 30 --fuzz-seed 99

Every scenario prints two verdicts side by side:
    VERDICT-DASH ...  dashboard thresholds (RMSE, loss/acq, reacq, FPS)
    VERDICT-TRAV ...  pipeline-traversal proof (reached TRACKING, post-lock
                      hold or intermittent re-acquisition, clean run)
Suite tables carry both columns plus the seed (re-run any scenario exactly).

Exit codes: 0 = pass, 1 = FAIL (any gating verdict, or a scenario crashed),
2 = usage / configuration error, 3 = single run crashed, 130 = interrupted.

Reproducibility: every run seeds SyntheticSource AND python/numpy global RNGs
with the printed seed, and --set overrides are applied LAST so they win over
scenario/fuzz/far-start values.

Ground-truth note: the pipeline itself (detector -> tracker -> controller)
never sees ground truth. Like the GUI, this runner uses gt only for scoring
(metrics), the OFF-SCREEN display hint, and the start cue.
"""
import argparse
import copy
import enum
import math
import os
import random
import sys
import time
import traceback

ROOT = os.path.dirname(os.path.abspath(__file__))
for _p in (ROOT, os.path.join(ROOT, "src")):   # src ends up first, ROOT second
    if _p not in sys.path:
        sys.path.insert(0, _p)

import numpy as np
import yaml

from fsoc_tracker.config.loader import load_config
from fsoc_tracker.input.synthetic_source import SyntheticSource
from pat_pipeline import DisplayTracker, make_pipeline
from fsoc_tracker.evaluation.metrics import MetricsCollector
from fsoc_tracker.evaluation.auto_logger import RobustPerfLogger

# --------------------------------------------------------------------------
# Extreme scenario definitions live in the shared package module so the GUI
# preset panel lists the same set (single source of truth).
# Ranges per config/validation: gauss_std 0-20, spp 0-0.15, jitter 0-20,
# atmo strength 0-1, platform speed 0-20, target speed 0-20, size 5-20,
# count 1-5, blink 0-50 Hz, stars density 0-0.006.
# --------------------------------------------------------------------------
from fsoc_tracker.config.stress_presets import SCENARIOS, FAR_START
from scenario_gen import random_scenario, validate_overrides

# Pass thresholds (mirror the dashboard badges).
RMSE_PASS = 10.0
LOSS_PASS_PCT = 5.0
ACQ_PASS_S = 2.0
REACQ_PASS_S = 1.0
FPS_MIN = 20.0
POST_LOCK_PASS_PCT = 90.0
VISIBLE_MIN_PCT = 15.0      # intermittent runs: minimum valid-detection share
MIN_ACQUISITIONS = 2        # intermittent runs: locks needed across cycles

# Default far-start geometry lives in stress_presets.FAR_START (imported above):
# target begins ~990px (~6 deg) from the camera boresight (far corner) and
# crosses the FOV on a straight 30-deg track, so an uncued run must traverse
# the ENTIRE pipeline: scan -> detect -> verify -> acquire -> track.

# Pipeline stage order for the coverage checklist.
STAGE_ORDER = ["INITIALIZING", "SCANNING", "TARGET_DETECTED", "VERIFYING",
               "ACQUIRING", "TRACKING", "OFF_SCREEN", "DEGRADED", "LOST",
               "REACQUIRING"]


# --------------------------------------------------------------------------
# small helpers
# --------------------------------------------------------------------------
def parse_set(items):
    """Parse ['a.b=c', ...] into a nested dict (values YAML-parsed)."""
    out = {}
    for item in items or []:
        if "=" not in item:
            raise ValueError(f"--set expects key=value, got {item!r}")
        key, raw = item.split("=", 1)
        key = key.strip()
        if not key or any(not p for p in key.split(".")):
            raise ValueError(f"--set has an empty key segment: {item!r}")
        try:
            val = yaml.safe_load(raw)
        except Exception:
            val = raw
        node = out
        parts = key.split(".")
        for p in parts[:-1]:
            nxt = node.setdefault(p, {})
            if not isinstance(nxt, dict):
                raise ValueError(f"--set conflict: {p!r} is both a value and a section ({item!r})")
            node = nxt
        node[parts[-1]] = val
    return out


def deep_merge(a, b):
    """Return a new dict: b merged recursively over a (neither is mutated)."""
    out = copy.deepcopy(a)
    for k, v in (b or {}).items():
        if k in out and isinstance(out[k], dict) and isinstance(v, dict):
            out[k] = deep_merge(out[k], v)
        else:
            out[k] = copy.deepcopy(v)
    return out


def _f(x, default=0.0):
    """float(x), with None / non-numeric / NaN mapped to default."""
    try:
        v = float(x)
    except (TypeError, ValueError):
        return default
    return default if math.isnan(v) else v


def _names(*groups):
    """Normalise stage / state-machine members (Enum, str-Enum, str) to plain strings."""
    out = set()
    for g in groups:
        for s in g or ():
            if isinstance(s, enum.Enum):
                out.add(str(s.value))
            else:
                out.add(str(getattr(s, "value", s)))
    return out


def _ascii(v, default="--"):
    try:
        return str(v).encode("ascii", "replace").decode("ascii")
    except Exception:
        return default


_WARNED = set()


def _warn_once(tag, key, exc):
    """Count-free first-occurrence warning so swallowed errors are never silent."""
    if (tag, key) not in _WARNED:
        _WARNED.add((tag, key))
        print(f"WARN [{tag}] {key}: {type(exc).__name__}: {exc}", flush=True)


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


def _rmse_problem(summary, has_gt):
    """Reason string if RMSE fails, else None.

    A NaN/inf/missing RMSE used to PASS silently (NaN > 10 is False), so a
    run with no usable error samples looked perfect. Now it fails -- unless
    the run has no ground truth at all (video without annotations).
    """
    if not has_gt:
        return None
    raw = (summary or {}).get("rmse_px")
    try:
        v = float(raw)
    except (TypeError, ValueError):
        return "RMSE unavailable"
    if not math.isfinite(v):
        return f"RMSE not finite ({v})"
    if v > RMSE_PASS:
        return f"RMSE {v:.1f} > {RMSE_PASS}"
    return None


def _visible_pct(summary):
    """Valid-detection share in %. Falls back to valid/total when the metrics
    summary has no valid_detection_pct (which used to read as 0% and fail
    every intermittent run)."""
    if summary.get("valid_detection_pct") is not None:
        return _f(summary.get("valid_detection_pct"))
    total = _f(summary.get("total_frames"))
    return 100.0 * _f(summary.get("valid_detections")) / total if total > 0 else 0.0


def _intermittent_reasons(summary, reached):
    """Duty-cycle rule shared by both verdicts."""
    reasons = []
    if not reached:
        reasons.append("never reached TRACKING")
    if int(_f(summary.get("acquisition_count"))) < MIN_ACQUISITIONS:
        reasons.append(f"never re-acquired (need >={MIN_ACQUISITIONS} locks across cycles)")
    vpct = _visible_pct(summary)
    if vpct < VISIBLE_MIN_PCT:
        reasons.append(f"visible share {vpct:.1f}% < {VISIBLE_MIN_PCT:g}%")
    return reasons


def verdict(summary, cold=False, post_lock_pct=None, stages=(), intermittent=False,
            sm_states=(), *, fps_min=FPS_MIN, has_gt=True):
    """(ok, reasons) -- dashboard-threshold gate.

    Standard (cued) runs: dashboard thresholds over the whole run
    (RMSE, loss, acquisition, re-acquisition, FPS).
    Cold/far-start runs: the search phase is honestly unproductive, so judge
    pipeline traversal instead -- must reach TRACKING, hold lock once acquired
    (post-lock retention), and keep RMSE within budget -- plus re-acquisition
    and FPS gates when measurable.
    Intermittent (blink/hidden) runs: loss% is inapplicable since the beacon
    is physically absent part of the time -- judge acquisition (locks
    repeatedly), RMSE while visible, and fast re-acquisition instead.
    Intermittent takes priority over cold: a duty-cycled beacon can never
    hold 90% post-lock no matter how good the tracker is.

    "Reached TRACKING" accepts the display stage TRACKING or tracker state
    LOCKED, in every mode (a display-side failure can no longer false-fail
    a cold run whose tracker did lock).
    fps_min <= 0 disables the FPS gate (machine-load-independent CI runs).
    """
    summary = summary or {}
    reasons = []
    r = _rmse_problem(summary, has_gt)
    if r:
        reasons.append(r)
    reacq_m = summary.get("reacquisition_mean_s")
    if reacq_m is not None and _f(reacq_m) > REACQ_PASS_S:
        reasons.append(f"reacq {_f(reacq_m):.2f}s > {REACQ_PASS_S}s")
    avg_fps = _f(summary.get("avg_fps"))
    e2e_fps = _f(summary.get("e2e_fps"))
    if fps_min > 0 and avg_fps < fps_min and e2e_fps < fps_min:
        reasons.append(f"fps {avg_fps:.1f}/{e2e_fps:.1f} < {fps_min:g}")

    reached = bool(_names(stages, sm_states) & {"TRACKING", "LOCKED"})
    if intermittent:
        reasons += _intermittent_reasons(summary, reached)
    elif cold:
        if not reached:
            reasons.append("never reached TRACKING")
        if post_lock_pct is None:
            reasons.append("never acquired")
        elif post_lock_pct < POST_LOCK_PASS_PCT:
            reasons.append(f"post-lock {post_lock_pct:.1f}% < {POST_LOCK_PASS_PCT}%")
    else:
        loss = summary.get("target_loss_pct")
        if loss is None or math.isnan(_f(loss, float("nan"))):
            reasons.append("loss% unavailable")
        elif _f(loss) >= LOSS_PASS_PCT:
            reasons.append(f"loss {_f(loss):.1f}% >= {LOSS_PASS_PCT}%")
        acq = summary.get("acquisition_time_s")
        if acq is None:
            reasons.append("never acquired")
        elif _f(acq) > ACQ_PASS_S:
            reasons.append(f"acq {_f(acq):.2f}s > {ACQ_PASS_S}s")
    return (len(reasons) == 0, reasons)


def traversal_verdict(res, cfg):
    """(ok, reasons) -- pipeline-health gate, independent of dashboard tuning.

    Proves the search-to-track chain works end to end: the run completed
    without exceptions, processed every requested frame (synthetic input),
    reached a real track, and held (or repeatedly re-acquired) it.
    Intermittent beacons use the duty-cycle rule; all others must hold
    post-lock retention. RMSE is included so a diverging filter cannot pass
    on lock flags alone.
    """
    if not isinstance(res, dict) or res.get("error"):
        err = res.get("error", "crash") if isinstance(res, dict) else "crash"
        return False, [f"crashed: {err}"]
    s = res.get("summary") or {}
    reasons = []

    frames_run = res.get("frames_run")
    if frames_run is not None:
        if frames_run == 0:
            return False, ["no frames processed"]
        req = res.get("frames_requested")
        if req and not res.get("is_video") and frames_run < req:
            reasons.append(f"source ended early ({frames_run}/{req} frames)")

    r = _rmse_problem(s, res.get("has_gt", True))
    if r:
        reasons.append(r)
    reached = bool(_names(res.get("stages"), res.get("sm_states")) & {"TRACKING", "LOCKED"})
    if has_intermittent_target(cfg):
        reasons += _intermittent_reasons(s, reached)
    else:
        if not reached:
            reasons.append("never reached TRACKING")
        post = res.get("post_lock_pct")
        if post is None:
            reasons.append("never acquired")
        elif post < POST_LOCK_PASS_PCT:
            reasons.append(f"post-lock {post:.1f}% < {POST_LOCK_PASS_PCT}%")
    return (len(reasons) == 0, reasons)


def _fmt_verdict(ok, reasons):
    return "PASS" if ok else "FAIL (" + "; ".join(reasons) + ")"


# --------------------------------------------------------------------------
# Fuzz scenarios are sampled by scenario_gen (next to this file) inside
# validated ranges; every run is exactly reproducible from its printed seed.
# --------------------------------------------------------------------------


def _compute_in_fov(source, gt, tag):
    """Host-side camera context from pre-move geometry (matches the frame
    pixels). None when unknown (video sources / missing or sentinel gt).

    The old `world_pos not in (None, (0, 0))` raised on ndarray world_pos
    (ambiguous truth value), which the surrounding except swallowed -- so
    in_fov was silently always None for array positions."""
    cam = getattr(source, "camera", None)
    if cam is None or gt is None:
        return None
    try:
        wp = getattr(gt, "world_pos", None)
        if wp is None:
            return None
        arr = np.asarray(wp, dtype=float)
        if arr.shape == (2,) and not arr.any():   # (0, 0) == "no ground truth"
            return None
        return cam.world_to_image(wp) is not None
    except Exception as e:
        _warn_once(tag, "in_fov", e)
        return None


def _close(obj, tag):
    for name in ("release", "close"):
        fn = getattr(obj, name, None)
        if callable(fn):
            try:
                fn()
            except Exception as e:
                _warn_once(tag, f"source.{name}", e)
            return


def run_single(cfg, frames, seed=42, every=30, live=False, no_cue=False,
               use_logger=True, tag="run", video_path=None, video_gt=None,
               video_native_fps=False):
    """Headless mirror of MainWindow._tick (no Qt, no views)."""
    cfg = copy.deepcopy(cfg)
    # Make the whole run reproducible, not just the synthetic source: detectors
    # / trackers using python or numpy global RNGs now see the printed seed.
    random.seed(seed)
    np.random.seed(seed % (2 ** 32))

    # Benchmark-2: external video bypasses the PTZ camera (measurement only).
    is_video = bool(video_path or (cfg.get("experiment", {}).get("input_mode") == "VIDEO"
                                   and cfg.get("experiment", {}).get("video_path")))
    has_gt = True
    if is_video:
        from fsoc_tracker.input.video_source import VideoSource
        vpath = video_path or cfg["experiment"]["video_path"]
        ann = video_gt or cfg["experiment"].get("video_annotations_path") or None
        if isinstance(ann, str):
            ann = ann.strip() or None
        has_gt = ann is not None
        source = VideoSource(vpath, target_fps=30.0,
                             centre_offset_x=float(cfg["camera"].get("video_centre_offset_x", 0)),
                             centre_offset_y=float(cfg["camera"].get("video_centre_offset_y", 0)),
                             annotations_path=ann, native_fps=bool(video_native_fps))
        no_cue = True  # cue is synthetic-only; video has no gimbal to cue
    else:
        source = SyntheticSource(cfg, seed=seed)

    logger = None
    try:
        # Canonical pipeline: exactly one detector + tracker + controller,
        # owned by the SearchTrackPipeline (no separate constructions).
        pipe = make_pipeline(cfg)
        controller = pipe.controller
        metrics = MetricsCollector()
        metrics.input_fps = float(getattr(source, "fps", cfg["camera"]["fps"]))
        # Anchored to the repo, not the CWD, so runs from any directory land together.
        logger = RobustPerfLogger(base_dir=os.path.join(ROOT, "outputs", "runs"),
                                  metrics_collector=metrics) if use_logger else None
        display = DisplayTracker(cfg)

        metrics.start_run()
        if logger is not None:
            logger.begin_run(cfg)
        pipe.reset()
        source.reset()
        if not no_cue and hasattr(source, "cue_camera_to_target"):
            source.cue_camera_to_target()
        display.reset()

        fps = float(cfg["camera"]["fps"])
        upd = float(cfg["camera"].get("update_interval_hz", fps))
        dt_ctrl = 1.0 / max(upd, 1)
        fps_smooth = float(getattr(source, "fps", fps))
        last_t = time.perf_counter()
        last_state = last_tele = None
        last_raw = last_fused = None
        stages = set()
        sm_states = set()
        locked_flags = []
        soft_errors = {}
        frames_run = 0
        t0 = time.perf_counter()

        def soft(key, exc):
            soft_errors[key] = soft_errors.get(key, 0) + 1
            _warn_once(tag, key, exc)

        for i in range(frames):
            f0 = time.perf_counter()
            frame, gt = source.read()
            if frame is None:
                break
            frames_run += 1
            _in_fov = _compute_in_fov(source, gt, tag)
            try:
                _at_lim = bool(source.camera.is_at_limit(
                    getattr(controller, "prev_pan_rate", 0.0),
                    getattr(controller, "prev_tilt_rate", 0.0))) \
                    if hasattr(source, "camera") else False
            except Exception as e:
                soft("at_limit", e)
                _at_lim = False
            try:
                _ego = (float(getattr(controller, "prev_pan_rate", 0.0)),
                        float(getattr(controller, "prev_tilt_rate", 0.0)))
            except Exception as e:
                soft("ego_rate", e)
                _ego = (0.0, 0.0)
            # Canonical per-frame chain (predict -> gate -> detect -> estimate ->
            # state -> control, command held between control ticks internally).
            # Ground truth is NOT passed: the pipeline decides from pixels alone.
            detection, estimate, cmd = pipe.step_frame(
                frame, dt=dt_ctrl, in_fov=_in_fov, at_limit=_at_lim, ego_rate=_ego)
            if _in_fov is None and detection.valid:
                _in_fov = True   # video: no gimbal geometry, follow detection
            is_ptz = getattr(source, "is_ptz_enabled", not is_video)
            if is_ptz:
                source.apply_camera_command(cmd.pan_rate, cmd.tilt_rate, dt_ctrl)

            proc_ms = (time.perf_counter() - f0) * 1000
            now = time.perf_counter()
            inst = 1.0 / max(now - last_t, 1e-6)
            last_t = now
            fps_smooth = 0.85 * fps_smooth + 0.15 * inst

            pos_args = (frame.frame_id, frame.timestamp, detection.valid,
                        estimate, gt, proc_ms, fps_smooth,
                        cmd.pan_rate if is_ptz else 0, cmd.tilt_rate if is_ptz else 0)
            kw = dict(detection_confidence=detection.confidence,
                      saturated=cmd.saturated if is_ptz else False,
                      input_fps=float(getattr(source, "fps", fps)),
                      detection_centroid=detection.centroid_px if detection.valid else None,
                      search_case=getattr(cmd, "search_case", ""))
            (logger.log_frame if logger is not None else metrics.update)(*pos_args, **kw)

            try:
                sm = getattr(pipe.tracker, "sm", None)
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
            except Exception as e:
                soft("display.update", e)
            try:
                st = getattr(estimate.tracking_state, "value", "?")
                sm_states.add(st)
                locked_flags.append(1 if st == "LOCKED" else 0)
            except Exception as e:
                soft("tracking_state", e)
                locked_flags.append(0)   # keep flags aligned with frames
            last_raw = detection.centroid_px if detection.valid else None
            last_fused = estimate.pos_px

            if live or (every > 0 and (i + 1) % every == 0):
                s = metrics.summary()
                lbl = _ascii(last_state.label, "?") if last_state is not None else "?"
                print(f"[{tag} f{i + 1:4d}/{frames}] {lbl:22s} "
                      f"valid={int(_f(s.get('valid_detections'))):4d} fps={fps_smooth:5.1f} "
                      f"lat={_f(s.get('avg_processing_ms')):5.1f}ms "
                      f"rmse={_f(s.get('rmse_px')):5.1f}px "
                      f"lock={_f(s.get('lock_retention_pct')):5.1f}% "
                      f"case={getattr(cmd, 'search_case', '')}", flush=True)
    finally:
        # Always flush the CSV logger and free the source, even on a crash
        # mid-run (previously: end_run skipped, video handle leaked).
        if logger is not None:
            try:
                logger.end_run()
            except Exception as e:
                _warn_once(tag, "logger.end_run", e)
        _close(source, tag)

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
            "post_lock_pct": post, "frames_run": frames_run,
            "frames_requested": frames, "is_video": is_video,
            "has_gt": has_gt, "soft_errors": soft_errors}


def print_status(res, title="STATUS"):
    # ASCII-only so output stays clean on any terminal/codepage.
    s = res["summary"]
    st = res.get("state")
    tele = res.get("tele")
    raw, fused = res.get("raw"), res.get("fused")
    acq = s.get("acquisition_time_s")
    reacq_m = s.get("reacquisition_mean_s")
    g = lambda k: _f(s.get(k))   # noqa: E731  (missing/NaN-safe numeric read)
    print(f"--- {title} ---")
    print(f"State               : {_ascii(st.label, '?') if st is not None else '?'}")
    print(f"Valid Detections    : {int(g('valid_detections'))}")
    print(f"Average Confidence  : {g('avg_confidence') * 100:.1f}%")
    print(f"Raw Centroid (x, y) : {f'{raw[0]:.1f}, {raw[1]:.1f}' if raw is not None else '--'}")
    try:
        fz = f"{fused[0]:.1f}, {fused[1]:.1f}" if fused is not None else "--"
    except Exception:
        fz = "--"
    print(f"Fused Centroid      : {fz}")
    print(f"FPS                 : {_f(res.get('fps_smooth', s.get('avg_fps'))):.1f} "
          f"(avg {g('avg_fps'):.1f} / e2e {g('e2e_fps'):.1f}, in {g('input_fps'):.0f})")
    print(f"Average Latency     : {g('avg_processing_ms'):.1f} ms")
    print(f"Maximum Latency     : {g('max_processing_ms'):.1f} ms")
    print(f"Mean / Max Error    : {g('mean_error_px'):.1f} / {g('max_error_px'):.1f} px")
    print(f"RMSE / P95 Error    : {g('rmse_px'):.1f} / {g('p95_error_px'):.1f} px")
    print(f"Centroid RMSE / Max : {g('centroid_rmse_px'):.1f} / {g('centroid_max_error_px'):.1f} px (see centroiding_error.csv)")
    print(f"Lock Retention      : {g('lock_retention_pct'):.1f}%")
    print(f"Target Loss & Count : {g('target_loss_pct'):.1f}% ({int(g('loss_count'))})")
    try:
        _cases = s.get("search_case_counts", {}) or {}
        if _cases:
            print("Search Cases        : " + " ".join(f"{k}={v}" for k, v in sorted(_cases.items())))
    except Exception:
        pass
    print(f"Acquisition T & Cnt : {f'{_f(acq):.2f}s' if acq is not None else '--'} ({int(g('acquisition_count'))})")
    print(f"Reacq T Mean & Cnt  : {f'{_f(reacq_m):.2f}s' if reacq_m is not None else '--'} ({int(g('reacquisition_count'))})")
    if tele is not None:
        dc = f"{tele.det_conf * 100:.0f}%" if tele.det_conf is not None else "--"
        ag = f"{tele.track_age_s:.2f} s" if tele.track_age_s is not None else "--"
        la = f"{tele.last_detect_age_s:.2f} s" if tele.last_detect_age_s is not None else "--"
        print(f"TRACK {_ascii(tele.track_label)} | DET {dc} | AGE {ag} | LAST {la} | {_ascii(tele.fov)}")
    # entire-pipeline proof: which display stages + tracker SM states were hit
    seen = _names(res.get("stages"))
    print("PIPELINE STAGES : " + "  ".join(f"[{'x' if n in seen else ' '}] {n}" for n in STAGE_ORDER))
    try:
        print("TRACKER SM      : " + " ".join(sorted(_names(res.get("sm_states")))))
    except Exception:
        pass
    if res.get("post_lock_pct") is not None:
        print(f"POST-LOCK HOLD  : {res['post_lock_pct']:.1f}% (from frame {res['first_lock_idx'] + 1})")
    if res.get("frames_run") is not None:
        print(f"Frames run          : {res['frames_run']}/{res.get('frames_requested')}")
    print(f"Frames/Dropped/Dur  : {int(g('total_frames'))}/{int(g('dropped_frames'))}/{g('duration_s'):.1f}s "
          f"| wall {g('wall_s'):.1f}s")
    if res.get("soft_errors"):
        print("SWALLOWED ERRORS: " + ", ".join(f"{k}x{v}" for k, v in sorted(res["soft_errors"].items()))
              + "  (pipeline kept running; investigate)")


def run_suite_item(tag, desc, cfg, frames, seed, cold, args, repro=None):
    """Run one scenario crash-safely; print status + both verdicts.

    Returns (tag, dash_ok, dash_reasons, trav_ok, trav_reasons, summary|None,
    post_lock|None, seed, frames). A crash is a traversal FAIL and never
    aborts the suite.
    """
    print(f"\n===== {tag}: {desc} =====")
    print(f"SEED {seed} | frames {frames} | cue={'ON' if not cold else 'OFF'}"
          + (f" | repro: {repro}" if repro else ""))
    if getattr(args, "show_overrides", False):
        print(f"CONFIG target={cfg.get('target')} camera={cfg.get('camera')}")
    try:
        res = run_single(cfg, frames, seed=seed, every=0,
                         live=args.live, no_cue=cold,
                         use_logger=not args.no_log, tag=tag)
    except Exception as e:
        err = f"{type(e).__name__}: {e}"
        print(f"CRASH {tag}: {err}")
        traceback.print_exc(limit=5)
        return (tag, False, [f"crashed: {err}"], False, [f"crashed: {err}"],
                None, None, seed, frames)
    print_status(res, title=tag)
    intermittent = has_intermittent_target(cfg)
    dash_ok, dash_reasons = verdict(res["summary"], cold=cold,
                                    post_lock_pct=res.get("post_lock_pct"),
                                    stages=res.get("stages", set()),
                                    intermittent=intermittent,
                                    sm_states=res.get("sm_states", set()),
                                    fps_min=args.fps_min, has_gt=res.get("has_gt", True))
    trav_ok, trav_reasons = traversal_verdict(res, cfg)
    print(f"VERDICT-DASH {tag}: {_fmt_verdict(dash_ok, dash_reasons)}")
    print(f"VERDICT-TRAV {tag}: {_fmt_verdict(trav_ok, trav_reasons)}")
    return (tag, dash_ok, dash_reasons, trav_ok, trav_reasons,
            res["summary"], res.get("post_lock_pct"), seed, frames)


def print_suite_summary(results, title="SUITE SUMMARY"):
    print(f"\n===== {title} =====")
    for (n, dok, dreasons, tok, treasons, s, post, seed, fr) in results:
        dflag = _fmt_verdict(dok, dreasons)
        tflag = _fmt_verdict(tok, treasons)
        if s is None:
            print(f"{n:22s} DASH={dflag:40s} TRAV={tflag:40s} CRASH seed={seed}")
            continue
        extra = f" postlock={post:.1f}%" if post is not None else ""
        print(f"{n:22s} DASH={dflag:40s} TRAV={tflag:40s} "
              f"rmse={_f(s.get('rmse_px')):5.1f} lock={_f(s.get('lock_retention_pct')):5.1f}% "
              f"valid={int(_f(s.get('valid_detections')))}{extra} seed={seed} f={fr}")
    nd = sum(1 for r in results if r[1])
    nt = sum(1 for r in results if r[3])
    print(f"DASH {nd}/{len(results)} PASS | TRAV {nt}/{len(results)} PASS")


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------
def _pos_int(text):
    v = int(text)
    if v <= 0:
        raise argparse.ArgumentTypeError(f"must be a positive integer, got {text}")
    return v


def _nonneg_int(text):
    v = int(text)
    if v < 0:
        raise argparse.ArgumentTypeError(f"must be >= 0, got {text}")
    return v


def build_cfg(args, ov=None, far_start=False):
    """Config = file/defaults (+--set, so load_config validates/derives it)
    -> far-start -> scenario overrides -> --set AGAIN so the user's explicit
    overrides always win. (Suites used to let scenario values clobber --set.)"""
    set_ov = parse_set(args.set)
    cfg = load_config(args.config, overrides=set_ov or None)
    if far_start:
        cfg = deep_merge(cfg, FAR_START)
    if ov:
        cfg = deep_merge(cfg, ov)
    if set_ov:
        cfg = deep_merge(cfg, set_ov)
    return cfg


def resolve_scenario(name):
    """Exact name, else a unique case-insensitive prefix. None if no match."""
    if name in SCENARIOS:
        return name
    hits = [n for n in SCENARIOS if n.lower().startswith(name.lower())]
    if len(hits) == 1:
        return hits[0]
    if len(hits) > 1:
        print(f"ambiguous scenario {name!r}: {', '.join(hits)}")
    else:
        print(f"unknown scenario {name!r} (see --list)")
    return None


def build_parser():
    ap = argparse.ArgumentParser(description="Headless PAT-SIM runner + extreme/fuzz/gauntlet suites.")
    ap.add_argument("--config", default=None, help="YAML config file (default: built-in defaults)")
    ap.add_argument("--frames", type=_pos_int, default=None, help="frames to run (default: full duration)")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--set", action="append", default=[], metavar="a.b=c",
                    help="config override, repeatable (values YAML-parsed; always wins over scenarios)")
    ap.add_argument("--every", type=_nonneg_int, default=60, help="progress line every N frames (0=off)")
    ap.add_argument("--live", action="store_true", help="print a line every frame")
    ap.add_argument("--no-log", action="store_true", help="skip outputs/runs CSV logging")
    ap.add_argument("--cue", action="store_true",
                    help="assisted start: cue camera to target (default: cold far-start)")
    ap.add_argument("--no-far-start", action="store_true",
                    help="skip the default far-corner target geometry (pure config)")
    ap.add_argument("--extreme", action="store_true", help="run the full extreme suite")
    ap.add_argument("--scenario", default=None, help="run one scenario (name or unique prefix; see --list)")
    ap.add_argument("--list", action="store_true", help="list extreme scenarios and exit")
    ap.add_argument("--strict", action="store_true",
                    help="exit 1 on ANY FAIL: single runs gate on DASH and TRAV; "
                         "fuzz/gauntlet add the DASH gate to the default TRAV gate")
    ap.add_argument("--fps-min", type=float, default=FPS_MIN, metavar="FPS",
                    help=f"FPS gate for the DASH verdict (default {FPS_MIN:g}; 0 disables -- "
                         "use on loaded/slow CI machines to avoid flaky verdicts)")
    ap.add_argument("--show-overrides", action="store_true",
                    help="print each suite scenario's target/camera config before running")
    ap.add_argument("--video", default=None, help="Benchmark-2: external .mp4 (PTZ bypassed, normalized to 30fps)")
    ap.add_argument("--video-gt", default=None, help="Benchmark-2 annotations CSV: frame_id,x,y[,visible]")
    ap.add_argument("--video-native-fps", action="store_true",
                    help="use native video FPS instead of normalizing to 30fps")
    ap.add_argument("--fuzz", type=_nonneg_int, default=0, metavar="N",
                    help="run N seeded random scenarios (inside validated ranges)")
    ap.add_argument("--fuzz-seed", type=int, default=None,
                    help="RNG seed for --fuzz sampling (default: --seed)")
    ap.add_argument("--fuzz-pick", type=_pos_int, action="append", default=[], metavar="K",
                    help="run only FUZZ-K (1-based, repeatable) from the --fuzz N/--fuzz-seed sequence")
    ap.add_argument("--gauntlet", action="store_true",
                    help="extreme suite + fuzz batch (default 20; set with --fuzz)")
    return ap


def main(argv=None):
    ap = build_parser()
    args = ap.parse_args(argv)

    if args.list:
        for name, (desc, _ov, fr) in SCENARIOS.items():
            print(f"{name:20s} [{fr} frames] {desc}")
        print("--fuzz N / --gauntlet add seeded random scenarios (see --help)")
        return 0

    # ---- argument sanity (silently ignored flags used to hide mistakes) -------
    suite_mode = args.extreme or args.fuzz or args.gauntlet
    if args.scenario and suite_mode:
        ap.error("--scenario cannot be combined with --extreme/--fuzz/--gauntlet")
    if (args.video or args.video_gt) and (suite_mode or args.scenario):
        ap.error("--video/--video-gt only apply to a single run, not scenario/suite modes")
    if args.fuzz_pick and not (args.fuzz or args.gauntlet):
        ap.error("--fuzz-pick needs --fuzz N (and the same --fuzz-seed) or --gauntlet")
    if args.fps_min < 0:
        ap.error("--fps-min must be >= 0")
    try:   # fail fast on a bad --set / --config, before any scenario starts
        parse_set(args.set)
        build_cfg(args)
    except Exception as e:
        print(f"config error: {type(e).__name__}: {e}")
        return 2

    cold = not args.cue   # stress/fuzz start far: cold unless --cue

    # ---- single named scenario --------------------------------------------
    if args.scenario:
        n = resolve_scenario(args.scenario)
        if n is None:
            return 2
        desc, ov, fr = SCENARIOS[n]
        for p in validate_overrides(ov):
            print(f"WARN preset {n}: {p}")
        cfg = build_cfg(args, ov)
        r = run_suite_item(n, desc, cfg, args.frames or fr, args.seed, cold, args)
        print_suite_summary([r], title="SINGLE SUMMARY")
        _n, dok, _dr, tok, _tr, _s, _post, _seed, _fr = r
        return 1 if (args.strict and not (dok and tok)) else 0

    # ---- suites: extreme / fuzz / gauntlet ----------------------------------
    if suite_mode:
        items = []
        if args.extreme or args.gauntlet:
            for n, (desc, ov, fr) in SCENARIOS.items():
                for p in validate_overrides(ov):
                    print(f"WARN preset {n}: {p}")
                items.append((n, desc, build_cfg(args, ov), args.frames or fr,
                              args.seed, cold, None))
        n_fuzz = args.fuzz if args.fuzz else (20 if args.gauntlet else 0)
        if n_fuzz > 0:
            fuzz_seed = args.fuzz_seed if args.fuzz_seed is not None else args.seed
            bad = [k for k in args.fuzz_pick if k > n_fuzz]
            if bad:
                ap.error(f"--fuzz-pick {bad} exceeds --fuzz {n_fuzz}")
            picks = set(args.fuzz_pick)
            print(f"FUZZ: {n_fuzz} scenarios, fuzz-seed {fuzz_seed}"
                  + (f", picking {sorted(picks)}" if picks else ""))
            rng = random.Random(fuzz_seed)
            for k in range(1, n_fuzz + 1):
                # ALWAYS draw, then filter, so FUZZ-K is identical with or
                # without --fuzz-pick (the RNG stream is order dependent).
                desc, ov, fr = random_scenario(rng)
                run_seed = rng.randrange(2 ** 31 - 1)
                if picks and k not in picks:
                    continue
                repro = (f"python headless.py --fuzz {n_fuzz} --fuzz-seed {fuzz_seed} "
                         f"--fuzz-pick {k}" + (f" --frames {args.frames}" if args.frames else ""))
                items.append((f"FUZZ-{k:02d}", desc, build_cfg(args, ov),
                              args.frames or fr, run_seed, cold, repro))
        if not items:
            print("nothing to run (see --extreme / --fuzz / --gauntlet)")
            return 2
        results = []
        try:
            for (tag, desc, cfg, fr, seed, cold_, repro) in items:
                results.append(run_suite_item(tag, desc, cfg, fr, seed, cold_, args, repro=repro))
        except KeyboardInterrupt:
            print("\ninterrupted -- partial results follow")
            if results:
                print_suite_summary(results, title="PARTIAL SUMMARY (interrupted)")
            return 130
        title = "GAUNTLET SUMMARY" if args.gauntlet else (
            "EXTREME SUITE SUMMARY" if args.extreme and not args.fuzz else "FUZZ SUMMARY")
        print_suite_summary(results, title=title)
        failed = [r[0] for r in results if not r[3]] if (args.gauntlet or args.fuzz) \
            else [r[0] for r in results if not r[1]]
        if args.strict and (args.gauntlet or args.fuzz):
            failed += [r[0] for r in results if not r[1] and r[0] not in failed]
        if failed:
            print("FAILED: " + ", ".join(failed))
        # Pipeline-health gate (TRAV) drives fuzz/gauntlet exit; extreme-only uses DASH.
        return 1 if failed else 0

    # ---- default single run -------------------------------------------------
    base = build_cfg(args, far_start=not args.no_far_start)
    exp = base.get("experiment", {})
    is_video_run = bool(args.video or (exp.get("input_mode") == "VIDEO" and exp.get("video_path")))
    cold = (not args.cue) and not is_video_run
    if is_video_run and not args.video:
        # config-driven video run: force PTZ-bypass path via run_single detection
        args.video = exp["video_path"]
        if not args.video_gt:
            args.video_gt = exp.get("video_annotations_path") or None
    fps = 30.0 if is_video_run else float(base["camera"]["fps"])  # Benchmark-2 reference rate
    if args.frames:
        frames = args.frames
    else:
        dur = exp.get("duration_s")
        if dur is None:
            print("config error: experiment.duration_s missing; pass --frames")
            return 2
        frames = max(1, int(round(float(dur) * fps)))
    if is_video_run:
        print(f"INPUT: video {args.video} (PTZ bypassed @30fps)"
              + (f" + annotations {args.video_gt}" if args.video_gt else " (no annotations: RMSE not gated)"))
    else:
        t = base.get("target", {})
        print(f"GEOMETRY: target start {t.get('initial_pos')} "
              f"({t.get('initial_mode')}, {t.get('trajectory')} "
              f"@ {t.get('speed_px_per_frame')}px/f), "
              f"camera {base['camera'].get('initial_position')}, cue={'ON' if args.cue else 'OFF'}")
    print(f"SEED {args.seed} | frames {frames}")
    try:
        res = run_single(base, frames, seed=args.seed, every=args.every if not args.live else 1,
                         live=args.live, no_cue=not args.cue,
                         use_logger=not args.no_log, tag="run",
                         video_path=args.video, video_gt=args.video_gt,
                         video_native_fps=args.video_native_fps)
    except KeyboardInterrupt:
        print("\ninterrupted")
        return 130
    except Exception as e:
        print(f"CRASH run: {type(e).__name__}: {e}")
        traceback.print_exc(limit=8)
        return 3
    print_status(res)
    ok, reasons = verdict(res["summary"], cold=cold,
                          post_lock_pct=res.get("post_lock_pct"),
                          stages=res.get("stages", set()),
                          intermittent=has_intermittent_target(base),
                          sm_states=res.get("sm_states", set()),
                          fps_min=args.fps_min, has_gt=res.get("has_gt", True))
    print(f"VERDICT-DASH: {_fmt_verdict(ok, reasons)}")
    tok, treasons = traversal_verdict(res, base)
    print(f"VERDICT-TRAV: {_fmt_verdict(tok, treasons)}")
    return 1 if (args.strict and not (ok and tok)) else 0


if __name__ == "__main__":
    sys.exit(main())