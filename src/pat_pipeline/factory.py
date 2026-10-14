"""Factories for the pat_pipeline package (canonical)."""
from .camera.control import CameraController
from .camera.optics import VirtualCamera
from .detection import BeaconDetector
from .orchestration import SearchTrackPipeline
from .track import Tracker


def make_detector(cfg):
    return BeaconDetector(cfg)


def make_tracker(cfg):
    return Tracker(cfg)


def make_controller(cfg):
    return CameraController(cfg)


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


def make_pipeline(cfg, controller=None):
    """Build the canonical per-frame pipeline.

    Creates exactly one detector, one tracker, and (when no controller is
    supplied) one controller — callers must reuse the returned object rather
    than constructing components separately.
    """
    if controller is None:
        controller = CameraController(cfg)
    return SearchTrackPipeline(cfg, controller=controller)


__all__ = [
    "make_detector",
    "make_tracker",
    "make_controller",
    "make_camera",
    "make_pipeline",
]
