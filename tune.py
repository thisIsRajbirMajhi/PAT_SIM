"""Optuna tuning harness: search space + composite objective (pure functions).

No Optuna study loop here (Task 3), no headless imports at module import
time — headless is imported lazily inside functions so unit tests stay fast.
"""

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
    loss += max(0.0, bench_lock - float(lock)) * _W_LOCK

    rmse = result.get("rmse", 0.0) or 0.0
    loss += max(0.0, float(rmse) - bench_rmse) * _W_RMSE

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
