import math, numpy as np

class PlatformMotion:
    def __init__(self, cfg, seed=42):
        self.type = cfg["platform"].get("type","none")
        self.speed = float(cfg["platform"].get("speed_px_per_frame",0))
        self.amp = float(cfg["platform"].get("amplitude",0))
        self.rng = np.random.default_rng(seed)
        self.offset = np.array([0.0, 0.0])
        self.prev_offset = np.array([0.0, 0.0])
        self.t = 0
        self.dir = self.rng.uniform(0, 2*math.pi) if self.type=="linear" else 0
        # for spiral/figure8 keep phase
        self.spiral_r = 0.0

    def step(self):
        self.t += 1
        if self.type == "none" or self.speed==0:
            return (0.0, 0.0)
        new_offset = self.offset.copy()
        if self.type == "linear":
            dx = math.cos(self.dir) * self.speed
            dy = math.sin(self.dir) * self.speed
            new_offset[0] += dx
            new_offset[1] += dy
            new_offset = np.clip(new_offset, -600, 600)
        elif self.type == "circular":
            ang = 0.02 * self.t
            amp = self.speed * 8.0
            new_offset[0] = math.cos(ang) * amp
            new_offset[1] = math.sin(ang) * amp
        elif self.type == "random":
            # random walk delta
            dx = self.rng.normal(0, self.speed * 0.7)
            dy = self.rng.normal(0, self.speed * 0.7)
            new_offset[0] += dx
            new_offset[1] += dy
            new_offset = np.clip(new_offset, -500, 500)
        elif self.type == "spiral":
            # expanding spiral
            ang = 0.025 * self.t
            rad = min(120 + 0.6 * self.t, 450) * (self.speed / 5.0)
            new_offset[0] = math.cos(ang) * rad * 0.5
            new_offset[1] = math.sin(ang) * rad * 0.5
        elif self.type in ("figure_of_8", "figure_8", "figure-eight", "figure8"):
            ang = 0.018 * self.t
            amp = self.speed * 9.0
            new_offset[0] = math.sin(ang) * amp
            new_offset[1] = math.sin(ang) * math.cos(ang) * amp * 0.8
        else:
            # fallback linear
            dx = math.cos(self.dir) * self.speed
            dy = math.sin(self.dir) * self.speed
            new_offset[0] += dx
            new_offset[1] += dy

        delta = new_offset - self.prev_offset
        # for linear/random where we used incremental, prev_offset is previous new_offset, so delta is correct
        # for circular/spiral/figure8 where new_offset is absolute, delta is also correct
        self.prev_offset = new_offset.copy()
        self.offset = new_offset.copy()
        # clamp delta to ±20 as per spec max
        delta = np.clip(delta, -20, 20)
        return (float(delta[0]), float(delta[1]))

    def get_offset(self):
        return tuple(self.offset)
