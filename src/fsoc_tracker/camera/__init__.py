"""Legacy compatibility: canonical implementation lives in pat_pipeline.camera.

All names below resolve to the same objects as their `pat_pipeline.camera`
counterparts (verified by class-identity tests).
"""
from pat_pipeline.camera import (
    CAMERA_DEFAULTS,
    CONTROLLER_DEFAULTS,
    CameraController,
    PIDController,
    VirtualCamera,
    angle_to_pixel,
    deg_per_px,
    focal_px_rad,
    get_camera,
    get_controller,
    make_camera,
    make_controller,
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
