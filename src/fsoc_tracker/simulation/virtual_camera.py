import numpy as np
import math

class VirtualCamera:
    def __init__(self, world_size=(2000,2000), resolution=(640,480), fov_deg=(4.0,3.0), max_pan_speed=5.0, max_tilt_speed=5.0):
        self.world_w, self.world_h = world_size
        self.res_w, self.res_h = resolution
        self.fov_h, self.fov_v = fov_deg  # degrees
        # pan/tilt in degrees, center of world corresponds to 0,0
        self.pan = 0.0
        self.tilt = 0.0
        self.max_pan_speed = max_pan_speed
        self.max_tilt_speed = max_tilt_speed
        # world-to-angle scale: world width maps to ??? For simplicity, map world 2000px to FOV*? Actually we treat pan directly as world offset scaled.
        # Define scale: 1 degree = world_px_per_deg. world center to edge ~1000px should be maybe 10 deg for maneuverability.
        # But per spec: pixel error to angular error = e * FOV/W . So keep that.
        # For viewport extraction, convert pan/tilt to world pixel center.
        # 1 deg = (world visible range?) Let's define 1 deg = 250 px (so 4 deg = 1000 px viewport margin). Calibrate so pan +-4deg covers world.
        self.px_per_deg = 220.0  # tuned so max pan speed moves reasonably
        self.world_center = np.array([world_size[0]/2, world_size[1]/2], dtype=float)
        self._update_center()

    def _update_center(self):
        # pan moves x, tilt moves y (invert tilt so positive tilt moves up - y decreases)
        self.center_world = np.array([
            self.world_center[0] + self.pan * self.px_per_deg,
            self.world_center[1] - self.tilt * self.px_per_deg
        ])
        # clamp center so viewport stays inside world
        half_w = self.res_w / 2
        half_h = self.res_h / 2
        # World viewport is 1:1 pixel mapping (no zoom) - resolution equals world pixels visible
        self.center_world[0] = np.clip(self.center_world[0], half_w, self.world_w - half_w)
        self.center_world[1] = np.clip(self.center_world[1], half_h, self.world_h - half_h)
        # sync pan/tilt to clamped
        self.pan = (self.center_world[0] - self.world_center[0]) / self.px_per_deg
        self.tilt = -(self.center_world[1] - self.world_center[1]) / self.px_per_deg

    def apply_command(self, pan_rate, tilt_rate, dt):
        # clamp rates
        pan_rate = float(np.clip(pan_rate, -self.max_pan_speed, self.max_pan_speed))
        tilt_rate = float(np.clip(tilt_rate, -self.max_tilt_speed, self.max_tilt_speed))
        self.pan += pan_rate * dt
        self.tilt += tilt_rate * dt
        self._update_center()
        return pan_rate, tilt_rate

    def world_to_image(self, world_pos):
        # world_pos (x,y) -> image pixel (u,v) or None if outside FOV
        wx, wy = world_pos
        # viewport bounds
        left = self.center_world[0] - self.res_w/2
        top = self.center_world[1] - self.res_h/2
        u = wx - left
        v = wy - top
        if 0 <= u < self.res_w and 0 <= v < self.res_h:
            return (float(u), float(v))
        return None

    def image_to_angle_error(self, image_pos):
        # image_pos -> angular error (alpha, beta) relative to optical axis
        if image_pos is None:
            return None
        u, v = image_pos
        ex = u - self.res_w/2
        ey = v - self.res_h/2
        alpha = ex * (self.fov_h / self.res_w)
        beta = -ey * (self.fov_v / self.res_h)  # invert y for tilt
        return (alpha, beta)

    def angle_to_image(self, alpha, beta):
        # for EKF projection visualization
        u = self.res_w/2 + alpha * (self.res_w / self.fov_h)
        v = self.res_h/2 - beta * (self.res_h / self.fov_v)
        return (float(u), float(v))

    def get_viewport_bounds(self):
        left = self.center_world[0] - self.res_w/2
        top = self.center_world[1] - self.res_h/2
        return (left, top, left+self.res_w, top+self.res_h)

    def extract_viewport(self, world_image: np.ndarray):
        l, t, r, b = map(int, self.get_viewport_bounds())
        # world_image is HxW grayscale
        crop = world_image[t:b, l:r].copy()
        # ensure size matches resolution (world may be different size)
        if crop.shape[1] != self.res_w or crop.shape[0] != self.res_h:
            import cv2
            crop = cv2.resize(crop, (self.res_w, self.res_h), interpolation=cv2.INTER_LINEAR)
        return crop
