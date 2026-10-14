"""Searching-to-tracking pipeline — canonical home for the PAT sense-decide-act chain.

Layout:
    pat_pipeline/
        detection/     BeaconDetector (threshold + connected-components + scoring)
        estimation/    SimpleEKF (6-state angle filter) + IMM (CV/CA/MN fusion)
        state/         TrackingStateMachine (SEARCHING->CANDIDATE->ACQUIRING->LOCKED,
                       TEMP_LOST/REACQUIRING/FAILED) + search_policy (canonical
                       search-vs-track spec shared with the gimbal)
        track/         Tracker (IMM predict/update + state machine -> Estimate)
                       + DisplayTracker/DisplayStatus (GUI-free status truth)
        orchestration/ SearchTrackPipeline (frame -> detection -> estimate ->
                       command; controller injected to avoid cycles)
        camera/        VirtualCamera + geometry + PIDController + CameraController
        config.py      detector/tracker/camera/controller defaults + accessors
                       (values owned by fsoc_tracker.config.defaults)
        factory.py     make_detector()/make_tracker()/make_controller()/
                       make_camera()/make_pipeline()

Shared-ownership rule: genuinely shared, GUI-free definitions (common types,
enums, config defaults/loading, target visibility) stay in `fsoc_tracker`
and are imported, never copied. The gimbal action lives in
pat_pipeline.camera; this package owns the search-vs-track decision spec
(state/search_policy) plus the end-to-end tick orchestration.

Legacy `fsoc_tracker.pipeline.*` and `fsoc_tracker.camera.*` paths remain as
thin compatibility re-exports resolving to these canonical objects.
"""
from .camera import (
    CAMERA_DEFAULTS,
    CONTROLLER_DEFAULTS,
    CameraController,
    PIDController,
    VirtualCamera,
    angle_to_pixel,
    deg_per_px,
    focal_px_rad,
    get_camera,
    get_controller,
    make_camera,
    make_controller,
    pixel_to_angle,
    px_per_deg,
    viewport_bounds,
)
from .config import (
    DETECTOR_DEFAULTS,
    TRACKER_DEFAULTS,
    get_detector,
    get_tracker,
)
from .detection import BeaconDetector
from .estimation import IMM, SimpleEKF
from .factory import (
    make_detector,
    make_pipeline,
    make_tracker,
)
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
from .track import (
    DisplayState,
    DisplayStatus,
    DisplayTracker,
    STATUS_META,
    Tracker,
    TrackTelemetry,
)

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
    # track / display
    "Tracker",
    "DisplayTracker",
    "DisplayStatus",
    "DisplayState",
    "TrackTelemetry",
    "STATUS_META",
    # orchestration
    "SearchTrackPipeline",
    # camera
    "VirtualCamera",
    "px_per_deg",
    "deg_per_px",
    "pixel_to_angle",
    "angle_to_pixel",
    "viewport_bounds",
    "focal_px_rad",
    "PIDController",
    "CameraController",
    # config / factory
    "DETECTOR_DEFAULTS",
    "TRACKER_DEFAULTS",
    "CONTROLLER_DEFAULTS",
    "CAMERA_DEFAULTS",
    "get_detector",
    "get_tracker",
    "get_camera",
    "get_controller",
    "make_detector",
    "make_tracker",
    "make_controller",
    "make_camera",
    "make_pipeline",
]
