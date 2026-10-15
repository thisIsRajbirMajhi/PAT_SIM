# Implementation Plan: Fix 23 headless failures (80-case suite)

## Overview
Baseline `runs/headless_20261015_125258` is 46 strict + 11 intermittent + 23 fail, 0 error. Failures cluster into P0 blindness (CORE), seed-fragile acquisition, lenient intermittent masking huge RMSE, HD throughput, and rate sensitivity. Fix code first (tuning cannot fix a hardcoded floor or s42-only overfit), then pilot-tune, then full tune, then re-baseline to `FINAL VERDICT: PASS`.

## Architecture Decisions
- Adaptive detection threshold over fixed floor: `src/pat_pipeline/detection/detector.py:39-44` floor `120` kills dim beacons (`E11` at 0.56x brightness). Make floor dim-aware (e.g. scale with median/p98) rather than lowering `threshold_k` globally.
- Colour path must be measurement-neutral: `src/fsoc_tracker/input/synthetic_source.py:120-126` tint raises background median; detector already does `BGR2GRAY` at `detector.py:28-29`. Keep conversion, remove/compensate tint effect on threshold.
- Acquisition persistence over sensitivity boost: seed variance (`X4: 51%/0%/68%`) points to search give-up, not detector gain. Fix `search_policy`/`state_machine` timeouts first.
- Harness honesty: `tests/headless.py:742` intermittent gate ignores `rmse/lock`. Add RMSE gate so wrong-target tracks (150-300px) fail instead of `INTERMITTENT-PASS`. Mirror in `tests/tune.py:115-120` loss so tuner optimizes the same gate.
- Throughput via ROI, not full-frame shrink: HD cases (`E18/E21`) spend 36-61ms in full-frame blur+components. Gate full processing behind predicted-position ROI.

## Task List

### Phase 0: Diagnostics (no fixes)
- [x] Task 0: per-frame threshold trace (see todo) — DONE 2026-10-15: E11 floor-hit confirmed (raw 140/blur 84 vs floor 120); E10 geometric (peak 246, gt never in FOV, search TILE), not threshold

### Checkpoint: Diagnostics
- [ ] Trace shows why E10/E11 never valid; hypothesis confirmed or revised before any edit

### Phase 1: P0 blindness (CORE)
- [ ] Task 1: adaptive threshold floor
- [ ] Task 2: colour-path neutrality

### Checkpoint: P0
- [ ] `E10>=40% lock`, `E11>0%`, `X1` still STRICT-PASS, `pytest tests/ -q` green

### Phase 2: Acquisition + rate
- [ ] Task 3: search persistence (seed-brittle)
- [ ] Task 4: dt normalization (E8/E22)

### Checkpoint: Acquisition
- [ ] Seed spread <20pp on X2/X4/X11; `E8>=40%`, `E22>=10%`

### Phase 3: Harness + throughput
- [ ] Task 5: intermittent RMSE gate (headless + tune)
- [ ] Task 6: HD ROI speedup

### Checkpoint: Harness
- [ ] Rescored JSON marks 150px+ RMSE as FAIL; `E21 avg<33ms` or documented waiver

### Phase 4: Tune + accept
- [ ] Task 7: pilot tune (5 trials)
- [ ] Task 8: stage1 full (60 trials) + top-3 validate
- [ ] Task 9: final 80-case baseline PASS

### Checkpoint: Complete
- [ ] `FINAL VERDICT: PASS`, artifacts in `runs/`, ready for review

## Risks and Mitigations
| Risk | Impact | Mitigation |
|------|--------|------------|
| Adaptive floor hurts X1/E1 bright cases | High | Gate floor change behind dim-detection (only lower when median/p98 low); verify X1/E1 stay STRICT-PASS |
| Search persistence slows avg_ms | Med | Bound extra search by frames, measure R5 latency budget each task |
| RMSE gate turns current intermittent passes red | Med | Expected and honest; tune Stage 2 policy after gate lands |
| Tuning overfits s42 fast subset | High | Validate top-3 on full 80 incl. s7/s99 before accepting any winner |

## Open Questions
- E25 zero-void `28%<50%`: detector OK with no clutter — is bench too high or is search dependent on stars? Decide after Task 1 trace.
- E21 `61ms` on 1920x1080: accept ROI fix or file throughput waiver for HD60?
