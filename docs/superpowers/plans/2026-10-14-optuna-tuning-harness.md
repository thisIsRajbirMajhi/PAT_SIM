# Optuna Tuning Harness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build `tune.py` that finds a balanced winner config with Optuna and auto-validates on the full 80-case headless suite until green.

**Architecture:** Reuse `headless.py` runner (`build_case_config`, `build_edge_config`, `run_tracking_case`, `verdict`, `BENCHMARKS`) and `pat_common` config (`DEFAULT_CONFIG`, `deep_merge`, `load_config`). Tune on a 19-case fast subset; judge on full 80 via new `--config` flag; loop rounds until 0 FAIL + 0 ERROR.

**Tech Stack:** Python, Optuna>=4.0, SQLite storage, ProcessPoolExecutor, existing `pat_pipeline`/`fsoc_tracker` pipeline.

**Spec:** `docs/superpowers/specs/2026-10-14-optuna-tuning-harness-design.md`

## Global Constraints

- Canonical contract: `docs/Tuning.md` (consolidates `docs/Hardware_Constraints.md` + `docs/Tuning Parameters.txt`). On any conflict between this plan and `Tuning.md`, `Tuning.md` wins; ledger the ruling.
- Fixed hardware excluded from tuning: camera `max_pan/tilt_speed`, `fov_deg [4,3]`, `resolution [640,480]` — validation runs at these exact values.
- Spec hard walls (`docs/Hardware_Constraints.md`): camera update rate ≥ 30 Hz, update interval ≥ 20 Hz, target type beacon spot, actuator envelope 5–10 °/s, disturbance ceilings (noise 20 / jitter ±20 / platform ±20), world ≥ 2000×2000. Tuned configs must respect floors: `fps` stays at default 30 (never proposed below 30), `update_interval_hz` ≥ 20.
- Ruling 2026-10-14: user explicitly allowed tuning initial camera position/pan/tilt, overriding the spec's "centre mandatory" wall. Included; validation runs winners as-tuned.
- Test conditions never tuned: world/target/noise/atmosphere/platform/environment/experiment keys — tuning these cheats the suite.
- Success = full-suite FINAL VERDICT PASS iff 0 FAIL + 0 ERROR (`headless.py:1403-1405`); STRICT-PASS and INTERMITTENT-PASS (intermittent-allowed only) both count.
- Outputs stay in single top-level `runs/` alongside `headless_*.json/md/html`; study DB at `runs/tune.db` (or `outputs/tune.db` with justification, `optuna-dashboard` compatible).
- No benchmark or verdict threshold changes.
- Per-case timeout passthrough defaults to headless `--timeout 300s`; MedianPruner warmup ~10 trials; default workers = CPU-1, processes not threads.

## Review Focus

- Winner JSON smuggling test-condition keys (target speed, fog strength, star density) expecting a boost — must be rejected/clamped to system-only keys.
- Winner overriding fixed hardware (fov, resolution, max speeds) passing sim but undeployable — must be rejected.
- Intermittent-pass on strict-only case counted as pass by objective — must score as fail.
- SQLite study lock contention under `--workers 8` causing trial crashes — must resume cleanly.
- Hopeless-trial pruning killing eventual winners on first subset case — pruner must warm up before pruning.

---

### Task 1: `headless.py --config` winner injection

**Files:**
- Modify: `headless.py:1247-1277` (argparse), `headless.py:566-592` (`build_case_config`, `build_edge_config`)
- Test: `tests/test_headless_config.py`

**Interfaces:**
- Consumes: `pat_common.config.loader.deep_merge(a: dict, b: dict) -> dict`
- Produces: `headless.WINNER_OVERRIDES: dict`, `headless.set_winner_overrides(path: str | None) -> dict` — loads JSON, keeps only `detector`/`tracker`/`controller`/camera allowlist keys, drops everything else including fixed hardware. Camera allowlist is exactly `{initial_position, initial_pan, initial_tilt, update_interval_hz}` (`update_interval_hz` floor ≥ 20 Hz, values below 20 rejected); `fps`, `max_pan/tilt_speed`, `fov_deg`, `resolution` are always dropped.
- Ordering (matters — `enforce_far_start` at `headless.py:467` resets camera to centre and pops pan/tilt): non-camera-start overrides merge after base, before stars/far-start; camera start keys (`initial_position`, `initial_pan`, `initial_tilt`) merge AFTER `enforce_far_start`, so tuned starts survive. Target `initial_mode`/`initial_pos` always stay far-corner (test condition, never overridden).

- [ ] **Step 1: Write the failing test**

```python
def test_config_flag_rejects_nonsystem_keys(tmp_path):
    from headless import set_winner_overrides
    p = tmp_path / "w.json"
    p.write_text('{"detector": {"threshold_k": 3.5}, "target": {"speed_px_per_frame": 99}, "camera": {"fov_deg": [12, 12]}}')
    got = set_winner_overrides(str(p))
    assert got["detector"]["threshold_k"] == 3.5
    assert "target" not in got
    assert "fov_deg" not in got.get("camera", {})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_headless_config.py::test_config_flag_rejects_nonsystem_keys -v`
Expected: FAIL with "set_winner_overrides not defined"

- [ ] **Step 2b: Write the ordering test (camera start survives far-start)**

```python
def test_camera_start_applies_after_far_start(tmp_path):
    import headless
    from headless import set_winner_overrides, build_case_config, X_DEFS
    p = tmp_path / "w.json"
    p.write_text('{"camera": {"initial_position": "user-defined", "initial_pan": 2.0, "initial_tilt": -1.5}}')
    set_winner_overrides(str(p))
    try:
        xd = next(d for d in X_DEFS if d["key"] == "X1")
        cfg = build_case_config(xd, 42)
        assert cfg["camera"].get("initial_pan") == 2.0
        assert cfg["camera"].get("initial_tilt") == -1.5
        assert cfg["target"]["initial_mode"] == "user-defined"  # far corner intact
    finally:
        set_winner_overrides(None)
```

- [ ] **Step 2c: Run ordering test to verify it fails**

Run: `pytest tests/test_headless_config.py::test_camera_start_applies_after_far_start -v`
Expected: FAIL (no post-far-start application yet)

- [ ] **Step 3: Implement `set_winner_overrides(path: str | None) -> dict` in `headless.py` plus `--config` argparse flag; apply non-camera-start `WINNER_OVERRIDES` via `deep_merge` in `build_case_config`/`build_edge_config` after base merge, before stars/far-start; apply camera start keys (`initial_position`, `initial_pan`, `initial_tilt`) AFTER `enforce_far_start`**

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_headless_config.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add headless.py tests/test_headless_config.py
git commit -m "feat: add --config winner injection to headless"
```

### Task 2: Search space + composite objective (pure functions)

**Files:**
- Create: `tune.py`
- Test: `tests/test_tune_objective.py`

**Interfaces:**
- Consumes: `headless.BENCHMARKS: dict`, `headless.verdict(summary: dict, intermittent_allowed: bool, bkey: str) -> tuple[str, str]`
- Produces: `tune.SEARCH_SPACE: dict`, `tune.suggest_overrides(trial: optuna.Trial) -> dict`, `tune.composite_loss(results: list[dict]) -> float` (minimize; -fail heavy penalty, lock shortfall, rmse excess, first-lock delay; intermittent-allowed uses acq/valid gates)

Search space (user allowlist 2026-10-14 + expansions; defaults from `sections/*.py`, limits from `template.py:42-76`, floors from `docs/Hardware_Constraints.md`; implementer verifies every range against `validate_config`, narrowing where schema demands).
User-locked core: camera `initial_position` {centre, user-defined}, `initial_pan`/`initial_tilt` ±8 deg (applied post-far-start per Task 1 ordering); controller `kp_pan`/`kp_tilt` 0.1–5.0, `ki` 0–1.0, `kd` 0–2.0, `deadzone_px` 0–6.0; tracker `process_noise` 0.1–5.0, `meas_noise` 0.5–10.0; search `search_radius_max` 2.0–8.0, `spiral_phase_s` 1–8, `stare_rate_scale` 0.1–0.8, `intercept_gain` 0.5–5.0, `give_up_frames` 120–1800.
Expansions (same families, spec-safe): detector `threshold_k` 2.0–5.0, `min_area` 4–16, `max_area` 400–1500; tracker `gate_sigma` 3.0–8.0, `lost_timeout_frames` 5–30, `reacq_timeout_frames` 10–60; controller `integral_limit` 2–20, `feedforward_gain` 0–2.0; search `search_angle_step` 0.05–1.0, `search_radius_step` 0.01–0.5, `search_rate_scale` 0.3–1.5, `intercept_lead_s` 0–0.8, `unc_scale` 0–2.0, `unc_max_boost` 1–4, `fast_vel_deg_s` 0.2–5.0, `raster_pan_scale`/`raster_tilt_scale` 0.3–1.0; camera `update_interval_hz` 20–60 (floor ≥ 20; `fps` not in space, stays 30).
Staging advice (binding): tune in stages — Stage 1 core (detector + tracker + PID + deadzone), Stage 2 search policy (+ timeouts/give_up), Stage 3 joint polish on the best region — since ~33 knobs at once needs far more trials than a flat search. Canonical list: docs/Tuning Parameters.txt.

- [ ] **Step 1: Write the failing test**

```python
def test_composite_loss_prefers_strict_over_fail():
    from tune import composite_loss
    strict = [{"verdict": "STRICT-PASS", "lock_pct": 80, "rmse": 3.0, "first_lock": 100, "losses": 0, "bkey": "X1", "intermittent": False}]
    failed = [{"verdict": "FAIL", "lock_pct": 0, "rmse": 99.0, "first_lock": None, "losses": 9, "bkey": "X1", "intermittent": False}]
    assert composite_loss(strict) < composite_loss(failed)

def test_composite_loss_rejects_intermittent_on_strict_case():
    from tune import composite_loss
    strict_case = [{"verdict": "INTERMITTENT-PASS", "lock_pct": 5, "rmse": 20.0, "first_lock": 900, "losses": 9, "acq": 5, "valid_pct": 50.0, "bkey": "X1", "intermittent": False}]
    strict_win = [{"verdict": "STRICT-PASS", "lock_pct": 60, "rmse": 4.0, "first_lock": 400, "losses": 1, "bkey": "X1", "intermittent": False}]
    assert composite_loss(strict_win) < composite_loss(strict_case)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_tune_objective.py::test_composite_loss_prefers_strict_over_fail -v`
Expected: FAIL with "tune not defined"

- [ ] **Step 3: Implement `SEARCH_SPACE`, `suggest_overrides(trial)`, `composite_loss(results)` in `tune.py` (no Optuna study yet)**

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_tune_objective.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tune.py tests/test_tune_objective.py
git commit -m "feat: add tune search space and objective"
```

### Task 3: Optuna study loop on fast subset

**Files:**
- Modify: `tune.py`
- Test: `tests/test_tune_study.py`

**Interfaces:**
- Consumes: `tune.suggest_overrides`, `tune.composite_loss`, `headless.build_case_config`, `headless.build_edge_config`, `headless.run_tracking_case`, `headless.X_DEFS`, `headless.E_DEFS`
- Produces: `tune.FAST_SUBSET: list[tuple[str, int]]`, `tune.evaluate_subset(overrides: dict, subset: list, timeout_s: float) -> list[dict]`, `tune.run_study(trials: int, workers: int, study_name: str, storage: str, timeout_s: float) -> optuna.Study`

`FAST_SUBSET` default: X1-X14 @ seed 42 (14) + E4,E5,E13,E15,E20 @ 42 (5) = 19 cases. TPESampler + MedianPruner(n_startup_trials=10). Storage default `sqlite:///runs/tune.db`.

- [ ] **Step 1: Write the failing test**

```python
def test_evaluate_subset_returns_scored_results():
    from tune import evaluate_subset
    out = evaluate_subset({"detector": {"threshold_k": 3.0}}, [("X1", 42)], timeout_s=60.0)
    assert len(out) == 1 and out[0]["verdict"] in ("STRICT-PASS", "INTERMITTENT-PASS", "FAIL", "ERROR")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_tune_study.py::test_evaluate_subset_returns_scored_results -v`
Expected: FAIL with "evaluate_subset not defined"

- [ ] **Step 3: Implement `FAST_SUBSET`, `evaluate_subset(overrides, subset, timeout_s)` (applies overrides via `deep_merge` onto each built case cfg, system keys only), and `run_study(...)` with TPESampler/MedianPruner/RDB storage resume**

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_tune_study.py -v`
Expected: PASS (subset of 1 case, under 300s)

- [ ] **Step 5: Commit**

```bash
git add tune.py tests/test_tune_study.py
git commit -m "feat: add optuna study loop on fast subset"
```

### Task 4: Full validation + auto-loop until green + CLI/artifacts

**Files:**
- Modify: `tune.py`, `requirements-dev.txt:13-14`
- Test: `tests/test_tune_validate.py`

**Interfaces:**
- Consumes: `tune.run_study`, `headless.set_winner_overrides`, full-suite `build_suite`/`run_tracking_case`/`run_robustness` path
- Produces: `tune.validate_full(winner_path: str, workers: int, timeout_s: float) -> dict` returning `{fails, errors, verdict, report_paths}`, CLI `tune.py --trials N --workers M --study NAME --storage URL --validate-topk K --max-rounds R --timeout S`, artifacts `runs/tune_<stamp>_best.json` (overrides + resolved cfg + score breakdown) + `runs/tune_<stamp>_validation.json`

Loop: study round -> top-K winners -> `validate_full` each (subprocess `headless.py --extreme --config winner.json --workers M` or in-process equivalent) -> stop when 0 FAIL+0 ERROR else next round up to `--max-rounds 0` = unbounded.

- [ ] **Step 1: Write the failing test**

```python
def test_validate_full_counts_fails(tmp_path):
    from tune import validate_full
    rep = validate_full("tests/fixtures/bad_winner.json", workers=1, timeout_s=30.0, frames_override=50)
    assert "fails" in rep and "verdict" in rep
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_tune_validate.py::test_validate_full_counts_fails -v`
Expected: FAIL with "validate_full not defined"

- [ ] **Step 3: Implement `validate_full(...)`, auto-loop in `main()`, artifact writers, CLI flags; pin `optuna` in `requirements-dev.txt` (already `optuna>=4.0`) and document `optuna-dashboard sqlite:///runs/tune.db`**

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_tune_validate.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tune.py requirements-dev.txt tests/test_tune_validate.py
git commit -m "feat: auto-validate winners until green"
```
