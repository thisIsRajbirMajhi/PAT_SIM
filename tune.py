"""Optuna tuning harness: search space + composite objective + study loop.

No Optuna/headless imports at module import time — both are imported
lazily inside functions so unit tests stay fast.
"""

import argparse
import copy
import json
import math
import os
import time

# SEARCH_SPACE: key -> spec. Each spec has section (config subtree), kind,
# range info, and stage tag (1/2/3) per docs/Tuning.md section 4:
#   Stage 1 (core):    detector + tracker noises + PID + deadzone
#   Stage 2 (policy):  search/intercept + loss/reacq timeouts (+ remaining
#                      tunable knobs: gate_sigma, integral/FF gains, camera
#                      start) so per-stage selection covers everything early
#   Stage 3 (polish):  joint re-tune = all knobs (stage=None/3 selects all)
# Ranges match Tuning.md section 3 and fit inside validate_config limits.
SEARCH_SPACE = {
    # Stage 1 — core (Group B detector + C noises + D PID/deadzone)
    "threshold_k": {"section": "detector", "kind": "float", "low": 2.0, "high": 5.0, "stage": 1},
    "min_area": {"section": "detector", "kind": "int", "low": 4, "high": 16, "stage": 1},
    "max_area": {"section": "detector", "kind": "int", "low": 400, "high": 1500, "stage": 1},
    "process_noise": {"section": "tracker", "kind": "float", "low": 0.1, "high": 5.0, "stage": 1},
    "meas_noise": {"section": "tracker", "kind": "float", "low": 0.5, "high": 10.0, "stage": 1},
    "kp_pan": {"section": "controller", "kind": "float", "low": 0.1, "high": 5.0, "stage": 1},
    "kp_tilt": {"section": "controller", "kind": "float", "low": 0.1, "high": 5.0, "stage": 1},
    "ki": {"section": "controller", "kind": "float", "low": 0.0, "high": 1.0, "stage": 1},
    "kd": {"section": "controller", "kind": "float", "low": 0.0, "high": 2.0, "stage": 1},
    "deadzone_px": {"section": "controller", "kind": "float", "low": 0.0, "high": 6.0, "stage": 1},
    # Stage 2 — policy (Group E + tracker timeouts/gate + remaining gains + camera start)
    "gate_sigma": {"section": "tracker", "kind": "float", "low": 3.0, "high": 8.0, "stage": 2},
    "lost_timeout_frames": {"section": "tracker", "kind": "int", "low": 5, "high": 30, "stage": 2},
    "reacq_timeout_frames": {"section": "tracker", "kind": "int", "low": 10, "high": 60, "stage": 2},
    "integral_limit": {"section": "controller", "kind": "float", "low": 2.0, "high": 20.0, "stage": 2},
    "feedforward_gain": {"section": "controller", "kind": "float", "low": 0.0, "high": 2.0, "stage": 2},
    "search_angle_step": {"section": "controller", "kind": "float", "low": 0.05, "high": 1.0, "stage": 2},
    "search_radius_step": {"section": "controller", "kind": "float", "low": 0.01, "high": 0.5, "stage": 2},
    "search_radius_max": {"section": "controller", "kind": "float", "low": 2.0, "high": 8.0, "stage": 2},
    "search_rate_scale": {"section": "controller", "kind": "float", "low": 0.3, "high": 1.5, "stage": 2},
    "spiral_phase_s": {"section": "controller", "kind": "float", "low": 1.0, "high": 8.0, "stage": 2},
    "raster_pan_scale": {"section": "controller", "kind": "float", "low": 0.3, "high": 1.0, "stage": 2},
    "raster_tilt_scale": {"section": "controller", "kind": "float", "low": 0.3, "high": 1.0, "stage": 2},
    "stare_rate_scale": {"section": "controller", "kind": "float", "low": 0.1, "high": 0.8, "stage": 2},
    "intercept_gain": {"section": "controller", "kind": "float", "low": 0.5, "high": 5.0, "stage": 2},
    "intercept_lead_s": {"section": "controller", "kind": "float", "low": 0.0, "high": 0.8, "stage": 2},
    "unc_scale": {"section": "controller", "kind": "float", "low": 0.0, "high": 2.0, "stage": 2},
    "unc_max_boost": {"section": "controller", "kind": "float", "low": 1.0, "high": 4.0, "stage": 2},
    "fast_vel_deg_s": {"section": "controller", "kind": "float", "low": 0.2, "high": 5.0, "stage": 2},
    "give_up_frames": {"section": "controller", "kind": "int", "low": 120, "high": 1800, "stage": 2},
    "initial_position": {"section": "camera", "kind": "categorical",
                         "choices": ["centre", "user-defined"], "stage": 2},
    "initial_pan": {"section": "camera", "kind": "float", "low": -8.0, "high": 8.0, "stage": 2},
    "initial_tilt": {"section": "camera", "kind": "float", "low": -8.0, "high": 8.0, "stage": 2},
    "update_interval_hz": {"section": "camera", "kind": "float", "low": 20.0, "high": 60.0, "stage": 2},
}


def suggest_overrides(trial, stage=None):
    """Suggest one candidate's overrides from SEARCH_SPACE.

    stage=1/2 suggests only that stage's knobs; stage=None/3 suggests all
    (Stage 3 polish = joint re-tune). Returns nested {section: {key: value}}.
    """
    overrides = {}
    for key, spec in SEARCH_SPACE.items():
        if stage in (1, 2) and spec["stage"] != stage:
            continue
        kind = spec["kind"]
        if kind == "float":
            value = trial.suggest_float(key, spec["low"], spec["high"])
        elif kind == "int":
            value = trial.suggest_int(key, spec["low"], spec["high"])
        elif kind == "categorical":
            value = trial.suggest_categorical(key, spec["choices"])
        else:  # pragma: no cover - defensive
            raise ValueError(f"unknown kind {kind!r} for {key}")
        overrides.setdefault(spec["section"], {})[key] = value
    return overrides


# Composite-loss weights: fail-count dominates; quality terms break ties.
_FAIL_PENALTY = 1000.0
_ERROR_PENALTY = 2000.0
_W_LOCK = 1.0
_W_RMSE = 2.0
_W_FIRST = 0.05
_W_LOSS = 5.0
_FIRST_MISSING_PENALTY = 500.0


def _case_loss(result, benchmarks):
    b = benchmarks.get(result.get("bkey"), {})
    bench_lock = float(b.get("lock", 50.0))
    bench_rmse = float(b.get("rmse", 10.0))
    bench_first = b.get("first", 500)
    bench_loss = int(b.get("losses", 3))

    verdict = result.get("verdict")
    intermittent_allowed = bool(result.get("intermittent", False))

    passed = verdict == "STRICT-PASS"
    if verdict == "INTERMITTENT-PASS" and intermittent_allowed:
        # Intermittent-allowed cases pass via acq/valid gates.
        acq_need = int(b.get("acq", 2))
        valid_need = float(b.get("valid", 15.0))
        acq = result.get("acq", 0) or 0
        valid = result.get("valid_pct", 0.0) or 0.0
        passed = int(acq) >= acq_need and float(valid) >= valid_need
    # INTERMITTENT-PASS on a strict-only case scores as fail (falls through
    # with passed=False); FAIL/ERROR always fail.

    loss = 0.0
    if not passed:
        loss += _ERROR_PENALTY if verdict == "ERROR" else _FAIL_PENALTY

    lock = result.get("lock_pct", 0.0) or 0.0
    try:
        lock_f = float(lock)
    except (TypeError, ValueError):
        lock_f = 0.0
    if not math.isfinite(lock_f):
        lock_f = 0.0  # worst-case; fail/ERROR penalties still dominate
    loss += max(0.0, bench_lock - lock_f) * _W_LOCK

    rmse = result.get("rmse", 0.0) or 0.0
    try:
        rmse_f = float(rmse)
    except (TypeError, ValueError):
        rmse_f = bench_rmse
    if not math.isfinite(rmse_f):
        rmse_f = bench_rmse + _FAIL_PENALTY / _W_RMSE  # worst-case, below ERROR
    loss += max(0.0, rmse_f - bench_rmse) * _W_RMSE

    first = result.get("first_lock")
    if first is None:
        loss += _FIRST_MISSING_PENALTY
    else:
        try:
            bench_first_f = float(bench_first)
        except (TypeError, ValueError):
            bench_first_f = 500.0
        loss += max(0.0, float(first) - bench_first_f) * _W_FIRST

    losses = result.get("losses", 0) or 0
    loss += max(0, int(losses) - bench_loss) * _W_LOSS
    return loss


def composite_loss(results):
    """Minimize: fail-count heavy penalty + lock shortfall + rmse excess
    + first-lock delay. INTERMITTENT-PASS counts only on intermittent-allowed
    cases (via acq/valid gates); elsewhere it scores as fail.
    """
    from headless import BENCHMARKS

    return float(sum(_case_loss(r, BENCHMARKS) for r in results))


# Fast tuning subset: X1..X14 @ seed 42 (14) + E4,E5,E13,E15,E20 @ 42 (5).
FAST_SUBSET = (
    [(f"X{i}", 42) for i in range(1, 15)]
    + [(k, 42) for k in ("E4", "E5", "E13", "E15", "E20")]
)

def _split_local_overrides(overrides):
    """Split trial overrides into (pre, post) batches.

    `post` holds the camera start keys merged after the base case config
    (so they survive `enforce_far_start`); `pre` holds everything else.
    Start keys come from `headless._CAMERA_START_KEYS` (single source).
    """
    import headless as _h

    start_keys = _h._CAMERA_START_KEYS
    overrides = overrides or {}
    pre = {}
    post = {}
    for section, kv in overrides.items():
        if not isinstance(kv, dict):
            pre[section] = kv
            continue
        if section == "camera":
            pre_cam = {k: v for k, v in kv.items() if k not in start_keys}
            post_cam = {k: v for k, v in kv.items() if k in start_keys}
            if pre_cam:
                pre[section] = pre_cam
            if post_cam:
                post[section] = post_cam
        else:
            pre[section] = kv
    return pre, post


def evaluate_subset(overrides, subset=None, timeout_s=300.0):
    """Run one candidate's overrides over a case subset, sequentially.

    Builds each base config via `build_case_config`/`build_edge_config`
    with the `headless.WINNER_OVERRIDES` global cleared (worker-safety —
    never rely on the global inside trials), then `deep_merge`s the trial's
    non-camera-start overrides, then the camera start keys last so tuned
    starts survive far-start enforcement. Target stays far-corner.

    Each returned dict carries `verdict`, `lock_pct`, `rmse`,
    `first_lock`, `losses`, `bkey`, `intermittent`, `acq`, `valid_pct`
    for `composite_loss`. Per-case timeout passes straight into
    `run_tracking_case(..., timeout_s=...)`; timeout ERRORs score via
    `composite_loss` with no special handling.
    """
    import copy

    import headless
    from pat_common.config.loader import deep_merge

    _CAM_ALLOW = {"initial_position", "initial_pan", "initial_tilt",
                  "update_interval_hz"}
    _bad = []
    for _section, _kv in (overrides or {}).items():
        if _section in ("detector", "tracker", "controller"):
            continue
        elif _section == "camera" and isinstance(_kv, dict):
            _bad.extend(f"camera.{k}" for k in _kv if k not in _CAM_ALLOW)
        else:
            _bad.append(str(_section))
    if _bad:
        raise ValueError(f"overrides contain non-system keys: {sorted(_bad)}")

    subset = list(subset) if subset is not None else list(FAST_SUBSET)
    pre, post = _split_local_overrides(overrides)
    x_by_key = {d["key"]: d for d in headless.X_DEFS}
    e_by_key = {d["key"]: d for d in headless.E_DEFS}

    results = []
    for key, seed in subset:
        saved = copy.deepcopy(headless.WINNER_OVERRIDES)
        try:
            headless.WINNER_OVERRIDES = {}
            if key in x_by_key:
                case_def = x_by_key[key]
                cfg = headless.build_case_config(case_def, seed)
            elif key in e_by_key:
                case_def = e_by_key[key]
                cfg = headless.build_edge_config(case_def, seed)
            else:  # pragma: no cover - defensive
                raise ValueError(f"unknown subset key {key!r}")
        finally:
            headless.WINNER_OVERRIDES = saved
        if pre:
            cfg = deep_merge(cfg, copy.deepcopy(pre))
        if post:
            cfg = deep_merge(cfg, copy.deepcopy(post))
        r = headless.run_tracking_case(
            f"{case_def['key']}-s{seed}", case_def["name"], case_def["desc"],
            cfg, case_def["frames"], seed, case_def["intermittent"],
            bkey=case_def["key"], timeout_s=timeout_s,
        )
        r["intermittent"] = bool(case_def["intermittent"])
        results.append(r)
    return results


def _coerce_workers(workers):
    """Coerce to int, rejecting non-integral values (e.g. 1.9, "1.9").

    Integer-valued strings ("4") and floats (4.0) still work.
    """
    try:
        as_float = float(workers)
    except (TypeError, ValueError):
        raise ValueError(f"workers must be an integer >= 1, got {workers!r}")
    if not math.isfinite(as_float) or as_float != int(as_float):
        raise ValueError(f"workers must be an integer >= 1, got {workers!r}")
    workers = int(as_float)
    if workers < 1:
        raise ValueError(f"workers must be >= 1, got {workers}")
    return workers


def run_study(trials=20, workers=1, study_name="tune",
              storage="sqlite:///runs/tune.db", timeout_s=300.0, stage=None):
    """Run an Optuna study over FAST_SUBSET and return the study.

    TPESampler + MedianPruner(n_startup_trials=10); RDB storage so rounds
    resume (`load_if_exists=True`; `runs/` created when the default
    sqlite path is used). Cases run sequentially in-process per trial;
    `workers` is accepted and validated (>=1) for forward-compat with
    Task 4 validation batching.
    """
    import os

    import optuna

    workers = _coerce_workers(workers)
    subset = list(FAST_SUBSET)

    def objective(trial):
        overrides = suggest_overrides(trial, stage)
        results = evaluate_subset(overrides, subset, timeout_s)
        return composite_loss(results)

    sampler = optuna.samplers.TPESampler()
    pruner = optuna.pruners.MedianPruner(n_startup_trials=10)
    if storage is None:
        return _optimize(optuna, None, study_name, sampler, pruner,
                         objective, trials)
    if isinstance(storage, str) and storage.startswith("sqlite:///"):
        db_path = storage[len("sqlite:///"):]
        if db_path and db_path != ":memory:":
            parent = os.path.dirname(os.path.abspath(db_path))
            os.makedirs(parent, exist_ok=True)
    return _optimize(optuna, storage, study_name, sampler, pruner,
                     objective, trials)


def _optimize(optuna, storage, study_name, sampler, pruner, objective, trials):
    study = optuna.create_study(
        direction="minimize", sampler=sampler, pruner=pruner,
        study_name=study_name, storage=storage, load_if_exists=True,
    )
    study.optimize(objective, n_trials=trials)
    return study


# Stage schedule across auto-loop rounds (Tuning.md section 4):
# round 0 core -> round 1 policy -> round 2+ joint polish (stage=None).
STAGE_SCHEDULE = (1, 2, None)


def _stamp():
    return time.strftime("%Y%m%d_%H%M%S")


def _write_json(path, payload):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(payload, f, indent=2)
    os.replace(tmp, path)
    return path


def validate_full(winner_path: str, workers: int = 1, timeout_s: float = 300.0,
                  frames_override: int | None = None, stamp: str | None = None) -> dict:
    """Validate a winner JSON against the full 80-case suite.

    Exercises the real Task 1 path: `set_winner_overrides(winner_path)`
    then the full suite through `build_suite` + `headless._worker`
    (X/E via `run_tracking_case`, R via `run_robustness`). Sequential
    in-process when `workers == 1`, otherwise a process pool (processes,
    never threads). Per-case timeout passes into X/E cases.

    `frames_override` is a TEST-ONLY accelerator (small frame counts);
    default None = real frames. Never wired into the CLI path. `stamp`
    lets the caller share one filename stamp between the validation
    report and the best artifact (CLI passes its per-candidate stamp).

    Returns at minimum `{fails, errors, verdict ("PASS"/"FAIL"),
    report_paths}` and writes `runs/tune_<stamp>_validation.json`.
    PASS iff 0 FAIL + 0 ERROR; any other non-passing verdict (including
    non-PASS R results) counts as a fail.
    """
    import concurrent.futures

    import headless

    workers = _coerce_workers(workers)

    saved = copy.deepcopy(headless.WINNER_OVERRIDES)
    try:
        headless.set_winner_overrides(winner_path)
        specs = headless.build_suite(frames_override=frames_override)
        for s in specs:
            s["timeout_s"] = timeout_s if s["kind"] in ("X", "E") else None
            if headless.WINNER_OVERRIDES:
                s["winner"] = copy.deepcopy(headless.WINNER_OVERRIDES)
        if workers > 1:
            with concurrent.futures.ProcessPoolExecutor(
                    max_workers=workers) as ex:
                results = list(ex.map(headless._worker, specs))
        else:
            results = [headless._worker(s) for s in specs]
    finally:
        headless.WINNER_OVERRIDES = saved

    fails = 0
    errors = 0
    for r in results:
        v = r.get("verdict")
        if v == "ERROR":
            errors += 1
        elif v == "FAIL":
            fails += 1
        elif v not in ("STRICT-PASS", "INTERMITTENT-PASS"):
            fails += 1
    verdict = "PASS" if (fails == 0 and errors == 0) else "FAIL"

    stamp = stamp or _stamp()
    report = os.path.join("runs", f"tune_{stamp}_validation.json")
    payload = {
        "winner": winner_path,
        "fails": fails,
        "errors": errors,
        "verdict": verdict,
        "stamp": stamp,
        "results": results,
    }
    _write_json(report, payload)
    return {"fails": fails, "errors": errors, "verdict": verdict,
            "report_paths": [report]}


def _nest_params(params):
    """Nest flat trial params into {section: {key: value}} overrides."""
    nested = {}
    for key, value in params.items():
        section = SEARCH_SPACE.get(key, {}).get("section", "controller")
        nested.setdefault(section, {})[key] = value
    return nested


def write_best_artifact(overrides, value, trial_number, round_idx, stage,
                        stamp=None):
    """Write `runs/tune_<stamp>_best.json` (overrides + resolved config
    + score breakdown). Returns the artifact path."""
    stamp = stamp or _stamp()
    try:
        from pat_common.config.loader import deep_merge
        from pat_common.config.defaults import DEFAULT_CONFIG
        resolved = deep_merge(copy.deepcopy(DEFAULT_CONFIG),
                              copy.deepcopy(overrides))
    except Exception:
        resolved = copy.deepcopy(overrides)
    path = os.path.join("runs", f"tune_{stamp}_best.json")
    _write_json(path, {
        "overrides": overrides,
        "resolved_config": resolved,
        "score": {"value": value, "trial": trial_number,
                  "round": round_idx, "stage": stage},
        "stamp": stamp,
    })
    return path


def main(argv=None):
    ap = argparse.ArgumentParser(description="Optuna tuning harness")
    ap.add_argument("--trials", type=int, default=20)
    ap.add_argument("--workers", type=int, default=1,
                    help="process count for full validation of each candidate "
                         "(the study loop itself runs sequentially)")
    ap.add_argument("--study", default="tune")
    ap.add_argument("--storage", default="sqlite:///runs/tune.db")
    ap.add_argument("--subset", default="fast")
    ap.add_argument("--validate-topk", type=int, default=1)
    ap.add_argument("--max-rounds", type=int, default=3,
                    help="study->validate rounds; 0 = unbounded")
    ap.add_argument("--timeout", type=float, default=300.0,
                    help="per-case timeout in seconds")
    args = ap.parse_args(argv)

    if args.subset != "fast":
        ap.error("--subset only supports 'fast'")
    if args.validate_topk < 1:
        ap.error("--validate-topk must be >= 1")

    round_idx = 0
    while True:
        if args.max_rounds and round_idx >= args.max_rounds:
            print(f"STOP: {args.max_rounds} round(s) exhausted without green.")
            return 1
        stage = (STAGE_SCHEDULE[round_idx]
                 if round_idx < len(STAGE_SCHEDULE) else None)
        print(f"=== round {round_idx} stage={stage} "
              f"trials={args.trials} ===")
        study = run_study(trials=args.trials, workers=args.workers,
                          study_name=args.study, storage=args.storage,
                          timeout_s=args.timeout, stage=stage)
        scored = [t for t in study.trials if t.value is not None]
        scored.sort(key=lambda t: t.value)
        top = scored[:args.validate_topk]
        if not top:
            print("STOP: study produced no completed trials.")
            return 1
        for rank, trial in enumerate(top):
            overrides = _nest_params(trial.params)
            stamp = _stamp()
            winner_path = os.path.join(
                "runs", f"tune_{stamp}_round{round_idx}_top{rank}.json")
            _write_json(winner_path, overrides)
            rep = validate_full(winner_path, workers=args.workers,
                                timeout_s=args.timeout, stamp=stamp)
            best_path = write_best_artifact(
                overrides, trial.value, trial.number,
                round_idx, stage, stamp=stamp)
            print(f"round {round_idx} top{rank}: trial={trial.number} "
                  f"value={trial.value:.1f} fails={rep['fails']} "
                  f"errors={rep['errors']} verdict={rep['verdict']} "
                  f"-> {best_path} {rep['report_paths']}")
            if rep["fails"] == 0 and rep["errors"] == 0:
                print("FINAL VERDICT: PASS - winner validated on full suite")
                return 0
        round_idx += 1


if __name__ == "__main__":
    raise SystemExit(main())
