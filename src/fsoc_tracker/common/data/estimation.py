from dataclasses import dataclass, field
from typing import Optional, Tuple

import numpy as np

from ..enums.tracking import TrackingState


@dataclass
class Estimate:
    pos_px: Optional[Tuple[float, float]] = None
    pos_angle: Tuple[float, float] = (0.0, 0.0)  # alpha, beta in degrees
    vel_angle: Tuple[float, float] = (0.0, 0.0)
    covariance: np.ndarray = field(default_factory=lambda: np.eye(4))
    model_probs: Tuple[float, float, float] = (0.33, 0.33, 0.34)
    tracking_state: TrackingState = TrackingState.SEARCHING
    innovation: float = 0.0
