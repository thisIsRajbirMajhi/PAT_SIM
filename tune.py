#!/usr/bin/env python3
"""Optuna tuner for the pat_pipeline controller/filter/search parameters.

Wraps headless.run_single as the evaluator: each trial proposes parameters,
runs them over fixed seeded scenarios, and scores deterministic metrics
only (RMSE, post-lock hold, lock retention). Wall-clock timings (acquisition
seconds, FPS) are NEVER scored -- they measure machine load, not quality.

    python tune.py --trials 30                        # PID+filter space, X1/X4/X6
    python tune.py --trials 30 --space search         # search-behavior space
    python tune.py --trials 50 --space all --frames 900
    python tune.py --trials 5 --scenarios X1-baseline --frames 120   # smoke test

Resume any run: same --study/--storage accumulates trials (load_if_exists).
Apply the winner with the printed --set flags, then confirm at full
duration with: headless.py --extreme
"""
import argparse
import copy
import os
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(ROOT, "src"))

import headless

try:
    import optuna
    from optuna.pruners import MedianPruner
except ImportError:
    print("optuna is required: .venv/Scripts/python -m pip install optuna")
    sys.exit(2)

# Fixed evaluation set: diverse, seeded, cold far-start (mirrors --extreme).
DEFAULT_SCENARIOS = ["X1-baseline", "X4-speed-demon", "X6-blink-dropout"]
WORST = 1e6

# Search spaces (all inside config/validation caps).
SPACES = {
    "pid": {
        "controller.kp_pan": ("float", 0.5, 2.5),
        "controller.kp_tilt": ("float", 0.5, 2.5),
        "controller.ki": ("float", 0.0, 0.2),
        "controller.kd": ("float", 0.0, 0.5),
        "controller.deadzone_px": ("float", 0.5, 4.0),
        "controller.integral_limit": ("float", 4.0, 12.0),
        "controller.feedforward_gain": ("float", 0.0, 1.0),
        "tracker.meas_noise": ("float", 1.0, 8.0),
        "tracker.process_noise": ("float", 0.2, 2.0),
    },
    "search": {
        "controller.search_angle_step": ("float", 0.2, 0.8),
        "controller.search_radius_step": ("float", 0.04, 0.2),
        "controller.search_radius_max": ("float", 2.0, 6.0),
        "controller.spiral_phase_s": ("float", 1.5, 5.0),
        "controller.raster_pan_scale": ("float", 0.5, 1.0),
        "controller.intercept_gain": ("float", 1.0, 3.0),
    },
    "detector": {
        "detector.threshold_k": ("float", 2.0, 5.0),
        "detector.min_area": ("int", 4, 16),
        "detector.blur_ksize": ("cat", [3, 5]),
    },
}


def set_nested(cfg, dotted, value):
    node = cfg
    parts = dotted.split(".")
    for p in parts[:-1]:
        node = node.setdefault(p, {})
    node[parts[-1]] = value


def suggest_all(trial, space):
    out = {}
    for key, spec in space.items():
        kind = spec[0]
        if kind == "float":
            out[key] = trial.suggest_float(key, spec[1], spec[2])
        elif kind == "int":
            out[key] = trial.suggest_int(key, spec[1], spec[2])
        elif kind == "cat":
            out[key] = trial.suggest_categorical(key, spec[1])
    return out


def score_run(res):
    """Deterministic scalar (lower is better) from one run_single result."""
    s = res["summary"]
    stages = res.get("stages", set())
    sm_states = res.get("sm_states", set())
    names = {getattr(x, "value", x) if not isinstance(x, str) else x for x in stages}
    names |= {getattr(x, "value", x) if not isinstance(x, str) else x for x in sm_states}
    if "TRACKING" not in names and "LOCKED" not in names:
        return None  # never tracked: bail out, worst score
    try:
        rmse = float(s.get("rmse_px", 0) or 0)
    except Exception:
        rmse = 0.0
    post = res.get("post_lock_pct") or 0.0
    try:
        lock = float(s.get("lock_retention_pct", 0) or 0)
    except Exception:
        lock = 0.0
    return rmse + 0.5 * (100.0 - post) + 0.2 * (100.0 - lock)


def make_objective(args, space, base_cfgs):
    def objective(trial):
        params = suggest_all(trial, space)
        ov = {}
        for key, val in params.items():
            set_nested(ov, key, val)
        total, n = 0.0, 0
        for idx, (name, cfg, frames) in enumerate(base_cfgs):
            try:
                res = headless.run_single(
                    headless.deep_merge(cfg, copy.deepcopy(ov)),
                    frames, seed=args.seed, every=0,
                    live=False, no_cue=True,
                    use_logger=False, tag=f"t{trial.number}-{name}")
            except Exception as e:
                print(f"[trial {trial.number}] {name} CRASH: {type(e).__name__}: {e}",
                      flush=True)
                return WORST
            sc = score_run(res)
            if sc is None:
                print(f"[trial {trial.number}] {name} never tracked -> bail", flush=True)
                return WORST
            total += sc
            n += 1
            trial.report(total / n, idx)
            if trial.should_prune():
                print(f"[trial {trial.number}] pruned after {name}", flush=True)
                raise optuna.TrialPruned()
        mean = total / max(n, 1)
        print(f"[trial {trial.number}] score={mean:.2f} params={params}", flush=True)
        return mean
    return objective


def main(argv=None):
    ap = argparse.ArgumentParser(description="Optuna tuner for pat_pipeline parameters.")
    ap.add_argument("--trials", type=int, default=30)
    ap.add_argument("--timeout", type=int, default=None, help="seconds budget (optional)")
    ap.add_argument("--space", default="pid", choices=["pid", "search", "detector", "all"],
                    help="parameter group to tune (default: pid)")
    ap.add_argument("--scenarios", default=",".join(DEFAULT_SCENARIOS),
                    help="comma-separated scenario names (fixed seeds)")
    ap.add_argument("--frames", type=int, default=600, help="cap frames per run")
    ap.add_argument("--seed", type=int, default=42, help="fixed sim seed for all trials")
    ap.add_argument("--study", default="pat_tune", help="study name (resume with same name)")
    ap.add_argument("--storage", default="outputs/tune.db",
                    help="sqlite path for the study (resume-safe)")
    ap.add_argument("--config", default=None)
    ap.add_argument("--n-jobs", type=int, default=1)
    args = ap.parse_args(argv)

    names = [n.strip() for n in args.scenarios.split(",") if n.strip()]
    for n in names:
        if n not in headless.SCENARIOS:
            print(f"unknown scenario {n!r} (see headless.py --list)")
            return 2
    space = {}
    for grp in (["pid", "search", "detector"] if args.space == "all" else [args.space]):
        space.update(SPACES[grp])
    print(f"space={args.space} ({len(space)} params) scenarios={names} "
          f"frames<={args.frames} seed={args.seed}")

    base_cfgs = []
    for n in names:
        _desc, ov, fr = headless.SCENARIOS[n]
        cfg = headless.deep_merge(
            headless.load_config(args.config), copy.deepcopy(ov))
        base_cfgs.append((n, cfg, min(args.frames, fr)))

    os.makedirs(os.path.dirname(args.storage) or ".", exist_ok=True)
    study = optuna.create_study(
        direction="minimize",
        sampler=optuna.samplers.TPESampler(seed=args.seed),
        pruner=MedianPruner(n_startup_trials=5),
        storage=f"sqlite:///{args.storage}",
        study_name=args.study, load_if_exists=True)
    study.optimize(make_objective(args, space, base_cfgs),
                   n_trials=args.trials, timeout=args.timeout,
                   n_jobs=args.n_jobs, show_progress_bar=False)

    print(f"\nbest score: {study.best_value:.2f} (trial {study.best_trial.number})")
    flags = " ".join(f"--set {k}={v}" for k, v in study.best_params.items())
    print(f"apply with: headless.py --extreme {flags}")
    print(f"resume with: tune.py --study {args.study} --storage {args.storage}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
