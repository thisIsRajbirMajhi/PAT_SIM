"""Camera module — virtual-camera optics + gimbal controller in one place.

Layout:
    camera/
        optics/     VirtualCamera + pure pixel<->angle geometry
        control/    PIDController + CameraController (track PID + spiral search)
        config.py   defaults + cfg accessors (mirrors config/defaults.py)
        factory.py  make_camera(cfg) / make_controller(cfg)
"""
from .config import CAMERA_DEFAULTS, CONTROLLER_DEFAULTS, get_camera, get_controller
from .control import CameraController, PIDController
from .factory import make_camera, make_controller
from .optics import (
    VirtualCamera,
    angle_to_pixel,
    deg_per_px,
    focal_px_rad,
    pixel_to_angle,
    px_per_deg,
    viewport_bounds,
)

__all__ = [
    # optics
    "VirtualCamera",
    "px_per_deg",
    "deg_per_px",
    "pixel_to_angle",
    "angle_to_pixel",
    "viewport_bounds",
    "focal_px_rad",
    # control
    "PIDController",
    "CameraController",
    # config / factory
    "CAMERA_DEFAULTS",
    "CONTROLLER_DEFAULTS",
    "get_camera",
    "get_controller",
    "make_camera",
    "make_controller",
]
