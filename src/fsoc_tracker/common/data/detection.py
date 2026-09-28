from dataclasses import dataclass, field
from typing import List, Optional, Tuple


@dataclass
class Detection:
    valid: bool
    centroid_px: Optional[Tuple[float, float]] = None
    bbox: Optional[Tuple[int, int, int, int]] = None  # x,y,w,h
    confidence: float = 0.0
    score: float = 0.0
    area: float = 0.0
    # blobs discarded by the area/shape gates, for the REJECTED overlay:
    # list of (x, y, w, h, reason) with reason in {"SMALL", "LARGE", "SHAPE"}
    rejected: List[Tuple[int, int, int, int, str]] = field(default_factory=list)
