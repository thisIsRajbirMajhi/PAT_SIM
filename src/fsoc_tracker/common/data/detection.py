from dataclasses import dataclass
from typing import Optional, Tuple


@dataclass
class Detection:
    valid: bool
    centroid_px: Optional[Tuple[float, float]] = None
    bbox: Optional[Tuple[int, int, int, int]] = None  # x,y,w,h
    confidence: float = 0.0
    score: float = 0.0
    area: float = 0.0
