import numpy as np
import cv2
from .base import FrameSource
from ..common.types import Frame, GroundTruth
from ..simulation.world import World
from ..camera import VirtualCamera
from ..disturbances import DisturbancePipeline, PlatformMotion

class SyntheticSource(FrameSource):
    def __init__(self, cfg, seed=42):
        self.cfg = cfg
        self.seed = seed
        self.world = World(cfg, seed=seed)
        self.camera = VirtualCamera(
            world_size=(cfg["world"]["width"], cfg["world"]["height"]),
            resolution=tuple(cfg["camera"]["resolution"]),
            fov_deg=tuple(cfg["camera"]["fov_deg"]),
            max_pan_speed=cfg["camera"]["max_pan_speed"],
            max_tilt_speed=cfg["camera"]["max_tilt_speed"],
        )
        # Sr.6 Initial Camera Position: centre (0,0) or user-defined pan/tilt
        if cfg["camera"].get("initial_position") == "user-defined":
            self.camera.pan = float(cfg["camera"].get("initial_pan", 0.0))
            self.camera.tilt = float(cfg["camera"].get("initial_tilt", 0.0))
            self.camera._update_center()
        self.platform = PlatformMotion(cfg, seed=seed)
        self.rng = np.random.default_rng(seed)
        self.frame_id = 0
        self._fps = float(cfg["camera"]["fps"])
        # shared disturbances: single canonical pipeline (atmosphere -> noise -> jitter)
        self.pipeline = DisturbancePipeline(cfg)
        # legacy mirrors (kept for backward compat; canonical state lives in self.pipeline)
        self.jitter = self.pipeline.jitter
        self.atmo_type = self.pipeline.atmo_type
        self.atmo_strength = self.pipeline.atmo_strength
        self.noise_cfg = self.pipeline.noise_cfg

    @property
    def fps(self): return self._fps
    @property
    def resolution(self): return tuple(self.cfg["camera"]["resolution"])

    def is_opened(self): return True
    def release(self): pass

    def reset(self):
        self.world.reset(seed=self.seed)
        self.camera = VirtualCamera(
            world_size=(self.cfg["world"]["width"], self.cfg["world"]["height"]),
            resolution=tuple(self.cfg["camera"]["resolution"]),
            fov_deg=tuple(self.cfg["camera"]["fov_deg"]),
            max_pan_speed=self.cfg["camera"]["max_pan_speed"],
            max_tilt_speed=self.cfg["camera"]["max_tilt_speed"],
        )
        if self.cfg["camera"].get("initial_position") == "user-defined":
            self.camera.pan = float(self.cfg["camera"].get("initial_pan", 0.0))
            self.camera.tilt = float(self.cfg["camera"].get("initial_tilt", 0.0))
            self.camera._update_center()
        self.frame_id = 0
        self.rng = np.random.default_rng(self.seed)
        # platform is stateful (t/offset/rng) — must restart too, else reset is not reproducible
        self.platform = PlatformMotion(self.cfg, seed=self.seed)
        self.pipeline.update_config(self.cfg)
        self.jitter = self.pipeline.jitter
        self.atmo_type = self.pipeline.atmo_type
        self.atmo_strength = self.pipeline.atmo_strength
        self.noise_cfg = self.pipeline.noise_cfg

    def apply_camera_command(self, pan_rate, tilt_rate, dt):
        self.camera.apply_command(pan_rate, tilt_rate, dt)

    def read(self):
        # advance world
        world_pos = self.world.step()
        # platform motion shifts world rendering? Simulate by shifting world_pos relative to camera
        # For simplicity, platform offset shifts camera center inverse
        # Apply platform delta to camera center
        pdx, pdy = self.platform.step()
        # We model platform motion as apparent world shift: move world_pos by platform offset
        # Instead, shift camera center slightly
        # Add to world_pos for ground truth visibility check? But easier: keep world_pos, but perturb camera viewport
        # We'll perturb by moving camera center opposite to platform motion
        if self.platform.type != "none":
            # platform ego-motion must persist via pan/tilt: center_world is
            # recomputed from pan/tilt inside _update_center(), so nudging it
            # directly is discarded (platform was silently a no-op)
            self.camera.pan += pdx / self.camera.px_per_deg
            self.camera.tilt -= pdy / self.camera.px_per_deg
            self.camera._update_center()

        world_img = self.world.render_world(world_pos)
        # extract viewport
        frame_img = self.camera.extract_viewport(world_img)

        # shared disturbances pipeline per spec (atmosphere -> gaussian -> salt&pepper -> poisson -> jitter)
        frame_img = self.pipeline.apply(frame_img, self.rng)

        # Sr.2 Camera Type: if colour, present as BGR for display (detector will convert to gray)
        if self.cfg["camera"].get("type", "monochrome") in ("colour", "color"):
            # subtle colour tint: convert gray to BGR and add faint blue sky tint for realism
            frame_img = cv2.cvtColor(frame_img, cv2.COLOR_GRAY2BGR)
            # add very light blue tint to background (non-beacon) to indicate colour mode
            # beacon remains white
            frame_img[:, :, 0] = np.clip(frame_img[:, :, 0].astype(np.int16) + 6, 0, 255).astype(np.uint8)  # blue channel +6

        # ground truth in image coords
        image_pos = self.camera.world_to_image(world_pos)
        gt = GroundTruth(world_pos=world_pos, visible=image_pos is not None, image_pos=image_pos)

        frame = Frame(image=frame_img, frame_id=self.frame_id, timestamp=self.frame_id/self._fps, source_name="synthetic")
        self.frame_id += 1
        return frame, gt

    def update_config(self, cfg):
        self.cfg = cfg
        self.pipeline.update_config(cfg)
        # keep legacy mirrors in sync
        self.jitter = self.pipeline.jitter
        self.atmo_type = self.pipeline.atmo_type
        self.atmo_strength = self.pipeline.atmo_strength
        self.noise_cfg = self.pipeline.noise_cfg
        self._fps = float(cfg["camera"]["fps"])
        # world + environment (stars/gradient/vignetting/brightness) — rebuild base if needed
        self.world.update_config(cfg, seed=self.seed)
        # platform
        self.platform = PlatformMotion(cfg, seed=self.seed)
        # camera — rebuild if resolution/world/fov changed, else just update rates
        needs_new_cam = (
            (self.camera.res_w, self.camera.res_h) != tuple(cfg["camera"]["resolution"]) or
            (self.camera.world_w, self.camera.world_h) != (cfg["world"]["width"], cfg["world"]["height"]) or
            (self.camera.fov_h, self.camera.fov_v) != tuple(cfg["camera"]["fov_deg"])
        )
        if needs_new_cam:
            # preserve pan/tilt
            old_pan, old_tilt = self.camera.pan, self.camera.tilt
            self.camera = VirtualCamera(
                world_size=(cfg["world"]["width"], cfg["world"]["height"]),
                resolution=tuple(cfg["camera"]["resolution"]),
                fov_deg=tuple(cfg["camera"]["fov_deg"]),
                max_pan_speed=cfg["camera"]["max_pan_speed"],
                max_tilt_speed=cfg["camera"]["max_tilt_speed"],
            )
            self.camera.pan, self.camera.tilt = old_pan, old_tilt
            self.camera._update_center()
        else:
            self.camera.max_pan_speed = cfg["camera"]["max_pan_speed"]
            self.camera.max_tilt_speed = cfg["camera"]["max_tilt_speed"]
