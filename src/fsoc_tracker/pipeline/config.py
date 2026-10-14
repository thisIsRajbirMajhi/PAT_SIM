"""Legacy compatibility: canonical defaults live in pat_pipeline.config.

Single source of truth remains fsoc_tracker.config.defaults:DEFAULT_CONFIG.
"""
from pat_pipeline.config import (
    CONTROLLER_DEFAULTS,
    DETECTOR_DEFAULTS,
    TRACKER_DEFAULTS,
    get_detector,
    get_tracker,
)

__all__ = ["DETECTOR_DEFAULTS", "TRACKER_DEFAULTS", "CONTROLLER_DEFAULTS", "get_detector", "get_tracker"]
