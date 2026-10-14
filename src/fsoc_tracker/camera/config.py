"""Legacy compatibility: canonical implementation lives in pat_pipeline.camera.config."""
from pat_pipeline.camera.config import (
    CAMERA_DEFAULTS,
    CONTROLLER_DEFAULTS,
    get_camera,
    get_controller,
)

__all__ = ["CAMERA_DEFAULTS", "CONTROLLER_DEFAULTS", "get_camera", "get_controller"]
