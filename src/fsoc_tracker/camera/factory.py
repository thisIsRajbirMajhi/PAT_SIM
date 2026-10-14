"""Legacy compatibility: canonical implementation lives in pat_pipeline.camera.factory."""
from pat_pipeline.camera.factory import make_camera, make_controller

__all__ = ["make_camera", "make_controller"]
