"""Legacy compatibility: canonical implementation lives in pat_pipeline.

All names below resolve to the same objects as their `pat_pipeline`
counterparts (verified by class-identity tests).
"""
from pat_pipeline.config import CONTROLLER_DEFAULTS, DETECTOR_DEFAULTS, TRACKER_DEFAULTS, get_detector, get_tracker
from pat_pipeline.detection import BeaconDetector
from pat_pipeline.estimation import IMM, SimpleEKF
from pat_pipeline.factory import make_detector, make_pipeline, make_tracker
from pat_pipeline.orchestration import SearchTrackPipeline
from pat_pipeline.state import (
    CONFIDENCE_THRESHOLD,
    REQUIRED_CANDIDATE_FRAMES,
    REQUIRED_LOCK_FRAMES,
    SEARCH_ANGLE_STEP,
    SEARCH_RADIUS_MAX,
    SEARCH_RADIUS_STEP,
    SEARCH_RATE_SCALE,
    SEARCH_STATES,
    TEMP_LOST_GAIN,
    TrackingStateMachine,
    describe_state,
    is_search_state,
    is_track_state,
    track_gain,
)
from pat_pipeline.track import Tracker

__all__ = [
    # detection
    "BeaconDetector",
    # estimation
    "SimpleEKF",
    "IMM",
    # state / search
    "TrackingStateMachine",
    "SEARCH_STATES",
    "SEARCH_ANGLE_STEP",
    "SEARCH_RADIUS_STEP",
    "SEARCH_RADIUS_MAX",
    "SEARCH_RATE_SCALE",
    "TEMP_LOST_GAIN",
    "REQUIRED_CANDIDATE_FRAMES",
    "REQUIRED_LOCK_FRAMES",
    "CONFIDENCE_THRESHOLD",
    "is_search_state",
    "is_track_state",
    "track_gain",
    "describe_state",
    # track
    "Tracker",
    # orchestration
    "SearchTrackPipeline",
    # config / factory
    "DETECTOR_DEFAULTS",
    "TRACKER_DEFAULTS",
    "CONTROLLER_DEFAULTS",
    "get_detector",
    "get_tracker",
    "make_detector",
    "make_tracker",
    "make_pipeline",
]
