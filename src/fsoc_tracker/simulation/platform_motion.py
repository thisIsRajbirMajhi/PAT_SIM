import math, numpy as np

class PlatformMotion:
    def __init__(self, cfg, seed=42):
        self.type = cfg["platform"].get("type","none")
        self.speed = float(cfg["platform"].get("speed_px_per_frame",0))
        self.amp = float(cfg["platform"].get("amplitude",0))
        self.rng = np.random.default_rng(seed)
        self.offset = np.array([0.0, 0.0])
        self.t = 0
        self.dir = self.rng.uniform(0, 2*math.pi) if self.type=="linear" else 0

    def step(self):
        self.t += 1
        if self.type == "none" or self.speed==0:
            return (0.0, 0.0)
        if self.type == "linear":
            dx = math.cos(self.dir) * self.speed
            dy = math.sin(self.dir) * self.speed
            self.offset[0] += dx
            self.offset[1] += dy
            # clamp offset to avoid drift out of bounds
            self.offset = np.clip(self.offset, -600, 600)
            return (float(dx), float(dy))
        elif self.type == "circular":
            ang = 0.02 * self.t
            ox = math.cos(ang) * self.speed * 8
            oy = math.sin(ang) * self.speed * 8
            return (ox, oy)
        elif self.type == "random":
            dx = self.rng.normal(0, self.speed)
            dy = self.rng.normal(0, self.speed)
            return (float(dx), float(dy))
        return (0.0,0.0)

    def get_offset(self):
        return tuple(self.offset)
