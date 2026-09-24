from dataclasses import dataclass, field
from typing import Optional, Tuple, List
import numpy as np
from .enums import TrackingState

@dataclass
class Frame:
    image: np.ndarray
    frame_id: int
    timestamp: float
    source_name: str = "synthetic"

@dataclass
class GroundTruth:
    world_pos: Tuple[float, float]  # in world pixels
    visible: bool
    image_pos: Optional[Tuple[float, float]] = None  # in camera frame pixels, None if outside FOV

@dataclass
class Detection:
    valid: bool
    centroid_px: Optional[Tuple[float, float]] = None
    bbox: Optional[Tuple[int,int,int,int]] = None  # x,y,w,h
    confidence: float = 0.0
    score: float = 0.0
    area: float = 0.0

@dataclass
class Estimate:
    pos_px: Optional[Tuple[float, float]] = None
    pos_angle: Tuple[float, float] = (0.0, 0.0)  # alpha, beta in degrees
    vel_angle: Tuple[float, float] = (0.0, 0.0)
    covariance: np.ndarray = field(default_factory=lambda: np.eye(4))
    model_probs: Tuple[float, float, float] = (0.33, 0.33, 0.34)
    tracking_state: TrackingState = TrackingState.SEARCHING
    innovation: float = 0.0

@dataclass
class ControlCommand:
    pan_rate: float = 0.0  # deg/s
    tilt_rate: float = 0.0
    saturated: bool = False
    search_mode: bool = False

@dataclass
class MetricsFrame:
    frame_id: int
    timestamp: float
    error_px: Optional[float] = None
    error_angle: Optional[float] = None
    processing_ms: float = 0.0
    fps: float = 0.0
    lock_valid: bool = False
    tracking_state: TrackingState = TrackingState.SEARCHING
    detection_valid: bool = False
    pan_rate: float = 0.0
    tilt_rate: float = 0.0
