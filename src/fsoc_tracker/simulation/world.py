import numpy as np
import cv2
from .trajectories import make_trajectory

class World:
    def __init__(self, cfg, seed=42):
        self.cfg = cfg
        self.seed = seed
        w = cfg["world"]["width"]
        h = cfg["world"]["height"]
        self.w = w; self.h = h
        self.bg = int(cfg["world"].get("background", 18))
        # base world image
        self.base = np.full((h, w), self.bg, dtype=np.uint8)
        # add subtle gradient / stars for texture
        rng = np.random.default_rng(seed)
        # faint texture
        noise = rng.integers(0, 6, size=(h, w), dtype=np.uint8)
        self.base = cv2.add(self.base, noise)
        # trajectory
        self.traj = make_trajectory(cfg, seed=seed)
        self.target_size = int(cfg["target"]["size"])
        self.target_intensity = int(cfg["target"].get("intensity", 255))
        self.frame_id = 0
        self.world_pos = self.traj.step(0)

    def step(self):
        self.world_pos = self.traj.step(self.frame_id)
        self.frame_id += 1
        return self.world_pos

    def render_world(self, world_pos=None):
        if world_pos is None:
            world_pos = self.world_pos
        img = self.base.copy()
        # draw beacon as bright square with soft glow
        x, y = int(round(world_pos[0])), int(round(world_pos[1]))
        s = self.target_size
        half = s//2
        # glow
        glow = 255
        cv2.rectangle(img, (x-half-1, y-half-1), (x+half+1, y+half+1), int(self.bg+45), -1)
        # core beacon
        cv2.rectangle(img, (x-half, y-half), (x+half, y+half), self.target_intensity, -1)
        # add slight gaussian blur to beacon core for realism (only small region)
        # clipped
        x0 = max(0, x-half-2); y0 = max(0, y-half-2)
        x1 = min(self.w, x+half+3); y1 = min(self.h, y+half+3)
        patch = img[y0:y1, x0:x1]
        if patch.size > 0:
            patch = cv2.GaussianBlur(patch, (3,3), 0)
            img[y0:y1, x0:x1] = patch
            # re-brighten center
            cv2.rectangle(img, (x-half, y-half), (x+half, y+half), self.target_intensity, -1)
        return img

    def reset(self, seed=None):
        if seed is not None:
            self.seed = seed
        self.frame_id = 0
        self.traj = make_trajectory(self.cfg, seed=self.seed)
        self.world_pos = self.traj.step(0)
