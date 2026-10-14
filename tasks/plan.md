# Implementation Plan: Extract PAT-SIM into `src/pat_pipeline/`

## Overview
Move the search-to-track implementation (detection, estimation, state, track/display, orchestration, camera optics+control) from `src/fsoc_tracker/` into new canonical package `src/pat_pipeline/`. Keep shared types/enums/config/visibility in `fsoc_tracker`. Re-point `fsoc_tracker.pipeline` and `fsoc_tracker.camera` at canonical classes via thin shims, refactor `headless.py` and `ui/app.py` to consume `pat_pipeline`, fix the `scheduled` context bug in `pat_loop`, split GUI extras in packaging, add isolation + behavior tests, and verify with pytest + headless scenarios.

## Architecture Decisions
- Canonical move (not wrappers): real code lives in `pat_pipeline/*`; `fsoc_tracker.pipeline/*` and `fsoc_tracker.camera/*` become `from pat_pipeline... import *` shims so class identity holds (`is` check). Per Prompt.md S2 rules 2-4.
- Shared deps stay put: `common/types.py`, `common/data/`, `common/enums/`, `config/defaults.py`+loader+validation, `target/dynamics/visibility.py`, other GUI-free utils. No copying. `pat_pipeline` imports them via `fsoc_tracker.*` (documented in README as future-separation opportunity).
- `SearchTrackPipeline.step_frame` keeps host-supplied-context contract: host passes `frame_image` (np array) or `Frame` + `in_fov/at_limit/ego_rate`; pipeline returns `(detection, estimate, command)` and optionally display state. Host (headless/GUI) still owns sources, GT scoring, logging, rendering. Fixes `scheduled` flow explicitly.
- DisplayTracker moves into pipeline (no Qt dep); rendering stays in UI.
- Packaging: `pyproject.toml` core deps = numpy, opencv, yaml, pillow; move PyQt5/pyqtgraph to `[project.optional-dependencies] gui`. Keep default install working (`pip install -e .` still gets GUI via extra or documented command).

## Task List

### Phase 0: Baseline
- [ ] Task 0: Baseline pytest + headless runs (record metrics)

### Checkpoint: Baseline
- [ ] Baseline recorded, env blockers noted

### Phase 1: Canonical package
- [ ] Task 1: Scaffold `src/pat_pipeline/` structure + `__init__` public API + `config.py`/`factory.py`
- [ ] Task 2: Move detection + estimation (detector, ekf, imm)
- [ ] Task 3: Move state (state_machine, search_policy) + track (tracker, display)
- [ ] Task 4: Move camera (optics geometry/virtual_camera, control pid/camera_controller)
- [ ] Task 5: Move orchestration (pat_loop) + fix scheduled-hold context bug + regression test

### Checkpoint: Package stands alone
- [ ] `pat_pipeline` imports without Qt/ui; no cycles

### Phase 2: Compatibility + hosts
- [ ] Task 6: Legacy shims in `fsoc_tracker.pipeline/*` + `fsoc_tracker.camera/*` (class identity)
- [ ] Task 7: Refactor `headless.py` to `pat_pipeline`, preserve CLI/behavior
- [ ] Task 8: Refactor `ui/app.py` `_tick` to shared path, keep rendering in UI

### Checkpoint: Hosts integrated
- [ ] headless + GUI paths use canonical pipeline

### Phase 3: Packaging, docs, tests, regression
- [ ] Task 9: Packaging extras + README
- [ ] Task 10: New tests (isolation, frame order, gating, control hold, scheduled hold, compat)
- [ ] Task 11: Full regression (pytest + headless scenarios + extreme if supported)

### Checkpoint: Complete
- [ ] Definition of done (Prompt.md S13) met, report written

## Risks and Mitigations
| Risk | Impact | Mitigation |
|------|--------|------------|
| Circular imports (camera<->pipeline via search_policy) | High | search_policy stays dependency-free; controller imports from `pat_pipeline.state`; verify after each move |
| pat_loop vs headless/_tick divergence (frame_id, FOV, control hold) | High | Compare line-by-line first; host passes explicit ctx; deterministic frame-level compare in regression |
| `scheduled` NameError currently latent | Med | Fix by explicit param + regression test (Prompt S5) |
| GUI extras split breaks `pip install` workflow | Med | Keep working install command documented + tested |
| Scope creep (algorithm rewrites) | Med | No threshold/math changes; structural moves only |

## Open Questions
- None blocking; Prompt.md is the spec. Installation preference (extras vs dual-requirements) decided in Task 9 with verification.
