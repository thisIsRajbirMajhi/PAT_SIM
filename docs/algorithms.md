# Algorithms — Tracking, AI and Control

> **Version:** 1.0.0 | **System:** FSOC Virtual Camera Tracking PAT Simulator

## 1. Overview

The PAT problem is a **closed-loop estimation-and-control problem**, not just detection. The pipeline is:

```
Frame -> BeaconDetector (measurement) -> IMM-EKF (estimation + model selection)
      -> StateMachine (SEARCH/LOCK/LOST) -> PID (+ search) (control)
      -> VirtualCamera (actuation) -> next Frame
```

Ground truth is evaluator-only. The detector, EKF, IMM and PID receive only image data and known camera state.

This document details each algorithmic component with equations, parameters, and annotated code snippets from `src/fsoc_tracker/`.

---

## 2. Beacon Detection — Adaptive Bright-Spot Detector

### 2.1 Rationale

The target is a **beacon spot**: a bright, localized source on a darker background. A classical detector is chosen over a heavy neural network because it is fast (< 10 ms), explainable, and has no training or GPU dependency. AI enhancement is reserved for candidate validation if needed, keeping the baseline measurable. (Implementation Plan section 7.1, 19-20)

### 2.2 Preprocessing

1. If frame is BGR (VIDEO mode, colour camera option Sr.2), convert to grayscale via `cv2.cvtColor`.
2. Small Gaussian blur `ksize=3` (configurable `blur_ksize`) to suppress single-pixel salt noise.

### 2.3 Adaptive Threshold

A fixed threshold fails under haze/fog/low-light. The detector estimates an adaptive threshold per frame:

```
bg    = median(image)                          # background intensity
noise = std(image)                              # noise level
p98   = percentile(image, 98)                   # bright percentile
threshold = max(bg + k*noise, p98 - 8, 120)    # k = threshold_k, default 3.0
threshold = clip(threshold, 80, 230)
```

- `k` (`threshold_k`) controls aggressiveness; higher `k` rejects more noise but may miss dim beacons.
- Clamping prevents threshold collapse in dark scenes or saturation in bright scenes.

### 2.4 Connected Components and Filtering

```python
# src/fsoc_tracker/perception/detector.py:36
_, binary = cv2.threshold(img, thresh_val, 255, cv2.THRESH_BINARY)
kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3,3))
binary = cv2.morphologyEx(binary, cv2.MORPH_OPEN, kernel, iterations=1)
num, labels, stats, centroids = cv2.connectedComponentsWithStats(binary, connectivity=8)
```

Per component filtering:

| Test | Bounds | Reason |
|------|--------|--------|
| Area | `min_area=8`, `max_area=900` | Reject noise fragments and large clutter |
| Aspect ratio | `max(w,h)/min(w,h) <= 3.5` | Reject elongated streaks (rain) |
| Fill | `area / bbox_area` | Compactness — low fill rejected implicitly via scoring |

### 2.5 Intensity-Weighted Centroid

For the surviving component with pixels `S` and intensities `I(x,y)`:

```
x_c = sum(I * x) / sum(I)
y_c = sum(I * y) / sum(I)
```

This is more accurate than bounding-box centre when the spot is blurred or noisy. The centroid is sub-pixel.

### 2.6 Candidate Scoring

Each valid candidate receives a composite score; the highest wins:

```python
# src/fsoc_tracker/perception/detector.py:66
brightness_score = (peak/255)*0.3 + (mean_int/255)*0.2
shape_score      = fill*0.2 + (1 - min(aspect-1,1))*0.1
prox_score       = max(0, 1 - dist/(max(W,H)*0.6))*0.2
score = brightness_score + shape_score + prox_score
if peak > 200: score += 0.15  # bright beacon bonus
```

`dist` is distance from **predicted position** (from IMM) if available, else from image centre. This prediction gating rejects salt-noise blobs far from the expected motion.

**Example:** Under salt-and-pepper `prob=0.04`, ~12k noise components survive the initial threshold, but only 2-3 pass area/aspect gates; the true beacon typically scores 0.85-0.95 vs noise 0.2-0.4.

### 2.7 Confidence and Output

```python
confidence = clip(0.35 + 0.65*score + (peak-180)/255*0.2, 0, 1)
return Detection(valid=True, centroid_px=(x_c, y_c), bbox=(x,y,w,h),
                 confidence=confidence, score=score, area=area)
```

If no candidate passes gates: `Detection(valid=False, confidence=0.0)`. The confidence modulates EKF measurement covariance (high conf -> smaller `R`, see section 3).

**Full detector snippet:**

```python
# src/fsoc_tracker/perception/detector.py:14
class BeaconDetector:
    def detect(self, frame_gray, predicted_pos=None) -> Detection:
        if len(frame_gray.shape) == 3:
            img = cv2.cvtColor(frame_gray, cv2.COLOR_BGR2GRAY)
        else:
            img = frame_gray
        if self.blur >= 3:
            k = self.blur if self.blur%2==1 else self.blur+1
            img = cv2.GaussianBlur(img, (k,k), 0)
        bg = float(np.median(img))
        noise = float(np.std(img)) + 1e-6
        p98 = float(np.percentile(img, 98))
        thresh_val = max(bg + self.k*noise, p98 - 8, 120)
        thresh_val = float(np.clip(thresh_val, 80, 230))
        _, binary = cv2.threshold(img, thresh_val, 255, cv2.THRESH_BINARY)
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3,3))
        binary = cv2.morphologyEx(binary, cv2.MORPH_OPEN, kernel, iterations=1)
        num, labels, stats, centroids = cv2.connectedComponentsWithStats(binary, connectivity=8)
        # ... scoring loop ...
        return Detection(valid=True, centroid_px=(cx_det, cy_det), ...)
```

### 2.8 Complexity

O(W*H) for threshold + morphology + connected components. On 640x480 this is ~5-8 ms on a modern CPU, well within the 30 Hz budget. No GPU required.

---

## 3. Extended Kalman Filter (EKF)

### 3.1 Why EKF

A standard Kalman filter suffices for pixel-space constant-velocity tracking, but the controller operates in **angular pan/tilt space** and the camera projection `angle -> pixel` is nonlinear (`tan`), especially near FOV edges (4 deg HFOV). EKF linearizes this projection via its Jacobian, giving correct angular estimates. (Implementation Plan section 21)

### 3.2 State Vector

A 6-state vector per model:

```
x = [alpha, beta, alpha_dot, beta_dot, alpha_ddot, beta_ddot]^T
    deg    deg    deg/s      deg/s     deg/s^2     deg/s^2
```

- `alpha, beta` — horizontal/vertical angular error of beacon relative to optical axis (desired value 0).
- Velocities and accelerations capture motion across trajectories.

### 3.3 Process Model

Constant-acceleration model with timestep `dt = 1/fps`:

```python
# src/fsoc_tracker/tracking/ekf.py:33
def _F(self, dt):
    F = np.eye(6)
    F[0,2]=dt; F[0,4]=0.5*dt*dt
    F[1,3]=dt; F[1,5]=0.5*dt*dt
    F[2,4]=dt
    F[3,5]=dt
    return F
```

So `alpha_{k+1} = alpha_k + alpha_dot*dt + 0.5*alpha_ddot*dt^2`, etc. Process noise `Q` is the continuous white-noise acceleration form (Implementation Plan section 22):

```python
# src/fsoc_tracker/tracking/ekf.py:42
def _Q(self, dt):
    q = self.Q_base  # 0.8 * scale
    Q[0,0]= dt4/4*q; Q[0,2]= dt3/2*q; Q[0,4]= dt2/2*q
    Q[1,1]= dt4/4*q; Q[1,3]= dt3/2*q; Q[1,5]= dt2/2*q
    # ... symmetrized + eps*I
```

Scales: CV 0.6 (low, smooth), CA 1.2 (moderate), MN 3.0 (high, responsive). Initial `P = diag([5,5,10,10,20,20])`.

### 3.4 Measurement Model (Nonlinear)

```
fx = (W/2) / tan(HFOV/2)      # focal length in px/rad
fy = (H/2) / tan(VFOV/2)
cx = W/2, cy = H/2

u = cx + fx * tan(alpha_rad)          # horizontal pixel
v = cy - fy * tan(beta_rad)           # vertical (inverted y)
z = h(x) = [u, v]^T
```

```python
# src/fsoc_tracker/tracking/ekf.py:62
def _h(self, x):
    alpha = math.radians(x[0]); beta = math.radians(x[1])
    u = self.cx + self.fx * math.tan(alpha)
    v = self.cy - self.fy * math.tan(beta)
    return np.array([u, v])

def _H(self, x):
    sec2_a = 1 / cos(alpha)^2; sec2_b = 1 / cos(beta)^2
    du_da = fx * sec2_a * pi/180
    dv_db = -fy * sec2_b * pi/180
    H = zeros((2,6)); H[0,0]=du_da; H[1,1]=dv_db
    return H
```

Near optical axis `du/da ~= fx * pi/180`, approximately linear; near edges `sec^2` captures tan curvature.

### 3.5 EKF Predict and Update Cycle

For each frame:

```
1. Predict: x_pred = F*x,  P_pred = F*P*F^T + Q
2. Predict measurement: z_pred = h(x_pred)
3. Innovation: y = z_meas - z_pred
4. Innovation covariance: S = H*P_pred*H^T + R(confidence)
5. NIS = y^T * S^{-1} * y   (normalized innovation squared)
6. If NIS > 28 (approx 5 sigma): reject measurement, inflate P slightly
7. Else: K = P_pred*H^T*S^{-1},  x = x_pred + K*y,  P = (I-KH)*P_pred
```

```python
# src/fsoc_tracker/tracking/ekf.py:84
def update(self, z_px, confidence=0.9):
    R = self.R * (1.5 - 0.8*confidence)  # high conf -> smaller R
    zpred = self._h(self.x)
    H = self._H(self.x)
    y = z - zpred
    S = H @ self.P @ H.T + R
    invS = np.linalg.inv(S)
    nis = float(y @ invS @ y)
    if nis > 28:
        self.P += np.eye(6)*0.8  # reject
        return self.x.copy(), nis
    K = self.P @ H.T @ invS
    self.x = self.x + K @ y
    self.P = (np.eye(6) - K @ H) @ self.P
    return self.x.copy(), nis
```

On missing detection (`z=None`): `P += 0.3*I` (covariance inflation, no correction), allowing prediction-only bridging for 1-3 frames.

Measurement noise `R = I * meas_noise^2` with default `meas_noise=4.0` px, scaled by confidence.

### 3.6 Example: Straight vs Random

On a straight trajectory at 3 px/frame, innovation stays < 4, NIS < 8, EKF converges in 5-8 frames. On random motion, innovation spikes to 10-15, but MN model absorbs it (see IMM).

---

## 4. Interacting Multiple Model (IMM)

### 4.1 Motivation

A single motion model is either too sluggish (misses random turns) or too noisy (jitters on straight motion). IMM runs three EKFs in parallel with different process-noise tunings and probabilistically fuses them. (Implementation Plan section 22)

### 4.2 Model Set

| Model | Abbrev | Best For | Q Scale | Behaviour |
|-------|--------|----------|---------|-----------|
| Constant Velocity | CV | straight, steady tracking | 0.6 | Low noise, smooth, accelerates toward zero |
| Constant Acceleration | CA | accelerating, start of circular/figure-8 | 1.2 | Allows persistent acceleration |
| Manoeuvre / High-Process-Noise | MN | random, sudden turns, platform disturbance | 3.0 | Large Q, quick response, noisier |

A coordinated-turn model was considered but CV/CA/MN proved more robust for mixed trajectories.

### 4.3 Transition Matrix

```
         -> CV    CA    MN
from CV [ 0.90  0.08  0.02 ]
     CA [ 0.08  0.90  0.02 ]
     MN [ 0.05  0.10  0.85 ]
```

High diagonal keeps model switching stable; MN has higher entry from any state when likelihood favours it. Initial `probs = [0.6, 0.25, 0.15]`.

### 4.4 IMM Cycle

```python
# src/fsoc_tracker/tracking/imm.py:18
class IMM:
    def predict(self, dt=None):
        for m in self.models.values():
            m.predict(dt)
        self._fuse()
        return self.fused_x.copy()

    def update(self, z_px, confidence=0.9):
        likelihoods = []
        for name in self.model_names:
            _, nis = self.models[name].update(z_px, confidence)
            like = float(np.exp(-0.5 * min(nis, 20)) + 1e-9)
            likelihoods.append(like)
        likelihoods = np.array(likelihoods)
        prior = self.trans.T.dot(self.probs) if z_px is not None else self.probs
        posterior_unnorm = prior * likelihoods if z_px is not None else prior
        self.probs = posterior_unnorm / posterior_unnorm.sum()
        self.probs = np.maximum(self.probs, 0.02)  # clamp min
        self.probs /= self.probs.sum()
        self._fuse()
        return self.fused_x.copy()

    def _fuse(self):
        xs = np.stack([self.models[n].x for n in self.model_names], axis=0)
        fused = np.average(xs, axis=0, weights=self.probs)
        self.fused_x = fused
        P_fused = zeros((6,6))
        for i, name in enumerate(self.model_names):
            diff = (self.models[name].x - fused).reshape(6,1)
            P_fused += self.probs[i] * (Ps[i] + diff @ diff.T)
        self.fused_P = P_fused
```

Mixing is simplified (no explicit interaction mixing step — each EKF predicts independently; full mixing is applied via likelihood-weighted posterior). Innovation likelihood `exp(-0.5*NIS)` naturally raises MN when residuals spike.

### 4.5 Fused Output

```
fused_state  = sum_i mu_i * x_i
fused_covar  = sum_i mu_i * (P_i + (x_i - x_fused)(x_i - x_fused)^T)
model_probs  = [P_CV, P_CA, P_MN]   (displayed in Dashboard)
```

On straight motion, `P_CV ~ 0.72`; on circular acceleration `P_CA` rises to 0.35; on random jolts `P_MN` spikes to 0.4-0.6 then decays.

### 4.6 Projection

The fused angular state is projected to pixel space via the CV model's `h()` (all models share `fx,fy,cx,cy`):

```python
def get_pixel(self):
    return self.models["CV"]._h(self.fused_x)
```

---

## 5. Tracking State Machine

Explicit states make acquisition, loss and re-acquisition measurable (spec section 9):

```python
# src/fsoc_tracker/tracking/state_machine.py:9
class TrackingStateMachine:
    def update(self, detection_valid, confidence):
        if detection_valid and confidence > 0.45:
            self.missed = 0; self.candidate_frames += 1; self.locked_frames += 1
            if self.candidate_frames >= 3:
                if self.locked_frames >= 5: self.state = LOCKED
                else:                       self.state = ACQUIRING
            else:                           self.state = CANDIDATE
        else:
            self.missed += 1
            if self.missed <= 3:             self.state = TEMP_LOST if was LOCKED else ...
            elif self.missed <= 15:          self.state = TEMP_LOST / REACQUIRING
            elif self.missed <= 30:          self.state = REACQUIRING
            else:                            self.state = SEARCHING / FAILED
        return self.state
```

| State | Meaning | Entry | Controller |
|-------|---------|-------|------------|
| `SEARCHING` | No target | > 30 missed frames or init | Spiral search |
| `CANDIDATE` | Possible detection | 1-2 valid frames | Cautious PID 0.55x |
| `ACQUIRING` | Consistent detections, slewing | 3-5 consecutive | PID |
| `LOCKED` | Stable lock | >=5 consecutive valid | Full PID + FF |
| `TEMP_LOST` | Brief dropout | 1-15 missed after LOCKED | Reduced PID, integral decay |
| `REACQUIRING` | Extended loss | 6-30 missed | Spiral search |
| `FAILED` | Recovery timeout | > 60 missed | Search, flagged red |

Thresholds: `lost_timeout=15`, `reacq_timeout=30`, `required_lock=5`, `required_candidate=3` (all configurable via `tracker` config).

---

## 6. PID Pan-Tilt Controller

### 6.1 Control Error

Uses the **fused IMM angular estimate**, not raw centroid, for smoothness:

```
error_pan  = alpha_hat   (deg, desired 0)
error_tilt = beta_hat
```

### 6.2 PID Law (per axis, independent gains)

```
command = Kp*error + Ki*integral(error) + Kd*derivative(error) + FF*velocity_hat
```

```python
# src/fsoc_tracker/control/pid.py:11
class PIDController:
    def step(self, error_deg, dt):
        dz = 0.015 * (self.deadzone/2.0)
        if abs(error_deg) < dz:
            return 0.0  # deadzone — prevents jitter near centre
        p = self.kp * error_deg
        self.integral += error_deg * dt
        self.integral = clip(self.integral, -limit, +limit)
        i = self.ki * self.integral
        deriv = (error_deg - self.prev_error) / dt
        deriv_f = alpha*deriv + (1-alpha)*self.prev_deriv  # low-pass alpha=0.2
        d = self.kd * deriv_f
        self.prev_error = error_deg; self.prev_deriv = deriv_f
        return p + i + d
```

Defaults `Kp=1.2`, `Ki=0.05`, `Kd=0.15`, `deadzone=2 px` (mapped to ~0.015 deg), `integral_limit=8`, `FF=0.0` (enable when velocity estimate is reliable). Derivative is computed from the **filtered EKF estimate**, not raw measurement, reducing noise amplification.

### 6.3 Saturation and Anti-Windup

```python
# src/fsoc_tracker/control/camera_controller.py:50
pan = self.pan_pid.step(err_pan, dt) + self.feedforward * vel_pan
tilt = self.tilt_pid.step(err_tilt, dt) + self.feedforward * vel_tilt
saturated = False
if pan > max_pan: pan = max_pan; saturated=True
if tilt < -max_tilt: tilt = -max_tilt; saturated=True
# if saturated or TEMP_LOST, integral is clamped/decayed
if state == TEMP_LOST:
    self.pan_pid.integral *= 0.96
```

- Integral is clamped by `integral_limit`; on saturation it is not allowed to grow further.
- In `TEMP_LOST`, integral decays 4 % per frame, preventing wind-up that would cause overshoot on re-acquisition.
- When `innovation > 18` (outlier), integral is frozen.

### 6.4 Search Controller (Re-acquisition)

When state is `SEARCHING`/`REACQUIRING`/`FAILED`, PID is replaced by an expanding spiral:

```python
# src/fsoc_tracker/control/camera_controller.py:32
self.search_angle += 0.32
self.search_radius = min(4.5, self.search_radius + 0.06)
pan_rate = cos(search_angle) * search_radius * 0.85
tilt_rate = sin(search_angle) * search_radius * 0.85
pan_rate = clip(pan_rate, -max_pan, +max_pan)
return ControlCommand(pan_rate, tilt_rate, search_mode=True)
```

This covers the FOV in ~1 s without unstable PID behaviour on a lost target. Upon re-lock, `search_radius` decays `*=0.9` per frame.

### 6.5 Tuning Sequence (recommended)

1. Set `Ki=Kd=0`, raise `Kp` until quick response without oscillation.
2. Add `Kd` to reduce overshoot.
3. Add small `Ki` only if steady-state bias remains; test with loss scenarios before committing.
See `docs/configuration.md` for per-parameter effects.

---

## 7. AI Methods and Hybrid Approach

The specification says *AI-assisted* but does not mandate a deep detector. The implemented hybrid is intentionally explainable and benchmark-robust:

| AI / ML Element | Where | Training / Data | Inference Cost |
|----------------|-------|----------------|----------------|
| Adaptive `bg + k*noise` threshold | Detector threshold | No training — background/noise estimated per frame | Negligible |
| Candidate scoring with prediction gating | Detector scoring | No training — geometry + brightness + temporal proximity | O(num_candidates) |
| EKF with nonlinear measurement | Tracker | No training — first-principles projection | O(1) |
| IMM with learned transition `trans` | Tracker | Heuristic but validated across trajectories | O(3) EKF |
| Optional learned shape classifier | Detector extension point | Train on synthetic beacon patches: clean vs noise vs star | < 2 ms if enabled |

A pure learned detector (e.g., tiny YOLO on synthetic beacons) is supported as a drop-in: implement `detect(frame_gray, predicted_pos) -> Detection` and register it. It was not made the default because (a) synthetic-to-video domain gap risks benchmark failure, and (b) connected-components with prediction gating already achieves RMSE < 6 px in haze.

Future AI extension: train a patch CNN on `World` generators (varying shape/size/atmosphere) to score candidates, replacing the hand-tuned `brightness*0.3 + shape*0.2 + prox*0.2` with learned weights — see `docs/technical_report.md` section 9.

---

## 8. End-to-End Algorithm Walkthrough

```
Frame (640x480 gray, possibly noisy/jittered)
  |
  v
BeaconDetector.detect(frame, predicted_pos=Tracker.get_predicted_pixel())
  -> Detection(valid, centroid, confidence)
  |
  v
Tracker.step(detection, frame):
  IMM.predict(dt)              # F*x, P for each of CV/CA/MN
  for each model: EKF.update(z, confidence) -> NIS
  IMM likelihood + transition -> probs -> fused x_hat, P_fused
  StateMachine.update(valid, conf) -> LOCKED / TEMP_LOST / ...
  -> Estimate(pos_angle=fused alpha,beta, pos_px=project(fused), model_probs, state)
  |
  v
CameraController.step(estimate):
  if SEARCHING/REACQUIRING: spiral search Command
  else: PID(fused error) + FF*velocity -> clamped Command
  |
  v
VirtualCamera.apply_command(pan_rate, tilt_rate, dt)  # next frame's viewport shifts
```

Every step is O(1) except the detector's connected components. The pipeline sustains >= 28 FPS on a typical laptop CPU.

---

## 9. Algorithmic Guarantees and Limits

- **Hidden ground truth:** detector/EKF/IMM/PID never access `World.world_pos` or `GroundTruth.image_pos`; only `VirtualCamera.center_world` and pixel frames.
- **Noise robustness:** adaptive threshold + morphology + prediction gating handles Gaussian std up to 20, S&P up to 0.04, Poisson simultaneously. Beyond that (e.g., heavy fog `strength>0.6`) detection confidence degrades and state falls to REACQUIRING — correctly reflecting the operating envelope.
- **Manoeuvre robustness:** IMM MN absorbs random-direction changes within 2-3 frames without diverging.
- **Control stability:** deadzone + saturation + anti-windup prevents oscillation; with `max_pan=5 deg/s` the camera can follow targets up to ~12 px/frame at 30 Hz before error grows — above that loss grows gracefully and re-acquisition triggers.

---

## 10. References

- Implementation Plan.md sections 6 (coordinate model), 7 (detector), 21-26 (EKF-IMM-PID, search).
- `src/fsoc_tracker/perception/detector.py`, `tracking/ekf.py`, `imm.py`, `state_machine.py`, `tracker.py`, `control/pid.py`, `camera_controller.py`
- Metrics definitions: Implementation Plan section 9, `evaluation/metrics.py`
