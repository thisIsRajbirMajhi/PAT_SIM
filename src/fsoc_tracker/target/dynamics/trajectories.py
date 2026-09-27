"""Target dynamics — canonical trajectory implementations.

Conventions:
    * Analytic trajectories (straight/circular/figure-8/spiral/sinusoidal)
      are pure functions of time step t (frames since run start).
    * RandomTrajectory is stateful (momentum random walk): it MUST be
      stepped exactly once per frame in increasing t order, and reset()
      to restart a run reproducibly.
    * All positions are world pixels; constructors take world_size and
      keep targets inside a margin (no silent teleports except the
      documented sinusoidal wrap).
"""
import math
import warnings

import numpy as np

TRAJECTORY_TYPES = (
    "straight", "circular", "figure_eight", "random",
    "spiral", "sinusoidal", "user-defined",
)

_TRAJECTORY_ALIASES = {
    "figure-eight": "figure_eight",
    "figure_8": "figure_eight",
    "figure-8": "figure_eight",
    "figure8": "figure_eight",
    "figure_of_8": "figure_eight",
    "user_defined": "user-defined",
}


def normalize_trajectory_type(raw):
    t = str(raw or "straight").strip().lower().replace(" ", "_")
    return _TRAJECTORY_ALIASES.get(t, t)


def _random_init(rng, ws):
    """Uniform start position, safe for small worlds."""
    lo_x = min(400, max(ws[0] // 4, 50))
    hi_x = max(ws[0] - lo_x, lo_x + 1)
    lo_y = min(400, max(ws[1] // 4, 50))
    hi_y = max(ws[1] - lo_y, lo_y + 1)
    return (int(rng.integers(lo_x, hi_x)), int(rng.integers(lo_y, hi_y)))


class Trajectory:
    def step(self, t: float) -> tuple[float, float]:
        raise NotImplementedError

    def reset(self, seed=None):
        """Restart stateful trajectories; no-op for analytic ones."""


# Fixed motion geometry (kept simple by design — tune via trajectory + speed).
STRAIGHT_ANGLE_DEG = 30.0
CIRCULAR_RADIUS = 400.0
FIGURE_EIGHT_RADIUS = 350.0
SINUSOIDAL_AMPLITUDE = 250.0
SINUSOIDAL_WAVELENGTH = 700.0


class StraightTrajectory(Trajectory):
    def __init__(self, start=(600, 600), angle_deg=STRAIGHT_ANGLE_DEG, speed_px_per_frame=3.0,
                 world_size=(2000, 2000)):
        self.start = np.array(start, dtype=float)
        self.angle = math.radians(angle_deg)
        self.speed = speed_px_per_frame
        self.world_size = world_size
        self.dir = np.array([math.cos(self.angle), math.sin(self.angle)])

    def step(self, t: float):
        pos = self.start + self.dir * self.speed * t
        # mirror bounce at a 50px margin
        for i in range(2):
            lo, hi = 50, self.world_size[i] - 50
            span = max(hi - lo, 1)
            if pos[i] < lo:
                pos[i] = lo + (lo - pos[i]) % span
            elif pos[i] > hi:
                pos[i] = hi - (pos[i] - hi) % span
        return float(pos[0]), float(pos[1])


class CircularTrajectory(Trajectory):
    def __init__(self, center=(1000, 1000), radius=400, speed_px_per_frame=3.0, angular_speed=None):
        self.center = np.array(center, dtype=float)
        self.radius = radius
        if angular_speed is None:
            # speed = r * omega  => omega = speed / r  (rad per frame)
            angular_speed = speed_px_per_frame / max(radius, 1)
        self.omega = angular_speed

    def step(self, t: float):
        ang = self.omega * t
        return float(self.center[0] + self.radius * math.cos(ang)), float(self.center[1] + self.radius * math.sin(ang))


class FigureEightTrajectory(Trajectory):
    def __init__(self, center=(1000, 1000), radius=350, speed_px_per_frame=3.0):
        self.center = np.array(center, dtype=float)
        self.radius = radius
        self.omega = speed_px_per_frame / max(radius, 1) * 0.85

    def step(self, t: float):
        ang = self.omega * t
        # Lissajous figure-8: x = cx + r*sin(ang), y = cy + r*sin(ang)*cos(ang)
        x = self.center[0] + self.radius * math.sin(ang)
        y = self.center[1] + self.radius * math.sin(ang) * math.cos(ang)
        return float(x), float(y)


class RandomTrajectory(Trajectory):
    """Momentum random walk. Stateful: step exactly once per frame; reset() to restart."""

    def __init__(self, start=(1000, 1000), speed_px_per_frame=3.5, world_size=(2000, 2000), seed=42):
        self.start = tuple(start)
        self.speed = speed_px_per_frame
        self.world_size = world_size
        self.seed = int(seed)
        self.reset()

    def reset(self, seed=None):
        if seed is not None:
            self.seed = int(seed)
        self.pos = np.array(self.start, dtype=float)
        self.rng = np.random.default_rng(self.seed)
        self.dir = self.rng.uniform(0, 2 * math.pi)
        self.steps_since_turn = 0
        self.velocity = (0.0, 0.0)

    def step(self, t: float):
        # random walk with momentum (t kept for API compatibility; motion is incremental)
        prev = self.pos.copy()
        if self.steps_since_turn > 12 and self.rng.random() < 0.12:
            self.dir += self.rng.normal(0, 0.9)
            self.steps_since_turn = 0
        self.dir += self.rng.normal(0, 0.06)
        self.pos[0] += math.cos(self.dir) * self.speed + self.rng.normal(0, 0.5)
        self.pos[1] += math.sin(self.dir) * self.speed + self.rng.normal(0, 0.5)
        # keep in bounds with bounce
        for i in range(2):
            if self.pos[i] < 40:
                self.pos[i] = 40
                self.dir = math.pi - self.dir if i == 0 else -self.dir
            elif self.pos[i] > self.world_size[i] - 40:
                self.pos[i] = self.world_size[i] - 40
                self.dir = math.pi - self.dir if i == 0 else -self.dir
        self.steps_since_turn += 1
        self.velocity = (float(self.pos[0] - prev[0]), float(self.pos[1] - prev[1]))
        return float(self.pos[0]), float(self.pos[1])


class SpiralTrajectory(Trajectory):
    def __init__(self, center=(1000, 1000), speed_px_per_frame=3.0):
        self.center = np.array(center, dtype=float)
        self.speed = speed_px_per_frame
        # scale expansion and angular rate with commanded speed (3.0 = reference)
        k = speed_px_per_frame / 3.0
        self.growth = 2.2 * k
        self.omega = 0.04 * (0.5 + 0.5 * k)
        self.max_r = 700

    def step(self, t: float):
        r = min(80 + self.growth * t, self.max_r)
        ang = self.omega * t
        return float(self.center[0] + r * math.cos(ang)), float(self.center[1] + r * math.sin(ang))


class SinusoidalTrajectory(Trajectory):
    def __init__(self, start=(400, 1000), speed_px_per_frame=3.0, amplitude=250, wavelength=700,
                 world_size=(2000, 2000)):
        self.start = np.array(start, dtype=float)
        self.speed = speed_px_per_frame
        self.amp = amplitude
        self.wl = wavelength
        self.world_size = world_size

    def step(self, t: float):
        w = self.world_size[0]
        x = self.start[0] + self.speed * t
        # wrap across the world width with a 100px margin
        x = 100 + (x - 100) % max(w - 200, 1)
        y = float(np.clip(self.start[1] + self.amp * math.sin(2 * math.pi * t * self.speed / self.wl),
                          40, self.world_size[1] - 40))
        return float(x), float(y)


class UserDefinedTrajectory(Trajectory):
    """Trajectory from CSV rows (x,y or t,x,y per frame). Falls back to straight."""

    def __init__(self, csv_path=None, world_size=(2000, 2000), seed=42):
        self.world_size = world_size
        self.points = []
        self.csv_path = csv_path
        if csv_path and isinstance(csv_path, str):
            try:
                import csv
                import os
                if os.path.exists(csv_path):
                    with open(csv_path, newline='') as f:
                        reader = csv.reader(f)
                        for row in reader:
                            if not row or row[0].strip().startswith('#'):
                                continue
                            # support x,y or t,x,y
                            vals = [float(v) for v in row if v.strip() != '']
                            if len(vals) >= 2:
                                if len(vals) == 2:
                                    x, y = vals
                                else:
                                    # assume t,x,y or x,y with extra
                                    x, y = vals[-2], vals[-1]
                                self.points.append((float(x), float(y)))
                else:
                    warnings.warn(f"[UserDefinedTrajectory] file not found: {csv_path}; using straight fallback.",
                                  UserWarning, stacklevel=2)
            except Exception as e:
                warnings.warn(f"[UserDefinedTrajectory] failed to load {csv_path}: {e}; using straight fallback.",
                              UserWarning, stacklevel=2)
        # fallback if empty: straight line through a random start
        if not self.points:
            rng = np.random.default_rng(seed)
            ws = world_size
            init = _random_init(rng, ws)
            angle = math.radians(30)
            dir_vec = np.array([math.cos(angle), math.sin(angle)])
            for t in range(2000):
                pos = np.array(init, dtype=float) + dir_vec * 3.0 * t
                for i in range(2):
                    lo, hi = 50, world_size[i] - 50
                    span = max(hi - lo, 1)
                    if pos[i] < lo:
                        pos[i] = lo + (lo - pos[i]) % span
                    elif pos[i] > hi:
                        pos[i] = hi - (pos[i] - hi) % span
                self.points.append((float(pos[0]), float(pos[1])))

    def step(self, t: float):
        idx = int(t) % len(self.points)
        # clamp to world bounds
        x, y = self.points[idx]
        x = float(np.clip(x, 50, self.world_size[0] - 50))
        y = float(np.clip(y, 50, self.world_size[1] - 50))
        return x, y


def make_trajectory(cfg, seed=42):
    t = normalize_trajectory_type(cfg["target"].get("trajectory", "straight"))
    if t not in TRAJECTORY_TYPES:
        raise ValueError(f"Unknown trajectory {cfg['target'].get('trajectory')!r}; "
                         f"expected one of {TRAJECTORY_TYPES}")
    speed = cfg["target"]["speed_px_per_frame"]
    ws = (cfg["world"]["width"], cfg["world"]["height"])
    init = cfg["target"].get("initial_pos")
    user_centre = (
        cfg["target"].get("initial_mode") == "user-defined"
        and isinstance(init, (list, tuple)) and len(init) == 2
    )
    if init is None:
        rng = np.random.default_rng(seed)
        init = _random_init(rng, ws)
    else:
        init = tuple(init)
    # user-defined start doubles as orbit centre for centred motions
    center = tuple(init) if user_centre else (ws[0] // 2, ws[1] // 2)
    if t == "straight":
        return StraightTrajectory(start=init, angle_deg=STRAIGHT_ANGLE_DEG,
                                  speed_px_per_frame=speed, world_size=ws)
    elif t == "circular":
        return CircularTrajectory(center=center, radius=CIRCULAR_RADIUS,
                                  speed_px_per_frame=speed)
    elif t == "figure_eight":
        return FigureEightTrajectory(center=center, radius=FIGURE_EIGHT_RADIUS,
                                     speed_px_per_frame=speed)
    elif t == "random":
        return RandomTrajectory(start=init, speed_px_per_frame=speed, world_size=ws, seed=seed)
    elif t == "spiral":
        return SpiralTrajectory(center=center, speed_px_per_frame=speed)
    elif t == "sinusoidal":
        return SinusoidalTrajectory(start=init, speed_px_per_frame=speed,
                                    amplitude=SINUSOIDAL_AMPLITUDE,
                                    wavelength=SINUSOIDAL_WAVELENGTH,
                                    world_size=ws)
    elif t == "user-defined":
        csv_path = cfg["target"].get("custom_trajectory_file", cfg["target"].get("custom_trajectory_path", None))
        return UserDefinedTrajectory(csv_path=csv_path, world_size=ws, seed=seed)
