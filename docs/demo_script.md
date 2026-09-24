# Demo Script — FSOC Virtual Camera Tracking PAT Simulator

> **Duration:** 3-5 minutes (180-300 s) | **Audience:** Evaluator / competition judge
> **Goal:** Prove in one sweep that mandatory PAT functionality works, is measurable and re-acquires within spec, on both synthetic and benchmark video, with automatic logs.

---

## 1. Demo Flow Overview (Timeboxed)

| Phase | Wall Time | What to Show | Proves |
|-------|-----------|-------------|--------|
| 1. Problem in one sentence | 0:00-0:15 | FSOC beam is narrow; coarse PAT must find-centre-follow a beacon under disturbance | Understanding |
| 2. Clean baseline lock | 0:15-0:55 | SYNTHETIC straight/circular, acq < 2 s, visible overlays | Mandatory baseline |
| 3. Live metrics explain | 0:55-1:20 | Dashboard: RMSE, reacq, lock %, IMM probs, FPS pass/fail | Measurability |
| 4. High-noise robustness | 1:20-2:10 | Switch to High Noise preset (jitter 8, Gaussian 14, S&P 0.04 + haze + random) — lock retained, RMSE < 10 | Robustness |
| 5. Forced loss & reacq | 2:10-2:50 | Trigger loss (pause/random or occlude), show spiral search, re-lock <= 1 s timer | Re-acquisition spec |
| 6. Benchmark video (MP4) | 2:50-3:30 | Load `.mp4` @30fps, show same pipeline without PTZ | Benchmark Performance-2 |
| 7. Export report | 3:30-3:55 | EXPORT REPORT -> open `summary_report.html` and `config_used.yaml` | Automatic logging |
| 8. Architecture & AI (Q&A) | 3:55-4:30 | Diagram: Detector -> IMM-EKF (CV/CA/MN) -> PID -> search | Design, AI contribution |
| 9. Close | 4:30-5:00 | Hardware-in-the-loop as next step | Roadmap |

If time is 3 min, compress 3 and 8; if 5 min, linger in phases 4-6.

---

## 2. Pre-Demo Checklist

- [ ] Machine at 640x480, 30 Hz, connected to a projector that shows both Camera FOV and World FOV.
- [ ] `python -m fsoc_tracker.main` launches without error; top bar shows `SYNTHETIC | Seed 42 | IDLE | FPS --`.
- [ ] `configs/default.yaml` and `configs/high_noise.yaml` present.
- [ ] A sample benchmark video at `data/sample.mp4` (or any H.264 30 fps clip) copied locally — path without spaces.
- [ ] A previous `outputs/runs/` example kept aside to show report layout if export runs long.
- [ ] Audio of system level muted (no surprise notifications).
- [ ] Projector resolution allows at least 1280x800 so both viewports are sharp; if using `launch.py`, no firewall prompt.

Rehearse the exact slider values: Clean `circular r=180 speed 2.8`; High Noise `random 4.5 + gaussian 14 + S&P 0.04 + jitter 8 + haze 0.35 + platform linear 4`. Transitions should be Apply -> RUN without typing.

---

## 3. Phase-by-Phase Narrative and Operator Actions

### Phase 1 — Problem Statement (0:00-0:15)

**Say:**

> "Free-Space Optical Communication offers very high data rates without spectrum licensing, but the beam is only a few degrees wide — a few pixels of error breaks the link. This simulator solves the **coarse PAT** problem: it must find, centre and keep a moving beacon in view while the platform, camera and atmosphere fight it — and do so measurably enough to pass acquisition under 2 s, re-acquisition under 1 s, tracking error under 10 px and loss under 5 %."

**Show:** Title bar `FSOC Virtual Camera Tracking PAT Simulator v1.0.0` with `SYNTHETIC` badge — gesture at top bar.

### Phase 2 — Clean Baseline Lock (0:15-0:55) — 40 s

**Objective:** Acquire and track visibly within spec on the simplest scenario.

**Operator actions:**

1. Point at Camera FOV and World FOV labels so the judge registers what each screen means.
2. Click **CONTROL DECK** -> Presets tab -> select **Clean Baseline** -> **Apply**. Seed shows `42`.
3. Confirm Target tab reads `circular, r=180, speed 2.8` and Camera tab `640x480 | FOV 4 deg x 3 deg | 30 fps`; close drawer (or leave open — judge should see it).
4. Click **RUN**.

**Say while it runs (10-20 s):**

> "The left pane is exactly what the sensor sees — 640x480 at 30 Hz. The cross is the image centre; yellow is the raw detector centroid and bounding box — the intensity-weighted centroid — green/cyan is the fused IMM-EKF estimate, and the line is the error vector. On the right is the full 2000x2000 world: the yellow trail is the beacon's true path, the cyan rectangle is the camera footprint — you're watching the camera slew to centre the error."

**Point at:**

- Detector snapping to the beacon within a few frames.
- Cyan footprint drifting to overlay the yellow trail.
- Dashboard state: `CANDIDATE -> ACQUIRING -> LOCKED` (green), acquisition timer counting. Announce when it passes: e.g., "Locked in 0.7 s — inside the 2 s limit."

### Phase 3 — Live Metrics Explain (0:55-1:20) — 25 s

Leave Clean Baseline running. Gesture across Dashboard cards left-to-right.

**Say:**

> "Every number on the bottom is the same number that goes into the automatic report — single source of truth. Accuracy shows mean 2.4, RMSE 3.1 — limit is 10 px. Timing shows processing 29 fps against the 20 fps minimum. Lock retention 99 %, loss 0 %. The three bars are the IMM motion-model probabilities — CV, CA and manoeuvre — the tracker is learning which motion it believes each frame; on this smooth circle you see CV dominant. The controller card shows pan and tilt commands and whether they saturated — here, no."

**Point at:** `RMSE 3.1 / 10 px` and `FPS 29 / 20` turning green; IMM bars stable.

### Phase 4 — High Noise Robustness (1:20-2:10) — 50 s

**Objective:** Show lock is retained under the combined benchmark disturbances — the key differentiator.

**Operator actions:**

1. Leave the clean run visible for 2 s, then click **CONTROL DECK** -> rename to **High Noise** (or load `configs/high_noise.yaml` preset) -> point at the slider summary: `Gaussian 14, S&P 0.04, Poisson on, jitter 8, haze 0.35, random 4.5, linear platform 4` -> **Apply**.
2. The frame visibly degrades (grain + haze veil). Click **RESET** so the new random trajectory starts under the new noise with seed 42 (or seed 43 to show a variant).
3. Click **RUN** again.

**Say:**

> "Same pipeline — no parameter trickery beyond what you see. We've added Gaussian noise at std 14 — near the max 20 — salt-and-pepper at 4 %, Poisson, camera jitter of 8 px per frame, haze at 0.35 and swapped the smooth circle for a random walk at 4.5 px/frame with platform drift. The raw image is ugly now, but watch — acquisition still under a second, RMSE stays around 6 to 7 px inside the 10 px limit, loss under 2 %. That gap between 6.8 and 10 is the margin we left for the benchmark's unknown clips. The tracker stayed in LOCKED; the IMM's manoeuvre bar rises when the target jogs — you can see it adapt in real time."

**Point at:**

- Degraded Camera FOV still detecting reliably (yellow bbox stable, confidence dip to ~0.7-0.85 but not collapse).
- Dashboard: RMSE still green despite visibly worse image; IMM MN bar now active.
- No manual retuning needed — adaptive threshold `bg + k*noise` and prediction gating handle it.

If time permits, momentarily drag `jitter_px` from 8 to 16 live to show degradation then revert, emphasizing the operating boundary.

### Phase 5 — Forced Loss and Re-acquisition (2:10-2:50) — 40 s

**Objective:** Prove the <= 1 s re-acquisition spec with a visible search behaviour.

**Operator actions:**

1. While High Noise is locked, trigger a loss. Two reliable options:
   - **Option A (recommended):** Click **PAUSE** for 1 s, change Target tab to `random` (if not already) or `circular` with speed `10`, click **Apply** -> **RUN** — queue a sudden direction/speed change the tracker hasn't converged on; or
   - **Option B:** Speed up `speed_px_per_frame` to `10` at `jitter 12` for 2 s, then revert — the beacon will exit the FOV briefly and the World FOV will show the footprint lagging.
2. Watch state go `LOCKED -> TEMP_LOST -> REACQUIRING` (amber/blue) and hear no beep — the camera footprint spirals (dashed cyan spiral on World FOV).
3. Point at the Dashboard **Re-acquisition** timer as it counts and then stops when `LOCKED` returns. Aim to narrate the value.

**Say:**

> "We've forced a loss — beacon left the FOV. The state machine declares TEMP_LOST then REACQUIRING and the controller stops chasing with PID and switches to an expanding spiral search — that's the faint cyan spiral on the right. We measure re-acquisition from loss declaration to stable lock — five consecutive valid detections. Watch the timer... re-locked in 0.5 s — inside the 1 s limit. PID integral was frozen during loss so there's no overshoot; it decays 4 % per frame until the new lock settles."

**Point at:**

- `TEMP_LOST` -> `REACQUIRING` -> `LOCKED` transition in top bar and card.
- Cyan spiral expanding then collapsing.
- `Re-acq 0.5 / 1.0 s` turning green.

If the loss doesn't happen (random sometimes cooperates), manually drag `platform speed` to `12` for 2 s — the distortion will force it.

### Phase 6 — Benchmark Video Mode (2:50-3:30) — 40 s

**Objective:** Prove Benchmark Performance-2 — `.mp4` at 30 fps through the same pipeline.

**Operator actions:**

1. Click **PAUSE** (or let the run finish).
2. Open Control Deck -> **Input/Logging** tab.
3. Switch Input Mode **SYNTHETIC -> VIDEO**. Click **Browse** -> select `data/sample.mp4` (or `benchmark.mp4`). Confirm the path.
4. Note that Camera tab and `max_pan/tilt` remain visible but are not actuating (PTZ is bypassed); say so.
5. Click **Apply** -> **RUN**.

**Say:**

> "Now we swap to the evaluator's case — a complete-screen `.mp4` at 30 fps containing its own noise and moving beacon. The virtual pan-tilt camera is bypassed — we decode frames directly into the same bright-spot detector and IMM-EKF pipeline that just handled synthetic. No new code path, no retuning. You see input FPS 30.0 and processing FPS 28 — both above the 20 minimum — lock still reports, error still reports, and the frame order is preserved. This is why synthetic-to-video can't hide detector failures — the metric is the same."

**Point at:**

- Camera FOV now plays decoded video (no cyan footprint lag — it's direct; World FOV may blank or show a debug overlay).
- Dashboard still shows `ACQUIRING/LOCKED`, `Valid det %`, `RMSE` and `FPS`.
- Input path in top bar changing to `MP4: sample.mp4`.

### Phase 7 — Export Report (3:30-3:55) — 25 s

**Operator actions:**

1. Click **EXPORT REPORT** (bottom bar).
2. Wait for the toast `Saved to outputs/runs/<timestamp>_<traj>_seedN`.
3. Open the folder in Explorer/file manager. Open `summary_report.html` in the default browser. Also open `config_used.yaml` beside it.

**Say:**

> "Everything you saw live is already saved — no manual copying. This folder is the run's evidence. The YAML is the exact fully-resolved configuration plus seed — running it again replays the same trajectory and noise. The CSV has one row per frame with error, state, confidence and per-frame FPS. The HTML is the human summary — duration, input vs processing FPS, acquisition and reacq times, RMSE/mean/max/P95, lock retention and loss percentage — all against the limits. The JSON is what an auto-grader would read. Ground truth was only used here in the evaluator — the detector never saw it."

**Point at:**

- `config_used.yaml` showing `seed: 42` and disturbance values matching the demo.
- `summary_report.html` green `PASS` badges next to `RMSE 6.8 / 10 px` and `Acq 0.9 / 2.0 s`.
- Optional: `frame_metrics.csv` row count matching `total_frames`.

### Phase 8 — Architecture and AI Talking Points (3:55-4:30) — 35 s (overlaps Q&A tail)

If the judge asks "what did you build?", use this 30 s answer without replaying the video:

**Say:**

> "The core is a hybrid: a fast adaptive bright-spot detector — `background + k*noise` threshold with prediction gating — supplies measurements to an Extended Kalman Filter that estimates the angular state via a tangent projection, because the camera model is nonlinear near the edges. Three EKFs in an Interacting Multiple Model compete — constant-velocity, constant-acceleration and high-noise manoeuvre — and the IMM learns which to trust each frame from its innovation likelihood. A PID with deadzone, anti-windup and feed-forward turns the fused angular error into bounded pan-tilt rates; a separate spiral search guarantees re-acquisition within a second. All configuration is in YAML, every experiment is seed-replayable, and both synthetic and `.mp4` share one detector-to-metrics pipeline — so the benchmark can't be gamed. The expensive part is connected components on 640x480; EKF/IMM/PID are microseconds — hence 28-29 fps."

Have ready the whiteboard diagram: `Frame -> Detector -> IMM-EKF -> StateMachine -> PID (+search) -> VirtualCamera -> Frame`, with the evaluator-only `GroundTruth -> Metrics` branch dashed.

### Phase 9 — Close (4:30-5:00) — 30 s

**Say:**

> "Clean baseline proved the loop locks. High noise proved it stays locked within the 10 px / 5 % envelope under the benchmark's combined disturbances — with live IMM adaptivity as the explanation. Loss proved the state machine and spiral search recover inside a second. Video proved the same pipeline handles the external 30 fps case without code forking. Logs proved everything is automatic and replayable. Next is hardware-in-the-loop — real pan-tilt encoders and a camera feeding the existing `FrameSource` and `CameraController` contracts — because the software interfaces already exist."

Thank the audience. Leave the exported `summary_report.html` and `config_used.yaml` on screen.

---

## 4. Fallback and Timing Variant

| If ... | Then ... |
|--------|----------|
| Projector hides World FOV | Spend 10 s extra on phase 2 pointing at Camera FOV only; skip platform path commentary |
| Video codec fails on evaluator machine | Have a second `.mp4` (1280x720 H.264) and a clean 640x480 fallback on a USB path without spaces |
| High Noise doesn't lose cleanly | Drive it artificially: `speed 12 + jitter 12` for 2 s — that guarantees exit; reset before moving to VIDEO |
| FPS dips on weak projector laptop | Disable Poisson, reduce resolution to 640x480 if on 1280x720; mention that detector is O(W*H) |
| Over time | Skip phase 8 detail; collapse 3 into phase 2 (point at Dashboard during first lock); still fit 3 min |
| Under time (5 min) | Linger in phase 4; show `threshold_k` 3.0 -> 2.0 live to demonstrate threshold sensitivity; open `frame_metrics.csv` plot in `pyqtgraph` |

---

## 5. Judge Q&A Preparation

| Question | Answer |
|----------|--------|
| Why not deep learning? | Bright-spot on 640x480 is classical-fast and explainable; learned detector is a 2 ms drop-in for candidate scoring and was avoided as default to prevent synthetic->video domain gap. IMM *is* the AI — adaptive model selection from innovation likelihood. |
| How to guarantee 1 s reacq? | Separate spiral search, not PID, triggered by explicit state machine (TEMP_LOST 1-15, REACQUIRING 16-30). Covers FOV in ~1 s without overshoot; PID integral decays 4 %/frame during loss. |
| How do you know the detector works? | Per-frame `frame_metrics.csv` with detector `valid/confidence` vs evaluator truth only in `MetricsCollector`; `Detection.valid` alone gates lock counting — prediction never hides persistent failure. |
| What breaks your system? | Fog >0.6 + Gaussian 20 + jitter 20 dims the beacon below threshold — correctly reported as search, not hidden. Beyond `~11 px/frame` the `max_pan=5 deg/s` slew limit is physical. |
| Reproducibility? | Seed 42 plus `config_used.yaml` fully determines trajectories, noise and stars; replay via Benchmark Dialog or `python benchmark` with same YAML produces byte-identical logs. |
| FPS headroom? | Detector ~6 ms, EKF/IMM/PID ~0.2 ms total -> 28-29 FPS typical. Larger resolution scales detector linearly; EKF flat. |

---

## 6. Post-Demo Deliverables Checklist (hand over)

- [ ] The running application (or installed exe) in the demo window.
- [ ] The exported `outputs/runs/<timestamp>_<traj>_seedN/` folder with `config_used.yaml`, `summary_report.html` and `frame_metrics.csv` on screen.
- [ ] `docs/` folder (architecture, algorithms, configuration, testing, technical_report, user_manual, this script).
- [ ] `configs/default.yaml` and `configs/high_noise.yaml` showing the two presets used.
- [ ] Optional 3-5 min screen recording of the same flow (as `data/demo_recording.mp4`, not in git if large).

---

*Rehearse phases 2-7 once without speaking, then once with timing. The single most convincing sentence is: "This HTML is the run we just watched — regeneration with the same YAML and seed reproduces it."*
