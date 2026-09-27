"""Canonical search-vs-track policy shared by Tracker state and CameraController action.

This module owns the *spec* (which states mean "search", track gains, spiral params)
so tracking/ and camera/ never duplicate it. Pure + dependency-free: it must NOT
import camera/ or tracking/ (avoids cycles). CameraController keeps its own
verbatim implementation whose constants mirror these values.
"""
from ...common.enums import TrackingState

# States where the gimbal must run the expanding-spiral search (mirrors CameraController.step).
SEARCH_STATES = frozenset({TrackingState.SEARCHING, TrackingState.REACQUIRING, TrackingState.FAILED})

# Expanding-spiral search params (mirrors camera/control/camera_controller.py).
SEARCH_ANGLE_STEP = 0.32
SEARCH_RADIUS_STEP = 0.06
SEARCH_RADIUS_MAX = 4.5
SEARCH_RATE_SCALE = 0.85

# Track-loop gains per state (mirrors CameraController: TEMP_LOST uses 0.55x PID).
TEMP_LOST_GAIN = 0.55

# Acquisition thresholds (mirrors TrackingStateMachine).
REQUIRED_CANDIDATE_FRAMES = 3
REQUIRED_LOCK_FRAMES = 5
CONFIDENCE_THRESHOLD = 0.45


def is_search_state(state):
    return state in SEARCH_STATES


def is_track_state(state):
    return not is_search_state(state)


def track_gain(state):
    if state == TrackingState.TEMP_LOST:
        return TEMP_LOST_GAIN
    return 1.0


def describe_state(state):
    if state == TrackingState.LOCKED:
        return "track: PID locked"
    if state == TrackingState.TEMP_LOST:
        return "track: coast 0.55x PID"
    if is_search_state(state):
        return "search: expanding spiral"
    return "acquire: PID converging"


__all__ = [
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
]
