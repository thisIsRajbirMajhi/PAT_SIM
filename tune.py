#!/usr/bin/env python3
"""Optuna tuner for the pat_pipeline controller/filter/search parameters.

Wraps headless.run_single as the evaluator: each trial proposes parameters,
runs them over a fixed seeded evaluation set (curated scenarios + fixed
fuzz draws), and scores deterministic metrics only (RMSE, post-lock hold,
lock retention). Wall-clock timings (acquisition seconds, FPS) are NEVER
scored -- they measure machine load, not quality.

    python tune.py --trials 30                        # PID+filter space
    python tune.py --stages "pid:30,search:20"        # phased: fix winners per phase
    python tune.py --stages "pid:30,search:20" --refine 10   # + narrowed re-tune
    python tune.py --hard                             # add X5 + X10 hell cases
    python tune.py --confirm 3 --study pat_tune       # re-check winner on fresh seeds
    python tune.py --trials 5 --scenarios X1-baseline --frames 120   # smoke test

Resume any run: same --study/--storage accumulates trials (load_if_exists).
Apply the winner with the printed --set flags, then confirm at full
duration with: headless.py --extreme
"""
import argparse
import copy
import json
import os
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(ROOT, "src"))

import headless
from scenario_gen import random_scenario

try:
    import optuna
    from optuna.pruners import MedianPruner
except ImportError:
    print("optuna is required: .venv/Scripts/python -m pip install optuna")
    sys.exit(2)

# Fixed evaluation set: diverse, seeded, cold far-start (mirrors --extreme).
DEFAULT_SCENARIOS = ["X1-baseline", "X4-speed-demon", "X6-blink-dropout"]
HARD_SCENARIOS = ["X5-tiny-target", "X10-combined-hell"]
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
        "tracker.gate_sigma": ("float", 3.0, 7.0),
        "tracker.lost_timeout_frames": ("int", 5, 30),
        "tracker.reacq_timeout_frames": ("int", 10, 60),
    },
    "search": {
        "controller.search_angle_step": ("float", 0.2, 0.8),
        "controller.search_radius_step": ("float", 0.04, 0.2),
        "controller.search_radius_max": ("float", 2.0, 6.0),
        "controller.search_rate_scale": ("float", 0.4, 1.2),
        "controller.spiral_phase_s": ("float", 1.5, 5.0),
        "controller.raster_pan_scale": ("float", 0.5, 1.0),
        "controller.raster_tilt_scale": ("float", 0.15, 0.6),
        "controller.stare_rate_scale": ("float", 0.1, 0.6),
        "controller.intercept_gain": ("float", 1.0, 3.0),
        "controller.intercept_lead_s": ("float", 0.1, 0.6),
        "controller.unc_scale": ("float", 0.2, 1.2),
        "controller.unc_max_boost": ("float", 1.5, 3.5),
        "controller.fast_vel_deg_s": ("float", 0.5, 2.0),
        "controller.give_up_frames": ("int", 300, 1200),
    },
    "detector": {
        "detector.threshold_k": ("float", 2.0, 5.0),
        "detector.min_area": ("int", 4, 16),
        "detector.max_area": ("int", 400, 1500),
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


def shrink_space(space, best, factor=0.25):
    """Narrow each range around the winning value (for --refine)."""
    out = {}
    for key, spec in space.items():
        if key not in best or spec[0] == "cat":
            out[key] = spec
            continue
        lo, hi = float(spec[1]), float(spec[2])
        half = factor * (hi - lo)
        b = float(best[key])
        if spec[0] == "int":
            out[key] = ("int", max(int(lo), int(round(b - half))),
                        min(int(hi), int(round(b + half))))
        else:
            out[key] = ("float", max(lo, b - half), min(hi, b + half))
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


def eval_params(params, eval_cfgs, seed, tag="eval", verbose=False):
    """Mean score of one param dict over the fixed eval set (raises on prune)."""
    ov = {}
    for key, val in params.items():
        set_nested(ov, key, val)
    total, n = 0.0, 0
    for (name, cfg, frames) in eval_cfgs:
        try:
            res = headless.run_single(
                headless.deep_merge(cfg, copy.deepcopy(ov)),
                frames, seed=seed, every=0,
                live=False, no_cue=True,
                use_logger=False, tag=f"{tag}-{name}")
        except Exception as e:
            if verbose:
                print(f"[{tag}] {name} CRASH: {type(e).__name__}: {e}", flush=True)
            return WORST
        sc = score_run(res)
        if sc is None:
            if verbose:
                print(f"[{tag}] {name} never tracked -> bail", flush=True)
            return WORST
        total += sc
        n += 1
    return total / max(n, 1)


def make_objective(space, fixed, eval_cfgs, seed):
    def objective(trial):
        params = dict(fixed)
        params.update(suggest_all(trial, space))
        ov = {}
        for key, val in params.items():
            set_nested(ov, key, val)
        total, n = 0.0, 0
        for idx, (name, cfg, frames) in enumerate(eval_cfgs):
            try:
                res = headless.run_single(
                    headless.deep_merge(cfg, copy.deepcopy(ov)),
                    frames, seed=seed, every=0,
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
        print(f"[trial {trial.number}] score={mean:.2f}", flush=True)
        return mean
    return objective


def open_study(args, name):
    os.makedirs(os.path.dirname(args.storage) or ".", exist_ok=True)
    return optuna.create_study(
        direction="minimize",
        sampler=optuna.samplers.TPESampler(seed=args.seed),
        pruner=MedianPruner(n_startup_trials=5),
        storage=f"sqlite:///{args.storage}",
        study_name=name, load_if_exists=True)


def save_best(args, study_name, space_name, best_value, best_params, eval_names):
    out = {"study": study_name, "space": space_name, "score": best_value,
           "params": best_params, "scenarios": eval_names,
           "frames": args.frames, "seed": args.seed}
    path = os.path.join("outputs", f"best_{study_name}.json")
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w") as f:
        json.dump(out, f, indent=1)
    flags = " ".join(f"--set {k}={v}" for k, v in best_params.items())
    print(f"best {study_name}: {best_value:.2f} -> {path}")
    print(f"apply with: headless.py --extreme {flags}")
    return path


def build_eval_cfgs(args):
    """Fixed eval set: named scenarios + seeded fuzz draws (same every run)."""
    names = [n.strip() for n in args.scenarios.split(",") if n.strip()]
    if args.hard:
        names += [n for n in HARD_SCENARIOS if n not in names]
    for n in names:
        if n not in headless.SCENARIOS:
            print(f"unknown scenario {n!r} (see headless.py --list)")
            return None
    base = headless.load_config(args.config)
    eval_cfgs = []
    for n in names:
        _desc, ov, fr = headless.SCENARIOS[n]
        cfg = headless.deep_merge(copy.deepcopy(base), copy.deepcopy(ov))
        eval_cfgs.append((n, cfg, min(args.frames, fr)))
    if args.fuzz_eval > 0:
        import random as _random
        rng = _random.Random(args.fuzz_eval_seed)
        for k in range(args.fuzz_eval):
            desc, ov, fr = random_scenario(rng)
            cfg = headless.deep_merge(copy.deepcopy(base), copy.deepcopy(ov))
            eval_cfgs.append((f"FUZZEVAL-{k + 1:02d}", cfg, min(args.frames, fr)))
    return eval_cfgs


def main(argv=None):
    ap = argparse.ArgumentParser(description="Optuna tuner for pat_pipeline parameters.")
    ap.add_argument("--trials", type=int, default=30)
    ap.add_argument("--timeout", type=int, default=None, help="seconds budget (optional)")
    ap.add_argument("--space", default="pid", choices=["pid", "search", "detector", "all"],
                    help="parameter group to tune (default: pid)")
    ap.add_argument("--stages", default=None, metavar="'pid:30,search:20'",
                    help="phased tuning: fix each phase's winners before the next")
    ap.add_argument("--refine", type=int, default=0, metavar="N",
                    help="extra trials with ranges shrunk around the winner")
    ap.add_argument("--scenarios", default="X1-baseline,X4-speed-demon,X6-blink-dropout",
                    help="comma-separated scenario names (fixed seeds)")
    ap.add_argument("--hard", action="store_true", help="add X5 + X10 hell cases")
    ap.add_argument("--fuzz-eval", type=int, default=2,
                    help="fixed seeded fuzz scenarios per trial (anti-overfit)")
    ap.add_argument("--fuzz-eval-seed", type=int, default=1234)
    ap.add_argument("--confirm", type=int, default=0, metavar="N",
                    help="re-evaluate the winner on N fresh seeds, report mean/std")
    ap.add_argument("--frames", type=int, default=600, help="cap frames per run")
    ap.add_argument("--seed", type=int, default=42, help="fixed sim seed for all trials")
    ap.add_argument("--study", default="pat_tune", help="study name (resume with same name)")
    ap.add_argument("--storage", default="outputs/tune.db",
                    help="sqlite path for the study (resume-safe)")
    ap.add_argument("--config", default=None)
    ap.add_argument("--n-jobs", type=int, default=1)
    args = ap.parse_args(argv)

    if args.confirm > 0:
        return cmd_confirm(args)

    eval_cfgs = build_eval_cfgs(args)
    if eval_cfgs is None:
        return 2
    eval_names = [n for (n, _c, _f) in eval_cfgs]
    print(f"eval={[n for n in eval_names]} frames<={args.frames} seed={args.seed}")

    fixed, phases = {}, []
    if args.stages:
        for chunk in args.stages.split(","):
            grp, num = chunk.strip().split(":")
            grp = grp.strip()
            if grp not in SPACES:
                print(f"unknown space {grp!r} (pid|search|detector)")
                return 2
            phases.append((grp, int(num)))
    else:
        groups = ["pid", "search", "detector"] if args.space == "all" else [args.space]
        per = max(1, args.trials // max(len(groups), 1))
        phases = [(g, per) for g in groups]
        if args.space == "all":
            print("note: --space all runs groups back-to-back; prefer --stages for control")

    for grp, num in phases:
        space = {k: v for k, v in SPACES[grp].items() if k not in fixed}
        if not space:
            continue
        sname = f"{args.study}_{grp}" if len(phases) > 1 or args.refine else args.study
        print(f"--- phase {grp}: {num} trials, {len(space)} params, study {sname} ---")
        study = open_study(args, sname)
        study.optimize(make_objective(space, fixed, eval_cfgs, args.seed),
                       n_trials=num, timeout=args.timeout,
                       n_jobs=args.n_jobs, show_progress_bar=False)
        fixed.update(study.best_params)
        save_best(args, sname, grp, study.best_value, dict(fixed), eval_names)

    if args.refine > 0 and fixed:
        last_grp = phases[-1][0]
        space = shrink_space(
            {k: v for k, v in SPACES[last_grp].items()}, fixed)
        sname = f"{args.study}_{last_grp}_refine"
        print(f"--- refine {last_grp}: {args.refine} trials, study {sname} ---")
        study = open_study(args, sname)
        base_fixed = {k: v for k, v in fixed.items() if k not in space}
        study.optimize(make_objective(space, base_fixed, eval_cfgs, args.seed),
                       n_trials=args.refine, timeout=args.timeout,
                       n_jobs=args.n_jobs, show_progress_bar=False)
        fixed.update(study.best_params)
        save_best(args, sname, last_grp + "+refine", study.best_value,
                  dict(fixed), eval_names)

    print(f"\nresume with: tune.py --study {args.study} --storage {args.storage}")
    return 0


def cmd_confirm(args):
    """Re-evaluate the study winner on fresh seeds; report mean/std."""
    import math
    study = open_study(args, args.study)
    if not study.best_trial:
        print(f"study {args.study} has no completed trials")
        return 2
    params = dict(study.best_trial.params)
    print(f"confirming {len(params)} params on {args.confirm} fresh seeds")
    eval_cfgs = build_eval_cfgs(args)
    if eval_cfgs is None:
        return 2
    scores = []
    for k in range(args.confirm):
        seed = args.seed + 1000 * (k + 1)
        sc = eval_params(params, eval_cfgs, seed, tag=f"confirm{k + 1}", verbose=True)
        scores.append(sc)
        print(f"[confirm {k + 1}] seed={seed} score={sc:.2f}", flush=True)
    mean = sum(scores) / len(scores)
    std = math.sqrt(sum((s - mean) ** 2 for s in scores) / len(scores))
    print(f"CONFIRM mean={mean:.2f} std={std:.2f} min={min(scores):.2f} "
          f"max={max(scores):.2f} (study best={study.best_value:.2f})")
    if std > 0.3 * mean:
        print("WARNING: high seed variance -- winner may be seed-overfit; "
              "widen --fuzz-eval or add scenarios and re-tune")
    return 0


if __name__ == "__main__":
    sys.exit(main())
