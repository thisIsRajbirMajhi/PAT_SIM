# Untitled

## Verdict

The AI pipeline is **partially implemented but not fully working as an end-to-end primary-target identification system**.

The repository contains most planned components:

```
classical candidate generation
→ candidate classifier
→ multi-target track manager
→ temporal identity classifier
→ identity state machine
→ EKF/IMM tracker
→ bounded PID/search control
```

However, the complete behavior does not yet satisfy the intended goal. The biggest blockers are:

- important AI presets do not render the configured decoys;
- the GUI bypasses the central AI pipeline orchestrator;
- shipped presets run heuristic fallback rather than learned models;
- heuristic identity logic confirms primaries more readily than decoys;
- the optical signature frequency model is inconsistent with the frame rate;
- AI confidence is not fully integrated into EKF/IMM covariance and model selection;
- timeout/failure fallback behavior is not consistently applied by the GUI;
- evaluation results contain placeholders and are not sufficient evidence of model quality.

The current implementation is best described as an **AI integration scaffold with a working classical safety path**, not a validated AI target-identification pipeline.

## Expected working goal

The intended production behavior is:

1. Render one primary beacon plus the configured number of decoys.
2. Detect every beacon-like candidate independently.
3. Assign stable track IDs while candidates move, cross, disappear, and reappear.
4. Run candidate-level appearance classification.
5. Build a temporal history for every track.
6. Evaluate appearance, motion, persistence, estimator consistency, and optical signature.
7. Produce calibrated probabilities for `PRIMARY`, `DECOY`, and `UNKNOWN`.
8. Require several consecutive frames before confirming either primary or decoy identity.
9. Allow full PID control only for `PRIMARY_CONFIRMED`.
10. Keep `UNKNOWN` and `IDENTITY_CHECKING` candidates under bounded control or search.
11. Remember rejected decoys without permanently blocking legitimate re-identification.
12. Increase uncertainty and avoid aggressive control if AI inference fails or times out.
13. Report model version, confidence, evidence, false locks, identity switches, and latency.
14. Demonstrate these behaviors with real multi-decoy benchmark scenarios.

## Stage-by-stage pipeline audit

| Stage | Current status | Expected goal | Assessment |
| --- | --- | --- | --- |
| Scene and decoy rendering | Partial | Render primary and all configured decoys | Fails for key presets |
| Candidate generation | Working baseline | Detect all plausible bright candidates | Works, but configuration is partly decorative |
| Stage-1 AI classifier | Partial | Classify beacon, decoy, noise, unknown | Heuristic fallback works; learned path is optional and unverified |
| Track manager | Partial | Maintain one independent history per candidate | Basic nearest-neighbor tracking works; association is fragile |
| Signature extraction | Partial | Reliably distinguish primary code/frequency from decoys | Timing model is inconsistent |
| Stage-2 identity model | Partial | Use track sequence to produce calibrated identity probabilities | Model adapter exists; evidence and training are weak |
| Identity confirmation | Working structurally | Require N consecutive confirmations | State machine works but inputs are not reliable enough |
| EKF/IMM integration | Partial | Use AI confidence to adapt measurement covariance and model probabilities | Only indirect integration is implemented |
| PID gating | Mostly working | Full control only after primary confirmation | Safety intent is correct |
| AI failure fallback | Partial | Increase uncertainty, reduce control, log failure | Central path supports it; GUI bypass weakens it |
| Evaluation | Not trustworthy | Measure real false-lock and decoy rejection performance | Placeholder and label-derived metrics exist |
| GUI observability | Good concept, partial truth | Show what was detected and why | UI exists but may display incomplete or heuristic evidence |

## 1. Scene and decoy rendering

### Current behavior

AI presets such as `ai_primary_decoys` define a primary target count of one and a separate decoy count of two. The world generator uses `target.count` when creating trajectories and rendered positions. It does not add `decoys.count` to the rendered scene. Therefore a preset that claims to contain two decoys can produce only one visible target. [[1]](https://github.com/thisIsRajbirMajhi/PAT_SIM/blob/feature/ai-primary-target-identification/configs/presets/ai_primary_decoys.yaml) [[2]](https://github.com/thisIsRajbirMajhi/PAT_SIM/blob/feature/ai-primary-target-identification/src/fsoc_tracker/simulation/world.py)

### Why this breaks the AI goal

The identity model cannot reject decoys that do not exist. A primary-only run can appear successful while never testing the hardest failure mode: locking onto a visually similar false beacon.

### Fix

Create an explicit scene object model:

```python
SceneObject(
    object_id,
    role="PRIMARY" | "DECOY",
    trajectory,
    appearance,
    optical_signature,
)
```

Construct one primary and `decoys.count` decoys when enabled. Add a test that asserts:

```
configured_decoy_count == rendered_decoy_count
```

and another that asserts every visible object receives a candidate and track ID.

## 2. Classical candidate generation

### Current behavior

`BeaconDetector.detect_candidates()` performs grayscale conversion, Gaussian blur, global thresholding, morphology, connected components, feature extraction, centroid calculation, and 64×64 patch extraction. This is the strongest working part of the AI path. [[3]](https://github.com/thisIsRajbirMajhi/PAT_SIM/blob/feature/ai-primary-target-identification/src/fsoc_tracker/perception/detector.py)

The detector returns useful candidate features:

- centroid;
- bounding box;
- area;
- width and height;
- aspect ratio;
- brightness;
- peak intensity;
- local contrast;
- compactness;
- distance from prediction;
- patch data.

### Problems

- Configured `adaptive_block` and `adaptive_C` values are not actually used.
- The detector uses a fixed global threshold strategy.
- Candidate proximity is a score term, not a proper prediction gate.
- Detection quality is not calibrated against false candidate rate.
- A `DECOY_LIKE` candidate is not naturally produced by the heuristic classifier.

### Fix

Implement selectable threshold modes:

```
fixed
percentile
adaptive mean
adaptive Gaussian
background + kσ
```

Add a real ROI gate around the predicted position during local tracking, while retaining full-frame processing during search. Unit-test candidate recall and false positives independently from identity performance.

## 3. Stage-1 candidate classifier

### Current behavior

The repository supports a MobileNetV3-Small-style candidate classifier and an ONNX adapter. When no model path is configured, it uses a deterministic heuristic based on brightness, compactness, area, aspect ratio, and local contrast. [[4]](https://github.com/thisIsRajbirMajhi/PAT_SIM/blob/feature/ai-primary-target-identification/src/fsoc_tracker/ai/candidate_model.py)

The shipped AI presets set model paths to null, so normal AI runs use heuristic fallback rather than the learned ONNX model. [[1]](https://github.com/thisIsRajbirMajhi/PAT_SIM/blob/feature/ai-primary-target-identification/configs/presets/ai_primary_decoys.yaml) [[5]](https://github.com/thisIsRajbirMajhi/PAT_SIM/blob/feature/ai-primary-target-identification/README.md)

### Problems

- `ai.enabled=true` does not mean learned inference is active.
- The fallback classifier generally produces `BEACON_LIKE`, `NOISE`, or `UNKNOWN`, not reliable `DECOY_LIKE` outputs.
- Model paths are relative to the process working directory.
- PyTorch, torchvision, and onnxruntime are not part of the standard dependency list.

### Expected behavior

The UI should clearly distinguish:

```
AI OFF
HEURISTIC AI
LEARNED AI — model loaded
LEARNED AI — model unavailable / fallback
```

### Fix

Validate model files before a learned-AI run. Display resolved paths, model versions, input dimensions, and load status. Provide separate runtime and training requirements. Do not silently label a heuristic run as a learned-model evaluation.

## 4. Multi-target track management

### Current behavior

`TrackManager` maintains per-track histories and uses greedy nearest-neighbor association with a fixed pixel gate. It stores positions, velocities, brightness, size, confidence, blink history, innovation, and IMM probabilities. It also has rejected-decoy memory. [[6]](https://github.com/thisIsRajbirMajhi/PAT_SIM/blob/feature/ai-primary-target-identification/src/fsoc_tracker/tracking/track_manager.py)

### Problems

- Greedy association can swap identities during crossing trajectories.
- The gate is derived from a hard-coded pixel multiplier rather than track covariance.
- Rejected-decoy position memory is position-based and can suppress a legitimate candidate near the same location.
- Track histories do not clearly preserve candidate appearance embeddings for the 139-dimensional GRU contract.
- Decoy memory and identity-state cleanup are spread across multiple components.

### Fix

Use a covariance-aware association cost:

```
Mahalanobis position cost
+ appearance similarity
+ velocity consistency
+ track age penalty
```

For multiple close candidates, use Hungarian assignment or a confirmed-track priority policy. Add crossing-target tests and verify that identity switches remain zero or within a documented bound.

## 5. Optical signature processing

### Current behavior

The primary signature uses an eight-bit pattern such as `10110010`. The simulator advances one bit per video frame and the signature module estimates frequency from the blink history using an FFT. [[7]](https://github.com/thisIsRajbirMajhi/PAT_SIM/blob/feature/ai-primary-target-identification/src/fsoc_tracker/ai/signatures.py) [[2]](https://github.com/thisIsRajbirMajhi/PAT_SIM/blob/feature/ai-primary-target-identification/src/fsoc_tracker/simulation/world.py)

### Problem

At 30 FPS, one pattern bit per frame produces an eight-frame repeating cycle, approximately 3.75 Hz. That is inconsistent with the configured 12 Hz modulation frequency. The system therefore cannot simultaneously claim that the pattern is sampled one bit per frame and that the same history reliably measures 12 Hz.

### Fix

Choose and document one signal model:

- code-only identity with no frequency estimate;
- sub-frame optical simulation;
- higher-rate sensor sampling;
- matched-filter code detection plus a separately sampled frequency estimator.

Test primary and decoy signatures at the actual configured FPS, not only using static lists of bits.

## 6. Stage-2 temporal identity classifier

### Current behavior

The repository contains a GRU adapter that consumes either an 11-feature sequence or a 139-feature sequence. The shipped ONNX identity model expects the 11-feature layout. [[8]](https://github.com/thisIsRajbirMajhi/PAT_SIM/blob/feature/ai-primary-target-identification/src/fsoc_tracker/ai/identity_model.py) [[9]](https://github.com/thisIsRajbirMajhi/PAT_SIM/blob/feature/ai-primary-target-identification/src/fsoc_tracker/ai/features.py)

### Problems

- The model’s training/evaluation set is very small.
- The committed evaluation reports excellent identity metrics on only a handful of sequences.
- Inference behavior is not stable enough to confirm primary identity consistently when the ONNX model is manually wired.
- The 139-dimensional path does not clearly populate the CNN embedding from the current track state.
- The model input contract is selected dynamically, which hides training/runtime mismatches.

### Fix

Standardize one runtime contract. Prefer the 11-feature model until appearance embeddings are explicitly stored on every observation. Persist:

```
model input dimension
sequence length
feature normalization version
training data version
model commit/version
```

Reject incompatible model files before the run starts.

## 7. Identity state machine

### Current behavior

`IdentityStateMachine` supports per-track states including `CANDIDATE_FOUND`, `IDENTITY_CHECKING`, `PRIMARY_CONFIRMED`, `DECOY_CONFIRMED`, and `UNKNOWN`. It requires consecutive high-probability frames before confirmation. [[10]](https://github.com/thisIsRajbirMajhi/PAT_SIM/blob/feature/ai-primary-target-identification/src/fsoc_tracker/tracking/identity_state_machine.py)

### What works

- Primary confirmation is not immediate.
- Low-confidence evidence can remain unknown or checking.
- State is tracked per candidate rather than globally.

### Problems

- The state machine receives unstable heuristic/model probabilities.
- The GUI has its own confirmation flow in addition to the central pipeline confirmation logic.
- Confirmation counters can diverge between the two paths.
- A wrong-signature decoy often remains checking rather than becoming rejected.

### Fix

Use exactly one confirmation authority. Return a typed result containing:

```
track_id
primary_probability
decoy_probability
unknown_probability
identity_state
consecutive_primary_frames
consecutive_decoy_frames
evidence_summary
fallback_triggered
model_version
```

## 8. AI-to-EKF/IMM integration

### Current behavior

The AI path selects a confirmed primary candidate and passes it into the existing tracker. The estimate then drives the controller. This gives the system a useful safety boundary: an unconfirmed candidate does not receive full PID control. [[11]](https://github.com/thisIsRajbirMajhi/PAT_SIM/blob/feature/ai-primary-target-identification/src/fsoc_tracker/ui/app.py) [[12]](https://github.com/thisIsRajbirMajhi/PAT_SIM/blob/feature/ai-primary-target-identification/src/fsoc_tracker/tracking/tracker.py)

### Problems

The design documents promise confidence-aware covariance and AI-assisted IMM model selection, but the runtime integration is limited:

- AI confidence is not consistently converted into measurement covariance.
- AI does not directly update IMM model probabilities.
- The track manager receives the previous IMM innovation and probabilities before the current tracker update.
- The central AI pipeline says it should increase uncertainty on failure, but the GUI bypass path does not consistently apply that behavior.

### Fix

Define an explicit interface:

```python
MeasurementEvidence(
    centroid_px,
    measurement_quality,
    identity_state,
    identity_confidence,
    innovation_gate_hint,
    fallback_triggered,
)
```

Then make the tracker apply a documented policy:

```
high quality + confirmed primary → nominal R
low quality + checking           → inflated R
unknown or fallback              → high R / prediction-dominant
rejected decoy                   → no measurement update
```

AI should suggest IMM behavior but must not bypass the IMM’s own likelihood calculation.

## 9. PID and search control gating

### Current behavior

The controller uses full PID only when the global tracking state is locked. Candidate and acquiring states use reduced control, while searching and reacquiring use a separate spiral search controller. It also includes saturation, slew-rate limiting, integral decay, and anti-windup behavior. [[13]](https://github.com/thisIsRajbirMajhi/PAT_SIM/blob/feature/ai-primary-target-identification/src/fsoc_tracker/control/camera_controller.py)

### Assessment

This is one of the safer parts of the architecture. The intended rule that only confirmed primary identity should receive full tracking control is present in the GUI path.

### Remaining problems

- Search coverage is not sufficient.
- The AI timeout/fallback path is not centralized.
- Identity and tracking state can be represented by different state machines.
- Controller behavior is not validated against false primary and wrong-signature cases.

### Fix

Make the controller consume a single `ControlAuthority` value:

```
FULL_TRACKING
BOUNDED_CANDIDATE_MOTION
PREDICTION_ONLY
SEARCH
STOP
```

Derive it from the identity/tracking result rather than manually mapping states in the UI.

## 10. Failure and timeout handling

### Expected goal

If candidate or identity inference fails:

1. Never confirm primary.
2. Inflate measurement uncertainty.
3. Freeze or decay PID integral.
4. Reduce control authority.
5. Continue bounded search or prediction.
6. Record the failure, stage, model, and latency.

### Current problem

`AIInferencePipeline` contains a fallback design, but the GUI manually runs the stages and handles exceptions locally. This makes the documented failure behavior inconsistent. A fallback result can be created without guaranteeing that uncertainty, controller authority, and logging are updated together. [[14]](https://github.com/thisIsRajbirMajhi/PAT_SIM/blob/feature/ai-primary-target-identification/src/fsoc_tracker/ai/inference.py) [[11]](https://github.com/thisIsRajbirMajhi/PAT_SIM/blob/feature/ai-primary-target-identification/src/fsoc_tracker/ui/app.py)

### Fix

Return a typed failure result and process it in exactly one place. Add tests for:

- missing ONNX runtime;
- missing model file;
- malformed model;
- inference timeout;
- classifier exception;
- partial candidate failure;
- identity failure after a confirmed primary.

## 11. Evaluation and training pipeline

### Current behavior

Training scripts, datasets, ONNX artifacts, manifests, and evaluation reports exist. However, the evaluator contains explicit placeholder values and can fall back to manifest labels if the identity model is missing. [[15]](https://github.com/thisIsRajbirMajhi/PAT_SIM/blob/feature/ai-primary-target-identification/scripts/evaluate_ai_models.py) [[16]](https://github.com/thisIsRajbirMajhi/PAT_SIM/blob/feature/ai-primary-target-identification/models/identity_classifier/train_summary.json)

### Why this is not sufficient

A model evaluation must prove that the model, not the dataset labels or a proxy score, produced the result. Current reported perfect identity metrics are based on very small validation/test sequence counts and should not be treated as production evidence.

### Fix

Require the evaluation command to:

- load the actual model;
- run predictions on the selected split;
- calculate predictions from logits;
- refuse to evaluate if the model is missing;
- calculate confusion matrices and false-lock rate;
- calculate ECE from actual probabilities;
- measure actual latency on the target runtime;
- perform real ablations;
- report scenario and seed breakdowns;
- save the exact model/config/data hashes.

## 12. Recommended target architecture after fixes

```
FrameSource
    ↓
Preprocess + detector
    ↓
Candidate[]
    ↓
Candidate classifier
    ↓
Track association
    ↓
TrackSequence[]
    ↓
Identity classifier + optical signature matcher
    ↓
Identity decision authority
    ├── PRIMARY_CONFIRMED
    ├── DECOY_CONFIRMED
    ├── UNKNOWN
    └── IDENTITY_CHECKING
    ↓
Measurement evidence adapter
    ↓
EKF/IMM
    ↓
Control authority gate
    ├── Full PID
    ├── Bounded candidate motion
    ├── Prediction-only
    └── Search controller
    ↓
Camera update + UI snapshot + metrics/event log
```

The UI should never independently decide identity, update the filter, or change controller authority. It should display read-only snapshots.

## Acceptance criteria for a working AI pipeline

The pipeline should not be considered complete until all of the following are true:

- [ ]  Primary plus configured decoys are physically rendered.
- [ ]  Every visible candidate gets a stable track ID.
- [ ]  Crossing candidates do not cause unacceptable identity switches.
- [ ]  Heuristic mode is explicitly labeled and does not claim learned-model results.
- [ ]  Learned model mode validates both model paths before running.
- [ ]  Candidate model predictions are generated by actual model inference.
- [ ]  Identity model predictions are generated by actual model inference.
- [ ]  Primary confirmation requires N consecutive frames.
- [ ]  Decoy confirmation requires N consecutive frames.
- [ ]  Wrong signatures do not become primary.
- [ ]  Unknown evidence remains unknown instead of being forced into a class.
- [ ]  AI failures increase uncertainty and reduce control authority.
- [ ]  Only `PRIMARY_CONFIRMED` can authorize full PID.
- [ ]  EKF/IMM uses confidence-aware measurement covariance.
- [ ]  Search and re-acquisition use simulation-time limits.
- [ ]  Metrics distinguish source FPS, processing FPS, lock, measurement validity, and ground-truth availability.
- [ ]  MP4 accuracy reports `N/A` when annotations are unavailable.
- [ ]  Evaluation contains no hardcoded metrics or label-copy fallback.
- [ ]  GUI and headless paths execute the same AI orchestrator.
- [ ]  The final report includes false-lock rate, decoy rejection, identity switches, time-to-identify, unknown rate, and model latency.

## Fix priority

### P0 — Must fix first

1. Render configured decoys.
2. Make search coverage and acquisition behavior measurable and compliant.
3. Replace wall-clock acquisition metrics with simulation-time metrics.

### P1 — Must fix before claiming AI success

1. Unify GUI and headless AI execution.
2. Repair heuristic decoy classification.
3. Correct blink/frequency sampling.
4. Rebuild EKF/IMM after configuration changes.
5. Implement confidence-aware AI-to-filter integration.
6. Replace placeholder AI evaluation.
7. Make MP4 accuracy and model availability explicit.

### P2 — Release hardening

1. Split classical, inference, and training dependencies.
2. Resolve model paths robustly.
3. Add failure-injection tests.
4. Add multi-target crossing and occlusion tests.
5. Add CI coverage for heuristic and learned modes.
6. Make documentation match actual runtime and export commands.

## Final conclusion

The AI pipeline is **architecturally present but behaviorally incomplete**. The deterministic detector, tracker, and controller can work well when a target is already visible, and the state-machine safety concept is sound. The pipeline does not yet prove reliable primary-vs-decoy identification under the scenarios it claims to support.

The next goal should be a trustworthy end-to-end identity benchmark, not a larger neural network. First make the scene, state transitions, timing, confidence propagation, fallback behavior, and evaluation honest. Then use the resulting benchmark to decide whether the learned candidate and GRU models actually improve false-lock rate and decoy rejection over the classical baseline.