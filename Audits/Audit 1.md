# Untitled

## Executive summary

This audit reviewed the active `feature/ai-primary-target-identification` branch of `PAT_SIM`, including its simulator, detector, EKF/IMM tracker, PID controller, AI identity pipeline, GUI wiring, benchmark scripts, model artifacts, tests, and documentation. The repository has a strong modular foundation and a useful deterministic tracking core, but it is not yet benchmark-ready as an AI multi-target PAT simulator.

The highest-risk problems are:

1. Key AI decoy presets do not render the configured decoys.
2. Search and re-acquisition do not reliably meet the stated acquisition targets.
3. Acquisition and re-acquisition timings are measured using wall-clock execution time rather than simulation time.
4. Headless FPS reporting can use configured FPS instead of measured throughput.
5. The GUI duplicates and bypasses the central AI inference orchestrator.
6. Heuristic AI mode does not reliably produce `DECOY_CONFIRMED` decisions.
7. Blink-pattern timing and modulation-frequency requirements are inconsistent.
8. Runtime configuration changes leave EKF/IMM parameters stale.
9. AI evaluation scripts contain placeholder metrics and label-derived fallbacks.
10. Unannotated MP4 runs can report zero RMSE even though no error measurement exists.

The project should be treated as a promising engineering prototype, not as a validated final system, until the P0/P1 issues in this report are fixed.

## Audit scope and validation performed

### Reviewed areas

- Repository structure and packaging.
- Synthetic world, virtual camera, platform motion, noise, atmosphere, and trajectories.
- Classical detection and centroiding.
- Tracking state machine, EKF, IMM, and PID control.
- Multi-target track management and identity confirmation.
- AI candidate and temporal identity models.
- GUI frame loop and Control Deck configuration flow.
- Benchmark runners, metrics, logging, model artifacts, and training/evaluation scripts.
- Tests and ground-truth isolation rules.

### Local checks

- Python source compilation completed successfully with `compileall`.
- Centered clean-scene test: 90 frames at 30 FPS, 100% valid detections, approximately 0.75 px RMSE, and approximately 95.6% lock retention.
- Original P01 configuration: target remained outside the initial camera FOV; five seconds of simulation produced no acquisition.
- AI preset inspection: `ai_primary_decoys` configured two decoys but rendered one trajectory and one candidate.
- Explicit three-target identity run: the primary could be confirmed, but wrong-signature candidates remained in `IDENTITY_CHECKING` rather than becoming confirmed decoys.
- GUI execution was not attempted in the sandbox because PyQt5 and pyqtgraph were unavailable; GUI behavior was reviewed statically.

## Severity model

| Severity | Meaning |
| --- | --- |
| P0 | Breaks a mandatory workflow, invalidates a benchmark, or creates a false success condition. Fix before demo claims. |
| P1 | Major correctness, integration, or measurement problem. Fix before serious evaluation. |
| P2 | Important quality, maintainability, or usability issue. Fix before release. |
| P3 | Improvement, cleanup, or future enhancement. |

# P0 findings

## P0-01 — Decoy count is disconnected from rendered scene objects

### Evidence

AI presets define `target.count: 1` while separately defining `decoys.count: 2` or `3`. The world generator creates trajectories and rendered positions from `target.count`, not from the decoy count. As a result, the normal Primary + Decoys and Hard Negatives presets can run with no actual decoys visible. The repository README describes these presets as decoy scenarios, so the configuration and runtime semantics disagree. [[1]](https://github.com/thisIsRajbirMajhi/PAT_SIM/blob/feature/ai-primary-target-identification/configs/presets/ai_primary_decoys.yaml) [[2]](https://github.com/thisIsRajbirMajhi/PAT_SIM/blob/feature/ai-primary-target-identification/configs/presets/ai_hard_negatives.yaml) [[3]](https://github.com/thisIsRajbirMajhi/PAT_SIM/blob/feature/ai-primary-target-identification/src/fsoc_tracker/simulation/world.py)

### Impact

- Decoy rejection is not being demonstrated by the key presets.
- False-lock performance is not measured against the intended scene.
- GUI claims such as “two decoys rejected” may be impossible in the configured run.

### Required fix

Separate primary and decoy counts explicitly:

```python
primary_count = 1
decoy_count = decoys.count if decoys.enabled else 0
total_count = primary_count + decoy_count
```

Create primary and decoy trajectories independently. Preserve `target.count` only if it is explicitly documented as the total number of rendered objects. Add an end-to-end test that verifies configured decoys become visible candidates.

## P0-02 — Search and re-acquisition do not meet the stated acquisition requirements

### Evidence

The search controller uses a slowly expanding spiral. It does not provide a calibrated local ROI search followed by a complete raster/global sweep. The detector uses the predicted position for scoring but does not restrict processing to a predicted ROI. In the original P01 configuration, the target starts at `[300, 220]`, while the camera initially views the center of a 2000×2000 world. The target is outside the 640×480 viewport, and the implementation did not acquire it during a five-second run. [[4]](https://github.com/thisIsRajbirMajhi/PAT_SIM/blob/feature/ai-primary-target-identification/src/fsoc_tracker/control/camera_controller.py) [[5]](https://github.com/thisIsRajbirMajhi/PAT_SIM/blob/feature/ai-primary-target-identification/src/fsoc_tracker/simulation/virtual_camera.py) [[6]](https://github.com/thisIsRajbirMajhi/PAT_SIM/blob/feature/ai-primary-target-identification/configs/benchmarks/P01_clean_baseline.yaml)

### Impact

- Mandatory acquisition ≤2 s is not demonstrated.
- Re-acquisition ≤1 s is not guaranteed.
- The benchmark depends heavily on starting the target inside or near the FOV.

### Required fix

Implement and test three explicit search stages:

1. Local recovery around the predicted position.
2. Calibrated expanding spiral with known coverage.
3. Deterministic raster sweep with bounded dwell time.

Add a search-coverage test that starts the target at known offsets and verifies acquisition time using simulation timestamps.

# P1 findings

## P1-01 — Acquisition and re-acquisition metrics use wall-clock time

`MetricsCollector` computes acquisition and re-acquisition duration with `time.perf_counter()`. This measures how quickly the computer executes the simulation, not how much simulated time passed. A fast headless run can therefore report unrealistically small acquisition times. [[7]](https://github.com/thisIsRajbirMajhi/PAT_SIM/blob/feature/ai-primary-target-identification/src/fsoc_tracker/evaluation/metrics.py)

### Fix

Use frame timestamps for behavioral metrics:

```python
acquisition_time = lock_timestamp - run_start_timestamp
reacquisition_time = relock_timestamp - loss_timestamp
```

Use wall-clock time only for processing latency, throughput, and profiling.

## P1-02 — Headless FPS reporting can be false

The headless simulation runner and parameter sweep pass the configured camera FPS into the metrics rather than measured processing FPS. This can cause a run to report 30 FPS even when the machine cannot process 30 frames per second. [[8]](https://github.com/thisIsRajbirMajhi/PAT_SIM/blob/feature/ai-primary-target-identification/scripts/run_simulation.py) [[9]](https://github.com/thisIsRajbirMajhi/PAT_SIM/blob/feature/ai-primary-target-identification/scripts/run_parameter_sweep.py)

### Fix

Report these separately:

- source/input FPS;
- measured processing FPS;
- end-to-end wall-clock FPS;
- real-time ratio;
- dropped frames.

Never use configured FPS as measured FPS.

## P1-03 — GUI duplicates and bypasses `AIInferencePipeline.step()`

The repository defines a central AI inference orchestrator, but the GUI frame loop manually repeats candidate classification, track management, signature scoring, identity inference, and state-machine updates. This creates two AI execution paths with potentially different timeout, fallback, and confirmation behavior. [[10]](https://github.com/thisIsRajbirMajhi/PAT_SIM/blob/feature/ai-primary-target-identification/src/fsoc_tracker/ai/inference.py) [[11]](https://github.com/thisIsRajbirMajhi/PAT_SIM/blob/feature/ai-primary-target-identification/src/fsoc_tracker/ui/app.py)

### Fix

Make the GUI call one public pipeline method and consume read-only results. Remove duplicated identity logic from `ui/app.py`. Add a test proving GUI and headless AI execution produce the same identity state for the same frame sequence.

## P1-04 — Heuristic AI mode does not reliably reject decoys

When no learned model path is configured, the identity classifier falls back to a rule-based voter. It promotes candidates with signature scores above approximately 0.60 toward primary, but only treats scores below approximately 0.42 as decoys. Many wrong signatures remain in the middle range and stay `IDENTITY_CHECKING`. In an explicit three-target run, the primary was confirmed while wrong-signature candidates were not confirmed as decoys. [[12]](https://github.com/thisIsRajbirMajhi/PAT_SIM/blob/feature/ai-primary-target-identification/src/fsoc_tracker/ai/identity_model.py) [[13]](https://github.com/thisIsRajbirMajhi/PAT_SIM/blob/feature/ai-primary-target-identification/src/fsoc_tracker/ai/signatures.py)

### Fix

- Use a calibrated identity score with explicit primary, decoy, and unknown operating regions.
- Add a minimum wrong-signature threshold for decoy rejection.
- Require multi-frame confirmation for both primary and decoy decisions.
- Add end-to-end tests for bright decoys, centre-biased decoys, partial codes, and crossing candidates.

## P1-05 — Blink pattern and modulation-frequency specifications are inconsistent

The simulator advances one blink-pattern bit per video frame. An eight-bit pattern repeated at 30 FPS has a fundamental period near 3.75 Hz, which is inconsistent with the configured 12 Hz modulation frequency. The FFT-based frequency estimator therefore cannot reliably validate the stated signature. [[13]](https://github.com/thisIsRajbirMajhi/PAT_SIM/blob/feature/ai-primary-target-identification/src/fsoc_tracker/ai/signatures.py) [[3]](https://github.com/thisIsRajbirMajhi/PAT_SIM/blob/feature/ai-primary-target-identification/src/fsoc_tracker/simulation/world.py)

### Fix options

- Use code correlation only and remove the frequency claim.
- Simulate sub-frame optical samples.
- Use a sensor sample rate capable of representing 12 Hz.
- Replace the short FFT with a matched filter or Goertzel detector designed for the actual sample rate.

## P1-06 — EKF/IMM parameters become stale after configuration changes

`Tracker.update_config()` updates the top-level config but keeps the existing IMM and EKF objects. Their focal lengths, FOV, resolution, covariance, and process-noise values can remain from the previous configuration. This affects Control Deck changes to camera geometry and estimator parameters. [[14]](https://github.com/thisIsRajbirMajhi/PAT_SIM/blob/feature/ai-primary-target-identification/src/fsoc_tracker/tracking/tracker.py) [[15]](https://github.com/thisIsRajbirMajhi/PAT_SIM/blob/feature/ai-primary-target-identification/src/fsoc_tracker/tracking/imm.py)

### Fix

Rebuild the IMM and tracking state machine when configuration changes, or implement a complete `update_config()` method for every nested EKF.

## P1-07 — Detector settings are partly decorative

The detector reads adaptive-threshold configuration values such as `adaptive_block` and `adaptive_C`, but uses a global fixed threshold and a hard-coded morphology kernel. Configured values therefore do not fully control runtime behavior. [[16]](https://github.com/thisIsRajbirMajhi/PAT_SIM/blob/feature/ai-primary-target-identification/src/fsoc_tracker/perception/detector.py)

### Fix

Either implement the configured adaptive threshold and morphology controls or remove those fields. Add gradient, haze, stars, low-light, and vignette tests that verify the settings change detector behavior.

## P1-08 — AI evaluation contains placeholder metrics and label-derived fallbacks

The AI evaluation script uses manifest-provided probabilities for candidate evaluation, falls back to ground-truth labels when the identity model is unavailable, and hardcodes ECE, latency, and ablation values. The committed identity model reports perfect validation-style metrics on only a very small number of sequences, so those numbers are not sufficient evidence of model quality. [[17]](https://github.com/thisIsRajbirMajhi/PAT_SIM/blob/feature/ai-primary-target-identification/scripts/evaluate_ai_models.py) [[18]](https://github.com/thisIsRajbirMajhi/PAT_SIM/blob/feature/ai-primary-target-identification/models/identity_classifier/train_summary.json) [[19]](https://github.com/thisIsRajbirMajhi/PAT_SIM/blob/feature/ai-primary-target-identification/outputs/ai_eval/ai_metrics_test.json)

### Fix

- Run the actual model for every evaluation sample.
- Fail if a required model is missing instead of copying labels.
- Compute real confusion matrices, ECE, latency, and ablations.
- Split by complete scenario and seed.
- Report confidence intervals and per-scenario false-lock rates.

## P1-09 — MP4 benchmark can report meaningless zero RMSE

When external-video annotations are missing, the benchmark runner creates ground truth with no image position. The metrics then have no error samples and report RMSE as zero. That is not perfect tracking; it is unavailable ground truth. The command-line video runner also uses the classical detector/tracker path rather than the complete AI identity path. [[20]](https://github.com/thisIsRajbirMajhi/PAT_SIM/blob/feature/ai-primary-target-identification/scripts/run_video_benchmark.py) [[21]](https://github.com/thisIsRajbirMajhi/PAT_SIM/blob/feature/ai-primary-target-identification/src/fsoc_tracker/input/video_source.py)

### Fix

Report `N/A — annotations unavailable` for RMSE and related accuracy metrics. Add explicit `--ai` support to video benchmarking if learned identity is part of the claim. Include an annotated sample MP4 or make the benchmark fail clearly when the required input is absent.

## P1-10 — AI dependencies are not included in the documented install path

The runtime requirements include NumPy, OpenCV, PyQt5, pyqtgraph, PyYAML, and Pillow, but do not declare PyTorch, torchvision, or onnxruntime. The training and learned inference workflows require those packages. [[22]](https://github.com/thisIsRajbirMajhi/PAT_SIM/blob/feature/ai-primary-target-identification/requirements.txt) [[23]](https://github.com/thisIsRajbirMajhi/PAT_SIM/blob/feature/ai-primary-target-identification/scripts/export_models.py)

### Fix

Provide dependency profiles:

- `requirements.txt` for classical runtime;
- `requirements-ai.txt` for ONNX inference;
- `requirements-training.txt` for PyTorch/torchvision training;
- an installation check that explains which modes are available.

## P1-11 — Learned models are not enabled by shipped presets

The README explains that AI mode with empty model paths uses heuristic fallback, and the shipped AI presets set model paths to null. The repository does contain ONNX artifacts, but the normal GUI presets do not automatically wire them into runtime. [[24]](https://github.com/thisIsRajbirMajhi/PAT_SIM/blob/feature/ai-primary-target-identification/README.md) [[1]](https://github.com/thisIsRajbirMajhi/PAT_SIM/blob/feature/ai-primary-target-identification/configs/presets/ai_primary_decoys.yaml)

### Fix

Provide an explicit “Heuristic AI” and “Learned AI” mode. For learned mode, validate both model paths before a run and show the active model versions in the dashboard.

# P2 findings

## P2-01 — Model paths are working-directory dependent

The Control Deck accepts model paths as strings and runtime loading uses them directly. Running the installed application from another working directory can make relative model paths fail. [[25]](https://github.com/thisIsRajbirMajhi/PAT_SIM/blob/feature/ai-primary-target-identification/src/fsoc_tracker/ai/candidate_model.py) [[12]](https://github.com/thisIsRajbirMajhi/PAT_SIM/blob/feature/ai-primary-target-identification/src/fsoc_tracker/ai/identity_model.py)

### Fix

Resolve paths relative to the project/package root or require absolute paths after validation. Display the resolved path and load status in the Control Deck.

## P2-02 — `.env.example` settings are not clearly wired into runtime

The repository provides environment variables for logging, FPS, seeds, paths, and feature flags, but the documented runtime path does not clearly load `.env` or apply these values. The project also does not list a dotenv dependency. [[26]](https://github.com/thisIsRajbirMajhi/PAT_SIM/blob/feature/ai-primary-target-identification/.env.example)

### Fix

Either implement environment loading with explicit precedence or remove the unused environment contract. Document precedence as CLI > Control Deck > config file > environment > defaults, or another chosen rule.

## P2-03 — Deployment documentation and export CLI disagree

Deployment documentation mentions a TFLite export command, while the export script currently accepts only ONNX as a format choice. [[27]](https://github.com/thisIsRajbirMajhi/PAT_SIM/blob/feature/ai-primary-target-identification/docs/deployment.md) [[23]](https://github.com/thisIsRajbirMajhi/PAT_SIM/blob/feature/ai-primary-target-identification/scripts/export_models.py)

### Fix

Either implement TFLite export or remove the unsupported command from the documentation.

## P2-04 — Test suite coverage is stronger on structure than on real success criteria

The tests verify source-level ground-truth isolation, state transitions, file outputs, and that scenarios do not crash. Several benchmark expectations are intentionally relaxed when acquisition does not occur. The AI decoy test checks blink-correlation primitives but does not validate full scene rendering, track association, identity confirmation, and controller gating together. [[28]](https://github.com/thisIsRajbirMajhi/PAT_SIM/blob/feature/ai-primary-target-identification/tests/test_headless_presets.py) [[29]](https://github.com/thisIsRajbirMajhi/PAT_SIM/blob/feature/ai-primary-target-identification/tests/scenarios/test_ai_decoy_rejection.py)

### Fix

Add mandatory pass/fail tests for:

- decoy count equals rendered decoy count;
- acquisition from defined offsets within 2 s simulation time;
- re-acquisition from forced loss within 1 s simulation time;
- no primary lock on a wrong signature;
- learned model missing or timeout fallback;
- configuration changes rebuilding estimator geometry;
- annotated MP4 accuracy;
- measured throughput rather than configured throughput.

# Recommended change plan

## Phase 1 — Correctness blockers

1. Fix primary/decoy scene construction.
2. Repair simulation-time metrics.
3. Repair measured FPS reporting.
4. Make P01/P10 acquisition scenarios physically valid.
5. Implement deterministic local, spiral, and raster search.
6. Rebuild EKF/IMM after configuration changes.

## Phase 2 — AI integration

1. Make the GUI use `AIInferencePipeline.step()`.
2. Define a physically consistent optical signature model.
3. Improve heuristic decoy classification.
4. Add candidate embeddings or explicitly standardize the GRU input to the 11-feature contract.
5. Validate model paths and runtime availability before starting a learned-AI run.
6. Separate heuristic AI from learned AI in the UI and reports.

## Phase 3 — Evaluation integrity

1. Remove label-copy fallbacks.
2. Replace hardcoded ECE, latency, and ablation values.
3. Expand identity train/validation/test sequences.
4. Use seed- and scenario-level splits.
5. Report `N/A` instead of zero when annotations are absent.
6. Add confidence intervals and false-lock metrics.

## Phase 4 — Demo and release hardening

1. Add a dependency checker and reproducible installation profiles.
2. Include an annotated MP4 fixture or a clear external-benchmark setup guide.
3. Display source FPS, measured FPS, latency, active model, seed, and configuration hash.
4. Add a CI job for classical, heuristic-AI, and learned-AI smoke tests.
5. Make GUI and headless execution share the same pipeline facade.
6. Update deployment documentation to match the actual export commands.

# Final assessment

| Area | Assessment |
| --- | --- |
| Modular architecture | Strong |
| Centered deterministic tracking | Strong |
| GUI concept | Strong |
| Controller safety | Good |
| Search/re-acquisition | Weak |
| Multi-target/decoy simulation | Incorrect for key presets |
| Heuristic AI identity | Partial |
| Learned model integration | Present but not production-ready |
| Evaluation credibility | Weak until placeholders are removed |
| Benchmark readiness | Not ready |

The best next milestone is not a larger neural model. It is a trustworthy end-to-end benchmark: rendered decoys, simulation-time metrics, measured throughput, deterministic search coverage, and real model evaluation. Once those are correct, model improvements will produce meaningful evidence rather than better-looking reports.

[](https://app.notion.com/p/b78112f3cb8042d7847263512f04e4cb?pvs=21)