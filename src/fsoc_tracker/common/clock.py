import time

class Clock:
    def __init__(self, fps: float = 30.0):
        self.fps = fps
        self.dt = 1.0 / fps if fps > 0 else 1/30
        self.frame_id = 0
        self.t0 = time.perf_counter()

    def tick(self):
        self.frame_id += 1
        return self.frame_id, self.frame_id * self.dt

    def now(self) -> float:
        return time.perf_counter() - self.t0

    def reset(self):
        self.frame_id = 0
        self.t0 = time.perf_counter()
