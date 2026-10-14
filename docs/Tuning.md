# SIH FSOC Coarse-Alignment — Parameter Contract

**Single source of truth for what's fixed, what's tunable, and how tuning is governed.**
Consolidates `Hardware_Constraints.md` + `Tuning Parameters.txt`.
Locked: **2026‑10‑14**. Defaults: `src/pat_common/config/sections/*.py`. Limits: `template.py:42–76`.

---

## 0. TL;DR

| Bucket | Count | Owner | Rule |
|---|---|---|---|
| §1 Hard walls | 18 | Spec | **Never touched** — a config that needs these changed is rejected |
| §2 Test conditions | 7 groups | Suite | **Never tuned** — tuning these cheats the benchmark |
| §3 Tunable knobs | 33 (5 groups A–E) | Optuna | **Must be tuned** — every winner ships tuned on all 80 cases |

Any "winner" that requires a §1 or §2 change to pass is **rejected**, no exceptions.

---

## 1. HARD WALLS — NOT CONFIGURABLE

Fixed by spec. Never tuned. Enforced by `--config` filter; values below/outside these are rejected before a candidate is scored.

### 1.1 Sensor & loop rates (floors)

| Parameter | Value | Role |
|---|---|---|
| Camera update rate (`fps`) | **= 30 Hz** | Sensor frame rate — pinned, not a range |
| Update interval (`update_interval_hz`) | **≥ 20 Hz** | Gimbal command-loop floor |

### 1.2 Actuator envelope (gimbal)

| Parameter | Value | Role |
|---|---|---|
| Max pan speed | **5 – 10 °/s** | Actuator ceiling (default 5) |
| Max tilt speed | **5 – 10 °/s** | Actuator ceiling (default 5) |
| Min pan / tilt speed floor | **5 °/s** | Actuator floor |

### 1.3 Disturbance ceilings (test-condition max)

| Parameter | Value | Role |
|---|---|---|
| Max noise std-dev | **≤ 20 px** | Sensor + atmosphere budget |
| Max camera jitter | **≤ ± 20 px / frame** | Vibration envelope |
| Max platform motion | **≤ ± 20 px / frame** | Platform dynamics budget |

### 1.4 Rendering & optics

| Parameter | Value | Role |
|---|---|---|
| Screen size | **≥ 2000 × 2000 px** | Rendering floor |
| Camera FOV (`fov_deg`) | **[4, 3]°** | Fixed hardware |
| Camera resolution | **640 × 480** | Fixed hardware |

### 1.5 Mandatory initial condition

| Parameter | Value | Notes |
|---|---|---|
| Camera initial position | **Centre of screen** | Default. Tuned start pose allowed only via winner `--config`, applied **after** `enforce_far_start` (`headless.py:467`); target stays far-corner. |
| Target type | **Beacon spot** | Mandatory; target group as a whole is §2 (never tuned) |

### 1.6 Acceptance thresholds (judged, never tuned)

| Parameter | Value |
|---|---|
| Acquisition time | **≤ 2 s** |
| Tracking error | **≤ 10 px** |
| Target loss | **< 5 %** |
| Re-acquisition time | **≤ 1 s** |
| Processing speed | **≥ 20 FPS** |

> Changing any acceptance threshold to make a run pass is **cheating** and auto-rejects the winner.

---

## 2. TEST CONDITIONS — NEVER TUNED

These are inputs the suite varies; the tuner must **never** move them. Doing so "cheats the suite" and invalidates the verdict.

| Group | What it controls |
|---|---|
| **Target** | Shape, size, count, trajectory, speed, blink, visibility schedule |
| **Noise** | Gaussian, salt & pepper, Poisson |
| **Atmosphere** | Clear / haze / fog / rain / low-light + strength |
| **Platform** | Linear / circular / random / spiral / fig-8 + speed |
| **Environment / stars** | Density, brightness, vignetting, gradient, twinkle |
| **World** | Size, background, corners |
| **Seed** | Per-case seed (fuzz varies this; tuner does not) |

Rule: if you find yourself editing `target`, `noise`, `atmosphere`, `platform`, `environment`, `world`, or `seed` to improve a score → stop. That's outside the tuning contract.

---

## 3. TUNABLE KNOBS — MUST TUNE (Optuna owns these)

**33 parameters across 5 groups A–E.** No winner ships without every group tuned and validated on the full **80-case suite**.

### Group A — Camera Start (4)

*Applied post‑`enforce_far_start` so tuned starts survive.*

| # | Parameter | Config key | Default | Range |
|---|---|---|---|---|
| 1 | Initial Camera Position | `initial_position` | `centre` | `centre` \| `user-defined` |
| 2 | Initial Pan Angle | `initial_pan` | 0.0° | ± 8° |
| 3 | Initial Tilt Angle | `initial_tilt` | 0.0° | ± 8° |
| 4 | Update Interval | `update_interval_hz` | 30 Hz | 20 – 60 (floor ≥ 20) |

### Group B — Detector (3)

*Detection front-end; biggest lock-acquisition lever.*

| # | Parameter | Config key | Default | Range |
|---|---|---|---|---|
| 5 | Threshold K | `threshold_k` | 3.0 | 2.0 – 5.0 |
| 6 | Min Area | `min_area` | 8 | 4 – 16 |
| 7 | Max Area | `max_area` | 900 | 400 – 1500 |

### Group C — Tracker / EKF (5)

*Estimation accuracy, outlier rejection, loss / re‑acquisition behaviour.*

| # | Parameter | Config key | Default | Range |
|---|---|---|---|---|
| 8 | Process Noise | `process_noise` | 0.8 | 0.1 – 5.0 |
| 9 | Meas Noise | `meas_noise` | 4.0 | 0.5 – 10.0 |
| 10 | Gate Sigma | `gate_sigma` | 5.0 | 3.0 – 8.0 |
| 11 | Lost Timeout | `lost_timeout_frames` | 15 | 5 – 30 |
| 12 | Reacq Timeout | `reacq_timeout_frames` | 30 | 10 – 60 |

### Group D — Controller PID (7)

*Tracking response, steady-state error, overshoot.*

| # | Parameter | Config key | Default | Range |
|---|---|---|---|---|
| 13 | KP Pan | `kp_pan` | 1.2 | 0.1 – 5.0 |
| 14 | KP Tilt | `kp_tilt` | 1.2 | 0.1 – 5.0 |
| 15 | KI | `ki` | 0.05 | 0 – 1.0 |
| 16 | KD | `kd` | 0.15 | 0 – 2.0 |
| 17 | Deadzone PX | `deadzone_px` | 2.0 | 0 – 6.0 |
| 18 | Integral Limit | `integral_limit` | 8.0 | 2 – 20 |
| 19 | Feedforward Gain | `feedforward_gain` | 0.0 | 0 – 2.0 |

### Group E — Search & Intercept Policy (14)

*Re-acquisition after dropout / crowded / blink cases; decides HARD-case verdicts.*

| # | Parameter | Config key | Default | Range |
|---|---|---|---|---|
| 20 | Search Angle Step | `search_angle_step` | 0.45 | 0.05 – 1.0 |
| 21 | Search Radius Step | `search_radius_step` | 0.09 | 0.01 – 0.5 |
| 22 | Search Radius Max | `search_radius_max` | 4.5 | 2.0 – 8.0 |
| 23 | Search Rate Scale | `search_rate_scale` | 0.85 | 0.3 – 1.5 |
| 24 | Spiral Phase S | `spiral_phase_s` | 3.0 | 1 – 8 |
| 25 | Raster Pan Scale | `raster_pan_scale` | 0.9 | 0.3 – 1.0 |
| 26 | Raster Tilt Scale | `raster_tilt_scale` | 0.35 | 0.3 – 1.0 |
| 27 | Stare Scale | `stare_rate_scale` | 0.3 | 0.1 – 0.8 |
| 28 | Intercept Gain | `intercept_gain` | 2.0 | 0.5 – 5.0 |
| 29 | Intercept Lead S | `intercept_lead_s` | 0.3 | 0 – 0.8 |
| 30 | Uncertainty Scale | `unc_scale` | 0.6 | 0 – 2.0 |
| 31 | Uncertainty Max Boost | `unc_max_boost` | 2.5 | 1 – 4 |
| 32 | Fast Velocity | `fast_vel_deg_s` | 1.0 | 0.2 – 5.0 |
| 33 | Give Up Frames | `give_up_frames` | 600 | 120 – 1800 |

---

## 4. TUNING ORDER — STAGED

**~33 dims is too many to tune flat.** `tune.py` runs three stages sequentially; each stage starts from the previous stage's winner.

| Stage | Scope | Parameters | Rationale |
|---|---|---|---|
| **Stage 1 — Core** | B + C(8,9) + D(13–17) | Detector + EKF noises + PID + deadzone | Front-end + control loop; dominates acquisition & tracking on far-start cases |
| **Stage 2 — Policy** | E + C(11,12) | Search & intercept + loss / reacq timeouts | Handles dropout / crowded / blink cases and decides HARD verdicts |
| **Stage 3 — Polish** | Joint re-tune of winners' region (all A–E) | All 33 | Local refinement around Stage 1+2 optimum |

---

## 5. TUNING RULES (binding on `tune.py`)

1. **Staged, never flat.** Stage 1 → Stage 2 → Stage 3 polish. Never all ~33 at once.
2. **Rate floors enforced.** `update_interval_hz ≥ 20`, `fps = 30` always. Winner values below the floor are rejected by the `--config` filter.
3. **Start overrides apply last.** Camera-start overrides run **after** `enforce_far_start` (`headless.py:467`); target stays at far-corner.
4. **Scoring = suite verdicts.** Every candidate is scored by `composite_loss` that mirrors benchmark gates. The loop runs until **full-suite 0 FAIL + 0 ERROR** or the user stops it.
5. **No benchmark, verdict, or §1 wall changes.** A "winner" needing those is auto-rejected.

---

## 6. QUICK REFERENCE — Where each knob lives

| Concern | Knob group | File |
|---|---|---|
| Loop rate, start pose | A | `sections/camera.py` |
| Detection threshold / area | B | `sections/detector.py` |
| EKF noise, gate, timeouts | C | `sections/tracker.py` |
| PID gains, deadzone, feedforward | D | `sections/controller.py` |
| Search pattern, intercept, give-up | E | `sections/controller.py` |
| Test conditions (never touch) | — | `headless.py` X/E/R defs |
| Hard walls (never touch) | — | spec §1 |

**One rule to remember:** *Category §1 you meet, §2 you leave alone, §3 you optimise — in that order, every time.*