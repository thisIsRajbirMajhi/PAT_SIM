"""pat_common — dependency-free shared core (stdlib + numpy only).

Single source of truth for the data types, tracking enum, canonical
vocabularies, visibility-schedule helpers, and configuration used by both
pat_pipeline and fsoc_tracker. Importing this package never pulls in GUI,
simulator, or Qt code.
"""
from .enums import TrackingState
from .kinds import (
    FIGURE_8_ALIASES,
    PLATFORM_TYPES,
    TRAJECTORY_TYPES,
    normalize_platform_type,
    normalize_trajectory_type,
)
from .types import (
    ControlCommand,
    Detection,
    Estimate,
    Frame,
    GroundTruth,
    MetricsFrame,
)
from .visibility import (
    BLINK_DUTY,
    get_blink_rate,
    get_visibility_schedule,
    is_blink_off,
    is_hidden,
    validate_visibility_schedule,
)

__all__ = [
    "TrackingState",
    "Frame",
    "GroundTruth",
    "Detection",
    "Estimate",
    "ControlCommand",
    "MetricsFrame",
    "TRAJECTORY_TYPES",
    "normalize_trajectory_type",
    "PLATFORM_TYPES",
    "FIGURE_8_ALIASES",
    "normalize_platform_type",
    "BLINK_DUTY",
    "get_blink_rate",
    "get_visibility_schedule",
    "is_blink_off",
    "is_hidden",
    "validate_visibility_schedule",
]
