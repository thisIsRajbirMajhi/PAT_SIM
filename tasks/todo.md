## Task 0: Baseline pytest + headless runs [DONE]
**Description:** Record pre-refactor test + simulation baseline for later comparison.
**Baseline recorded:** `pytest -q` 47 passed; X1-baseline PASS (rmse=0.7 loss=41.9% lock=58.1% valid=527 postlock=100.0%).
**Description:** Record pre-refactor test + simulation baseline for later comparison.
**Acceptance criteria:**
- [ ] `python -m pytest -q` outcome recorded (pass/fail + counts)
- [ ] Representative headless scenario output recorded (same seed/frames)
- [ ] Env blockers noted if anything cannot run
**Verification:**
- [ ] Tests pass: `python -m pytest -q`
- [ ] Build succeeds: `python -c "import fsoc_tracker.pipeline, fsoc_tracker.camera"`
- [ ] Manual check: headless single scenario runs
**Dependencies:** None
**Files likely touched:** (none — read-only)
**Estimated scope:** Small

## Checkpoint: After Task 0
- [ ] Baseline recorded
- [ ] Proceed with extraction

## Task 1: Scaffold pat_pipeline structure + public API
**Description:** Create `src/pat_pipeline/` tree, `__init__.py` exports, `config.py`, `factory.py` pointing at canonical locations.
**Acceptance criteria:**
- [ ] Tree matches Prompt.md S2 (detection/estimation/state/track/orchestration/camera)
- [ ] `from pat_pipeline import BeaconDetector, Tracker, CameraController, VirtualCamera, DisplayTracker, DisplayStatus, SearchTrackPipeline` succeeds
- [ ] No Qt/ui imports in package
**Verification:**
- [ ] Tests pass: `python -c "import pat_pipeline"`
- [ ] Build succeeds: `python -m compileall -q src/pat_pipeline`
- [ ] Manual check: `python -c "import sys; import pat_pipeline; print([m for m in sys.modules if 'PyQt' in m or 'pyqtgraph' in m])"` is empty
**Dependencies:** Task 0
**Files likely touched:**
- `src/pat_pipeline/__init__.py`
- `src/pat_pipeline/config.py`
- `src/pat_pipeline/factory.py`
**Estimated scope:** Small

## Task 2: Move detection + estimation
**Description:** Canonical detector.py, ekf.py, imm.py live in `pat_pipeline`; internal imports updated.
**Acceptance criteria:**
- [ ] Algorithms byte-identical behavior (no threshold/math changes)
- [ ] Imports resolve within `pat_pipeline`, shared types from `fsoc_tracker.common`
- [ ] No GUI imports transitively
**Verification:**
- [ ] Tests pass: `python -m pytest -q tests/test_display_status.py`
- [ ] Build succeeds: `python -m compileall -q src/pat_pipeline/detection src/pat_pipeline/estimation`
- [ ] Manual check: detector+IMM smoke on synthetic frame
**Dependencies:** Task 1
**Files likely touched:**
- `src/pat_pipeline/detection/__init__.py`
- `src/pat_pipeline/detection/detector.py`
- `src/pat_pipeline/estimation/__init__.py`
- `src/pat_pipeline/estimation/ekf.py`
- `src/pat_pipeline/estimation/imm.py`
**Estimated scope:** Medium

## Task 3: Move state + track
**Description:** Canonical state_machine, search_policy, tracker, display in `pat_pipeline`.
**Acceptance criteria:**
- [ ] State machine + search policy + tracker + display import from `pat_pipeline`
- [ ] search_policy remains dependency-free (no camera/tracking imports)
- [ ] DisplayTracker has no GUI dep
**Verification:**
- [ ] Tests pass: `python -m pytest -q tests/test_display_status.py tests/test_smart_search.py`
- [ ] Build succeeds: `python -m compileall -q src/pat_pipeline/state src/pat_pipeline/track`
- [ ] Manual check: cold-start acquire/lock smoke
**Dependencies:** Task 2
**Files likely touched:**
- `src/pat_pipeline/state/__init__.py`
- `src/pat_pipeline/state/state_machine.py`
- `src/pat_pipeline/state/search_policy.py`
- `src/pat_pipeline/track/__init__.py`
- `src/pat_pipeline/track/tracker.py`
- `src/pat_pipeline/track/display.py`
**Estimated scope:** Medium

## Task 4: Move camera optics + control
**Description:** Canonical geometry, virtual_camera, pid, camera_controller in `pat_pipeline/camera`.
**Acceptance criteria:**
- [ ] CameraController reads search spec from `pat_pipeline.state`
- [ ] No camera<->pipeline cycle
- [ ] Optics pure (numpy only, cv2 only for resize path)
**Verification:**
- [ ] Tests pass: `python -m pytest -q tests/test_smart_search.py tests/test_pat_improvements.py`
- [ ] Build succeeds: `python -m compileall -q src/pat_pipeline/camera`
- [ ] Manual check: controller step returns TRACK/TILE cases
**Dependencies:** Task 3
**Files likely touched:**
- `src/pat_pipeline/camera/__init__.py`
- `src/pat_pipeline/camera/optics/__init__.py`
- `src/pat_pipeline/camera/optics/geometry.py`
- `src/pat_pipeline/camera/optics/virtual_camera.py`
- `src/pat_pipeline/camera/control/__init__.py`
- `src/pat_pipeline/camera/control/pid.py`
- `src/pat_pipeline/camera/control/camera_controller.py`
**Estimated scope:** Medium

## Task 5: Move orchestration + fix scheduled-hold bug
**Description:** Canonical pat_loop.py in `pat_pipeline/orchestration`; `scheduled` flows explicitly into `_controller_ctx`; regression test.
**Acceptance criteria:**
- [ ] `_controller_ctx` takes scheduled-hold as explicit arg (no undefined variable)
- [ ] `step_frame` order: predict->gate->detect->estimate->state->ctx->control(hold)->return
- [ ] Regression test covers scheduled-hold ctx path
- [ ] No algorithm/semantics changes otherwise
**Verification:**
- [ ] Tests pass: new scheduled-hold regression test
- [ ] Build succeeds: `python -m compileall -q src/pat_pipeline/orchestration`
- [ ] Manual check: blink/hidden frame holds gimbal via ctx
**Dependencies:** Task 4
**Files likely touched:**
- `src/pat_pipeline/orchestration/__init__.py`
- `src/pat_pipeline/orchestration/pat_loop.py`
- `tests/test_pat_pipeline_scheduled_hold.py`
**Estimated scope:** Medium

## Checkpoint: After Tasks 1-5
- [ ] All `pat_pipeline` modules import without Qt/ui
- [ ] No circular imports
- [ ] Existing tests still pass

## Task 6: Legacy shims (fsoc_tracker -> pat_pipeline) [DONE]
**Verification:** 15/15 legacy class/factory identities hold; no `^class `/`^def make_` left under old paths; pytest 50 passed.
**Description:** Replace `fsoc_tracker/pipeline/*` and `fsoc_tracker/camera/*` bodies with thin re-exports; verify class identity.
**Acceptance criteria:**
- [ ] Every old import path still works
- [ ] `fsoc_tracker.pipeline.Tracker is pat_pipeline.track.tracker.Tracker` (and detector/IMM/SM/policy/controller/camera equivalents)
- [ ] No stale duplicate implementations remain
**Verification:**
- [ ] Tests pass: `python -m pytest -q`
- [ ] Build succeeds: `python -c` identity checks for all moved classes
- [ ] Manual check: grep shows no old duplicate class defs
**Dependencies:** Task 5
**Files likely touched:**
- `src/fsoc_tracker/pipeline/**/*.py`
- `src/fsoc_tracker/camera/**/*.py`
**Estimated scope:** Medium

## Task 7: Refactor headless.py to pat_pipeline
**Description:** `run_single` uses `pat_pipeline` canonical classes/orchestrator; preserves all CLI, scenarios, metrics, verdicts; GT never feeds detector/tracker.
**Acceptance criteria:**
- [ ] All CLI args/modes preserved (frames/seed/set/cue/far-start/extreme/video)
- [ ] Detection gating + ego compensation + control-hold behavior preserved
- [ ] Metrics/logging/stages/verdicts unchanged
**Verification:**
- [ ] Tests pass: `python -m pytest -q`
- [ ] Build succeeds: headless baseline scenario runs
- [ ] Manual check: frame-level deterministic compare pre/post (detection/estimate/cmd/states)
**Dependencies:** Task 6
**Files likely touched:**
- `headless.py`
**Estimated scope:** Medium

## Task 8: Refactor ui/app.py _tick to shared path
**Description:** GUI uses canonical pipeline for frame processing; rendering/timers/widgets stay in UI; no `pat_pipeline -> ui` dep.
**Acceptance criteria:**
- [ ] `_tick` detect->track->control->display order preserved via shared API
- [ ] Host-specific FOV/limit/ego ctx still supplied by GUI
- [ ] No GUI imports inside `pat_pipeline`
**Verification:**
- [ ] Tests pass: `python -m pytest -q tests/test_overlays_headless.py`
- [ ] Build succeeds: `python -m compileall -q src/fsoc_tracker/ui`
- [ ] Manual check: GUI tick imports resolve (headless overlay test covers logic)
**Dependencies:** Task 7
**Files likely touched:**
- `src/fsoc_tracker/ui/app.py`
**Estimated scope:** Medium

## Checkpoint: After Tasks 6-8
- [ ] headless + GUI use canonical pipeline
- [ ] Legacy imports verified identical
- [ ] No GUI dep in pipeline

## Task 9: Packaging extras + README [DONE]
- Core deps in `pyproject.toml` (numpy/opencv/yaml/pillow); `gui` extra (PyQt5/pyqtgraph). Qt confined to `main.py`+`ui/*`; headless verified with Qt import-blocked.
- `src/pat_pipeline/README.md` written per S11.
**Description:** Split GUI deps to optional extra, document install commands, write `src/pat_pipeline/README.md`.
**Acceptance criteria:**
- [ ] `pyproject.toml` core install does not require Qt; `pip install -e .[gui]` restores GUI workflow
- [ ] README covers purpose/architecture/API/lifecycle/per-frame contract/host commands/shared deps/GUI-less testing/legacy relations/limitations
- [ ] Install commands actually tested
**Verification:**
- [ ] Tests pass: clean-process import of `pat_pipeline` without Qt
- [ ] Build succeeds: `pip install -e .` and GUI extra path verified
- [ ] Manual check: README examples run
**Dependencies:** Task 8
**Files likely touched:**
- `pyproject.toml`
- `src/pat_pipeline/README.md`
**Estimated scope:** Small

## Task 10: New tests (isolation + behavior + compat) [DONE]
- 15 new tests, full suite 62 passed: isolation (7), behavior (5), scheduled-hold (3).
**Description:** Add focused pytest coverage per Prompt.md S9.
**Acceptance criteria:**
- [ ] Public imports succeed in clean process; no Qt/ui import
- [ ] Shared types/enums identity; legacy identity; init/reset/update_config
- [ ] Frame order, cold-start lock, stale-gate, loss/reacq, control hold, blink/hidden, ego ctx, scheduled-hold ctx, GUI-less run
- [ ] No mock-away-the-implementation tests
**Verification:**
- [ ] Tests pass: `python -m pytest -q`
- [ ] Build succeeds: full suite green (or blockers documented)
- [ ] Manual check: coverage of each S9 bullet
**Dependencies:** Task 9
**Files likely touched:**
- `tests/test_pat_pipeline_*.py`
**Estimated scope:** Medium

## Task 11: Full regression + report
**Description:** Run pytest + representative headless scenarios (+ extreme if supported), compare pre/post, write final report.
**Acceptance criteria:**
- [ ] `python -m pytest -q` result documented
- [ ] X1/X4/X5/X6/X9 scenarios (+ extreme) compared on detection/estimate/cmd/states/errors/loss/lock
- [ ] Only wall-clock FPS/latency allowed to vary; functional diffs investigated
- [ ] Changed files, decisions, results, failures, remaining work reported
**Verification:**
- [ ] Tests pass: `python -m pytest -q`
- [ ] Build succeeds: all scenario runs complete
- [ ] Manual check: deterministic compare artifacts saved
**Dependencies:** Task 10
**Files likely touched:** (report only)
**Estimated scope:** Medium

## Checkpoint: Complete
- [ ] Prompt.md S13 definition of done met
- [ ] Ready for review
