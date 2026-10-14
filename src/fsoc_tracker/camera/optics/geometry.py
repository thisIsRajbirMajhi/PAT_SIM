"""Legacy compatibility: canonical implementation lives in pat_pipeline.camera.optics."""
from pat_pipeline.camera.optics import (
    VirtualCamera,
    angle_to_pixel,
    deg_per_px,
    focal_px_rad,
    pixel_to_angle,
    px_per_deg,
    viewport_bounds,
)

__all__ = [
    "VirtualCamera",
    "px_per_deg",
    "deg_per_px",
    "pixel_to_angle",
    "angle_to_pixel",
    "viewport_bounds",
    "focal_px_rad",
]
