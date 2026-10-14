"""Legacy compatibility: canonical implementation lives in pat_pipeline.camera.control."""
from pat_pipeline.camera.control.camera_controller import CameraController
from pat_pipeline.camera.control.pid import PIDController

__all__ = ["CameraController", "PIDController"]
