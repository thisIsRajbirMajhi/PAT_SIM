```text
┌────────────────────┐
│   Virtual Camera   │
│   world → view     │
└─────────┬──────────┘
          │ frame
          ▼
┌────────────────────┐
│  Beacon Detector   │
│ threshold + blobs  │
│ + score            │
└─────────┬──────────┘
          │ detection
          │ (valid, centroid, confidence)
          ▼
┌──────────────────────────────────────────────────────┐
│                        Tracker                       │
│                                                      │
│  ┌──────────────┐    ┌───────────────────────────┐   │
│  │ 1. Predict   │    │ Simple EKF (CV)           │   │
│  │    (IMM)     ├───▶│ Simple EKF (CA)           ├──▶│ Fused
│  │              │    │ Simple EKF (MN)           │   │ Estimate
│  └──────────────┘    └───────────────────────────┘   │
│                                                      │
│  ┌──────────────┐                                    │
│  │ 2. Update    │◀── detection                       │
│  └──────────────┘                                    │
│                                                      │
│  ┌──────────────────────────────────────────────┐    │
│  │ 3. State                                     │    │
│  │ SEARCHING → CANDIDATE → ACQUIRING / LOCKED   │    │
│  │       ↘ TEMP_LOST → REACQUIRING / FAILED     │    │
│  └──────────────────────────────────────────────┘    │
└─────────────────────────┬────────────────────────────┘
                          │ estimate
                          │ (pos, vel, state)
                          ▼
┌──────────────────────────────────────────────────────┐
│                  CameraController                    │
│                                                      │
│  TRACK:   PID + feedforward                          │
│  SEARCH:  spiral / tile / slew / intercept           │
└─────────────────────────┬────────────────────────────┘
                          │ pan_rate, tilt_rate command
                          ▼
                ┌────────────────────┐
                │  PID + Gimbal      │
                │  apply command     │
                └────────────────────┘
```
