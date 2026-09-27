from dataclasses import dataclass
from typing import Optional, Tuple

import numpy as np


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
