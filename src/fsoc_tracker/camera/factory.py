"""Factories for the Camera module."""
from .control import CameraController
from .optics import VirtualCamera


def make_camera(cfg, **overrides):
    cam = cfg.get("camera", {})
    world = cfg.get("world", {})
    return VirtualCamera(
        world_size=overrides.get(
            "world_size", (world.get("width", 2000), world.get("height", 2000))
        ),
        resolution=overrides.get("resolution", tuple(cam.get("resolution", (640, 480)))),
        fov_deg=overrides.get("fov_deg", tuple(cam.get("fov_deg", (4.0, 3.0)))),
        max_pan_speed=overrides.get("max_pan_speed", cam.get("max_pan_speed", 5.0)),
        max_tilt_speed=overrides.get("max_tilt_speed", cam.get("max_tilt_speed", 5.0)),
    )


def make_controller(cfg):
    return CameraController(cfg)


__all__ = ["make_camera", "make_controller"]
