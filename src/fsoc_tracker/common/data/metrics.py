from dataclasses import dataclass
from typing import Optional

from ..enums.tracking import TrackingState


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
