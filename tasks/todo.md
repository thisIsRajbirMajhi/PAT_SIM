## Task 0: Per-frame threshold trace (diagnostics, no code fix)

**Description:** Log bg/median, noise/std, p98, thresh, peak per frame for 20 frames each of a failing case vs its passing twin (E10 vs E1, E11 vs X1). Confirms the fixed-floor hypothesis before any edit.

**Acceptance criteria:**
- [ ] CSV/trace shows thresh/peak pairs for all 4 cases
- [ ] Root cause stated: floor-hit vs never-detected vs gated-out

**Verification:**
- [ ] Tests pass: `python -m pytest tests/test_headless_config.py -q`
- [ ] Manual check: trace explains 0% valid on E10/E11

**Dependencies:** None — DONE 2026-10-15 (E11 floor-hit / E10 geometric split proven)

**Files likely touched:**
- `tests/headless.py`
- `src/pat_pipeline/detection/detector.py`

**Estimated scope:** Small: 1-2 files

## Task 1: Adaptive threshold floor

**Description:** Replace fixed 120 floor in threshold computation with dim-aware floor so low-light/haze beacons (~140px peak) still detect while bright scenes keep current behavior.

**Acceptance criteria:**
- [ ] E11 lock >0% (was 0%), E16 improves vs 0.2%
- [ ] X1-s42/s7/s99 stay STRICT-PASS, E1/E2 stay STRICT-PASS

**Verification:**
- [ ] Tests pass: `python -m pytest tests/ -q`
- [ ] Manual check: `headless --scenario E11 --seed 42` shows valid>0

**Dependencies:** Task 0 — DONE 2026-10-15 (RED→GREEN via stash; E11 0%→STRICT-PASS 37.0%/1.42; suite 25/25)

**Files likely touched:**
- `src/pat_pipeline/detection/detector.py`
- `tests/test_headless_config.py`

**Estimated scope:** Small: 1-2 files

## Task 2: Colour-path neutrality

**Description:** Make colour mode measurement-neutral: verify BGR2GRAY path and remove/compensate the +6 blue background tint effect on threshold so E10 matches monochrome sensitivity. SUPERSEDED by diagnosis 2026-10-15: E10 peak 246 clears any floor — root cause is corner-centred circular orbit leaving the 2000px world ~48% of the time (mirror-bounds fix below). Colour path verified innocent (BGR2GRAY + negligible +6 tint: bg 22 vs 21).

**Acceptance criteria:**
- [x] E10 lock >=40% (bench), first_lock <=500 — DONE: 81.8% lock / rmse 0.82 STRICT-PASS single-case

**Verification:**
- [ ] Tests pass: `python -m pytest tests/ -q`
- [ ] Manual check: `headless --scenario E10 --seed 42` STRICT-PASS

**Dependencies:** Task 0

**Files likely touched:**
- `src/fsoc_tracker/input/synthetic_source.py`
- `src/pat_pipeline/detection/detector.py`

**Estimated scope:** Small: 1-2 files

## Checkpoint: After Tasks 0-2
- [ ] All tests pass
- [ ] E10/E11 no longer 0%-blind, no regression on X1/E1/E2
- [ ] Review trace + diff with human before proceeding

## Task 3: Search persistence for seed-brittle cases

**Description:** Extend cold-search persistence (give-up frames, radius growth, reacq timeouts) so unlucky seeds (X2-s99, X4-s7, X11-s42/s99) acquire instead of returning first_lock None.

**Acceptance criteria:**
- [ ] X2/X4/X11 seed spread <20pp, no 0% where s42 passes at >40%
- [ ] X5 stays within 5pp of current (no collateral loss)

**Verification:**
- [ ] Tests pass: `python -m pytest tests/ -q`
- [ ] Manual check: `headless --scenario X4 --seed 7` and `--scenario X2 --seed 99` beat bench

**Dependencies:** Tasks 1-2

**Files likely touched:**
- `src/pat_pipeline/state/search_policy.py`
- `src/pat_pipeline/state/state_machine.py`
- `src/pat_pipeline/camera/control/camera_controller.py`

**Estimated scope:** Medium: 3-5 files

## Task 4: dt normalization for rate cases

**Description:** Normalize controller/search gains by dt_ctrl so 20Hz (E8) and 60Hz (E22) behave like 30Hz baseline.

**Acceptance criteria:**
- [ ] E8 lock >=40%, E22 lock >=10%

**Verification:**
- [ ] Tests pass: `python -m pytest tests/ -q`
- [ ] Manual check: `headless --scenario E8 --seed 42` and `E22` beat bench

**Dependencies:** Task 3

**Files likely touched:**
- `src/pat_pipeline/camera/control/pid.py`
- `src/pat_pipeline/orchestration/pat_loop.py`

**Estimated scope:** Small: 1-2 files

## Checkpoint: After Tasks 3-4
- [ ] All tests pass
- [ ] Seed-brittle group green, E8/E22 green
- [ ] R5 latency still <33ms

## Task 5: Intermittent RMSE gate (harness + tuner)

**Description:** Add rmse<bench requirement to intermittent pass in both the reporter and the tuner loss so 150px+ wrong-target tracks fail honestly.

**Acceptance criteria:**
- [ ] Rescored prior JSON marks E4/E12/E17/E23-class RMSE blowups as FAIL
- [ ] Tuner loss and reporter verdict agree on all 80 cases

**Verification:**
- [ ] Tests pass: `python -m pytest tests/test_tune_objective.py tests/test_tune_study.py -q`
- [ ] Manual check: offline rescore script output reviewed

**Dependencies:** Tasks 1-4

**Files likely touched:**
- `tests/headless.py`
- `tests/tune.py`
- `tests/headless_report.py`

**Estimated scope:** Small: 1-2 files

## Task 6: HD ROI speedup

**Description:** Gate full-frame detect behind predicted-position ROI (with full-frame fallback on loss) so 1280x960/1920x1080 cases meet latency budget.

**Acceptance criteria:**
- [ ] E21 avg_ms <33ms (or waiver filed), E18 rmse <12.0 held
- [ ] No accuracy regression on 640x480 cases

**Verification:**
- [ ] Tests pass: `python -m pytest tests/ -q`
- [ ] Manual check: `headless --scenario E21 --seed 42` timing row reviewed

**Dependencies:** Task 5

**Files likely touched:**
- `src/pat_pipeline/detection/detector.py`
- `src/pat_pipeline/track/tracker.py`

**Estimated scope:** Medium: 3-5 files

## Checkpoint: After Tasks 5-6
- [ ] All tests pass
- [ ] No fake intermittent passes, HD timing acceptable

## Task 7: Pilot tune

**Description:** 5-trial, 1-round pilot to confirm timing and study resumption before committing to full study.

**Acceptance criteria:**
- [ ] Pilot completes ~5-15 min, dashboard reads tune.db, winner file written

**Verification:**
- [ ] Manual check: `runs/tune_*_best.json` exists, dashboard loads

**Dependencies:** Tasks 0-6

**Files likely touched:**
- `tests/tune.py`

**Estimated scope:** Small: 1-2 files

## Task 8: Stage-1 full tune + top-3 validate

**Description:** 60-trial stage-1 study on fast subset, validate top-3 on full 80 cases with real frames.

**Acceptance criteria:**
- [ ] Winner improves X5 margin and holds P0/P1 fixes, no s42-only overfit

**Verification:**
- [ ] Manual check: validate log shows full-80 verdicts for top-3

**Dependencies:** Task 7

**Files likely touched:**
- `tests/tune.py`

**Estimated scope:** Small: 1-2 files

## Task 9: Final 80-case baseline

**Description:** Full extreme suite with winner config, 4 workers, 10-min timeout; confirm FINAL VERDICT: PASS and artifacts land correctly.

**Acceptance criteria:**
- [ ] `FINAL VERDICT: PASS` (0 FAIL + 0 ERROR)
- [ ] JSON/MD/HTML/CSV/repro scripts in runs/

**Verification:**
- [ ] Tests pass: `python -m pytest tests/ -q`
- [ ] Manual check: `headless --extreme --workers 4 --timeout 600 --config <winner>` prints PASS

**Dependencies:** Task 8

**Files likely touched:**
- `tests/headless.py`

**Estimated scope:** Small: 1 file

## Checkpoint: Complete
- [ ] All acceptance criteria met
- [ ] Ready for review (`requesting-code-review` before merge)
