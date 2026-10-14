"""Legacy compatibility: canonical implementation lives in pat_common.types."""
from pat_common.types import (
    ControlCommand,
    Detection,
    Estimate,
    Frame,
    GroundTruth,
    MetricsFrame,
)

__all__ = ["Frame", "GroundTruth", "Detection", "Estimate", "ControlCommand", "MetricsFrame"]
