"""Searching-to-tracking pipeline — single canonical home for the full PAT sense-decide-act chain.

Layout:
    pipeline/
        detection/     BeaconDetector (threshold + connected-components + scoring)
        estimation/    SimpleEKF (6-state angle filter) + IMM (CV/CA/MN fusion)
        state/         TrackingStateMachine (SEARCHING->CANDIDATE->ACQUIRING->LOCKED,
                       TEMP_LOST/REACQUIRING/FAILED) + search_policy (canonical
                       search-vs-track spec shared with camera/ gimbal)
        track/         Tracker (IMM predict/update + state machine -> Estimate)
        orchestration/ SearchTrackPipeline (frame -> detection -> estimate -> command;
                       controller injected from camera/ to avoid cycles)
        config.py      detector/tracker defaults + accessors (mirrors config/defaults.py)
        factory.py     make_detector()/make_tracker()/make_pipeline()

Shared-ownership rule: the gimbal action itself stays in
camera/ (CameraController); this package owns the search-vs-track *decision*
spec (state/search_policy) plus the end-to-end tick orchestration.
"""
from .config import CONTROLLER_DEFAULTS, DETECTOR_DEFAULTS, TRACKER_DEFAULTS, get_detector, get_tracker
from .detection import BeaconDetector
from .estimation import IMM, SimpleEKF
from .factory import make_detector, make_pipeline, make_tracker
from .orchestration import SearchTrackPipeline
from .state import (
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
from .track import Tracker

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
