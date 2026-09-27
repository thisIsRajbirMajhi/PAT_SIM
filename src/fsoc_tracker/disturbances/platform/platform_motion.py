"""Platform ego-motion / vibration — environment-side geometry disturbance.

Perturbs the camera centre (via pan/tilt in SyntheticSource), i.e. the
world appears to shift. Deterministic given (cfg, seed); call reset()
or construct anew to restart a run reproducibly.

Motion types (speed in px/frame, bounded so tracking stays feasible):
    none:        no motion
    linear:      constant drift along heading (or fixed velocity vector)
    circular:    bounded orbit, radius ~ 8*speed
    random:      gaussian random walk, clipped to +-500 px
    spiral:      expanding orbit, capped
    figure_of_8: Lissajous 1:2, amplitude ~ 9*speed
Type aliases (figure_8, figure-8, figure8, ...) are normalized.
Per-step deltas are clamped to +-20 px (spec max).
"""
import math

import numpy as np

FIGURE_8_ALIASES = frozenset({
    "figure_of_8", "figure_8", "figure-of-8", "figure-of_8",
    "figure8", "figure-8", "figure_of-8", "eight",
})

LINEAR_WANDER = 600.0
RANDOM_WANDER = 500.0
MAX_DELTA = 20.0


def normalize_platform_type(raw):
    t = str(raw or "none").strip().lower().replace(" ", "_")
    if t in FIGURE_8_ALIASES:
        return "figure_of_8"
    return t


class PlatformMotion:
    def __init__(self, cfg, seed=42):
        plat = cfg.get("platform", {}) if isinstance(cfg, dict) else {}
        self.type = normalize_platform_type(plat.get("type", "none"))
        vel = plat.get("velocity_px_frame", plat.get("velocity_px_per_frame", None))
        if isinstance(vel, (list, tuple)) and len(vel) == 2:
            self.velocity = np.array([float(vel[0]), float(vel[1])])
            self.speed = float(np.hypot(vel[0], vel[1]))
        else:
            self.velocity = None
            self.speed = float(plat.get("speed_px_per_frame", 0.0))
            if isinstance(vel, (int, float)):
                self.speed = float(vel)
        self.seed = int(seed)
        self._init_rng()
        self.reset()

    def _init_rng(self):
        self.rng = np.random.default_rng(self.seed)
        self.heading = self.rng.uniform(0, 2 * math.pi) if self.type == "linear" else 0.0

    def reset(self, seed=None):
        if seed is not None:
            self.seed = int(seed)
        # rewind rng so a reset run reproduces the original motion exactly
        self._init_rng()
        self.t = 0
        self.offset = np.zeros(2, dtype=np.float64)
        self.prev_offset = np.zeros(2, dtype=np.float64)

    def _linear_delta(self):
        if self.velocity is not None:
            return float(self.velocity[0]), float(self.velocity[1])
        return math.cos(self.heading) * self.speed, math.sin(self.heading) * self.speed

    def step(self):
        self.t += 1
        if self.type == "none" or self.speed <= 0:
            return (0.0, 0.0)
        if self.type == "linear":
            dx, dy = self._linear_delta()
            new = np.clip(self.offset + [dx, dy], -LINEAR_WANDER, LINEAR_WANDER)
        elif self.type == "circular":
            ang, amp = 0.02 * self.t, self.speed * 8.0
            new = np.array([math.cos(ang) * amp, math.sin(ang) * amp])
        elif self.type == "random":
            new = np.clip(
                self.offset + self.rng.normal(0, self.speed * 0.7, size=2),
                -RANDOM_WANDER, RANDOM_WANDER,
            )
        elif self.type == "spiral":
            ang = 0.025 * self.t
            rad = min(120 + 0.6 * self.t, 450) * (self.speed / 5.0) * 0.5
            new = np.array([math.cos(ang) * rad, math.sin(ang) * rad])
        elif self.type == "figure_of_8":
            ang, amp = 0.018 * self.t, self.speed * 9.0
            new = np.array([
                math.sin(ang) * amp,
                math.sin(ang) * math.cos(ang) * amp * 0.8,
            ])
        else:  # unknown -> drift like linear
            dx, dy = self._linear_delta()
            new = np.clip(self.offset + [dx, dy], -LINEAR_WANDER, LINEAR_WANDER)
        delta = np.clip(new - self.prev_offset, -MAX_DELTA, MAX_DELTA)
        self.prev_offset = new.copy()
        self.offset = new.copy()
        return (float(delta[0]), float(delta[1]))

    def get_offset(self):
        return (float(self.offset[0]), float(self.offset[1]))
