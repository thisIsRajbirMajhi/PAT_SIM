import math
import numpy as np

class Trajectory:
    def step(self, t: float) -> tuple[float, float]:
        raise NotImplementedError

class StraightTrajectory(Trajectory):
    def __init__(self, start=(600,600), angle_deg=30, speed_px_per_frame=3.0, world_size=(2000,2000)):
        self.start = np.array(start, dtype=float)
        self.angle = math.radians(angle_deg)
        self.speed = speed_px_per_frame
        self.world_size = world_size
        self.dir = np.array([math.cos(self.angle), math.sin(self.angle)])

    def step(self, t: float):
        pos = self.start + self.dir * self.speed * t
        # bounce
        for i in range(2):
            if pos[i] < 50: 
                pos[i] = 50 + (50 - pos[i]) % (self.world_size[i]-100)
            elif pos[i] > self.world_size[i]-50:
                pos[i] = self.world_size[i]-50 - (pos[i]-(self.world_size[i]-50)) % (self.world_size[i]-100)
        return float(pos[0]), float(pos[1])

class CircularTrajectory(Trajectory):
    def __init__(self, center=(1000,1000), radius=400, speed_px_per_frame=3.0, angular_speed=None):
        self.center = np.array(center, dtype=float)
        self.radius = radius
        if angular_speed is None:
            # speed = r * omega  => omega = speed / r  (rad per frame)
            angular_speed = speed_px_per_frame / max(radius, 1)
        self.omega = angular_speed

    def step(self, t: float):
        ang = self.omega * t
        return float(self.center[0] + self.radius*math.cos(ang)), float(self.center[1] + self.radius*math.sin(ang))

class FigureEightTrajectory(Trajectory):
    def __init__(self, center=(1000,1000), radius=350, speed_px_per_frame=3.0):
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
    def __init__(self, start=(1000,1000), speed_px_per_frame=3.5, world_size=(2000,2000), seed=42):
        self.pos = np.array(start, dtype=float)
        self.speed = speed_px_per_frame
        self.world_size = world_size
        self.rng = np.random.default_rng(seed)
        self.dir = self.rng.uniform(0, 2*math.pi)
        self.steps_since_turn = 0

    def step(self, t: float):
        # random walk with momentum
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
                self.dir = math.pi - self.dir if i==0 else -self.dir
            elif self.pos[i] > self.world_size[i]-40:
                self.pos[i] = self.world_size[i]-40
                self.dir = math.pi - self.dir if i==0 else -self.dir
        self.steps_since_turn += 1
        return float(self.pos[0]), float(self.pos[1])

class SpiralTrajectory(Trajectory):
    def __init__(self, center=(1000,1000), speed_px_per_frame=3.0):
        self.center = np.array(center, dtype=float)
        self.speed = speed_px_per_frame
        self.omega = 0.04

    def step(self, t: float):
        r = 80 + 2.2 * t
        r = min(r, 700)
        ang = self.omega * t
        return float(self.center[0] + r*math.cos(ang)), float(self.center[1] + r*math.sin(ang))

class SinusoidalTrajectory(Trajectory):
    def __init__(self, start=(400,1000), speed_px_per_frame=3.0, amplitude=250, wavelength=700):
        self.start = np.array(start, dtype=float)
        self.speed = speed_px_per_frame
        self.amp = amplitude
        self.wl = wavelength

    def step(self, t: float):
        x = self.start[0] + self.speed * t
        # wrap
        x = 100 + (x - 100) % 1800
        y = self.start[1] + self.amp * math.sin(2*math.pi*t*self.speed / self.wl)
        return float(x), float(y)

def make_trajectory(cfg, seed=42):
    t = cfg["target"]["trajectory"]
    speed = cfg["target"]["speed_px_per_frame"]
    ws = (cfg["world"]["width"], cfg["world"]["height"])
    init = cfg["target"].get("initial_pos")
    if init is None:
        rng = np.random.default_rng(seed)
        init = (int(rng.integers(400, ws[0]-400)), int(rng.integers(400, ws[1]-400)))
    else:
        init = tuple(init)
    center = (ws[0]//2, ws[1]//2)
    if t == "straight":
        return StraightTrajectory(start=init, angle_deg=cfg["target"].get("angle_deg",30), speed_px_per_frame=speed, world_size=ws)
    elif t == "circular":
        return CircularTrajectory(center=center, radius=cfg["target"].get("radius",400), speed_px_per_frame=speed)
    elif t == "figure_eight":
        return FigureEightTrajectory(center=center, radius=cfg["target"].get("radius",350), speed_px_per_frame=speed)
    elif t == "random":
        return RandomTrajectory(start=init, speed_px_per_frame=speed, world_size=ws, seed=seed)
    elif t == "spiral":
        return SpiralTrajectory(center=center, speed_px_per_frame=speed)
    elif t == "sinusoidal":
        return SinusoidalTrajectory(start=init, speed_px_per_frame=speed)
    else:
        return StraightTrajectory(start=init, speed_px_per_frame=speed, world_size=ws)
