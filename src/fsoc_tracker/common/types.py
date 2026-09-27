"""Backward-compat shim: canonical types live in common/data/.

Use `from .data import ...` or `from ..common import ...` in new code.
"""
from .data import ControlCommand, Detection, Estimate, Frame, GroundTruth, MetricsFrame

__all__ = ["Frame", "GroundTruth", "Detection", "Estimate", "ControlCommand", "MetricsFrame"]
