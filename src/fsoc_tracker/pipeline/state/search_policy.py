"""Canonical search-vs-track policy shared by Tracker state and CameraController action.

This module owns the *spec* (which states mean "search", track gains, spiral params)
so tracking/ and camera/ never duplicate it. Pure + dependency-free: it must NOT
import camera/ or tracking/ (avoids cycles). CameraController reads its numbers
via get_search_params(cfg) — single source of truth.
"""
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, Optional

from ...common.enums import TrackingState

# States where the gimbal must run the search controller (mirrors CameraController.step).
SEARCH_STATES = frozenset({TrackingState.SEARCHING, TrackingState.REACQUIRING, TrackingState.FAILED})

# Expanding-spiral search params (canonical defaults; overridable via cfg["controller"]).
SEARCH_ANGLE_STEP = 0.45
SEARCH_RADIUS_STEP = 0.09
SEARCH_RADIUS_MAX = 4.5
SEARCH_RATE_SCALE = 0.85

# Full-coverage raster fallback (mirrors CameraController): after 3s of spiral
# without lock, sweep the whole world (boustrophedon) for cold-start targets.
SPIRAL_PHASE_S = 3.0
RASTER_PAN_SCALE = 0.9
RASTER_TILT_SCALE = 0.35

# Track-loop gains per state (mirrors CameraController: TEMP_LOST uses 0.55x PID).
TEMP_LOST_GAIN = 0.55

# Acquisition thresholds (mirrors TrackingStateMachine).
REQUIRED_CANDIDATE_FRAMES = 3
REQUIRED_LOCK_FRAMES = 5
CONFIDENCE_THRESHOLD = 0.45

SEARCH_DEFAULTS: Dict[str, Any] = {
    "search_angle_step": SEARCH_ANGLE_STEP,
    "search_radius_step": SEARCH_RADIUS_STEP,
    "search_radius_max": SEARCH_RADIUS_MAX,
    "search_rate_scale": SEARCH_RATE_SCALE,
    "spiral_phase_s": SPIRAL_PHASE_S,
    "raster_pan_scale": RASTER_PAN_SCALE,
    "raster_tilt_scale": RASTER_TILT_SCALE,
    "stare_rate_scale": 0.3,
    "intercept_gain": 2.0,
    "intercept_lead_s": 0.3,
    "unc_scale": 0.6,
    "unc_max_boost": 2.5,
    "fast_vel_deg_s": 1.0,
    "give_up_frames": 600,
}


def get_search_params(cfg: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Merge canonical defaults with cfg["controller"] search_* overrides."""
    out = dict(SEARCH_DEFAULTS)
    try:
        c = (cfg or {}).get("controller", {}) or {}
        for k in list(out.keys()):
            if k in c and c[k] is not None:
                out[k] = float(c[k])
    except Exception:
        pass
    return out


class SearchCase(str, Enum):
    TRACK = "TRACK"
    COAST = "COAST"
    STARE = "STARE"
    SLEW_PREDICT = "SLEW_PREDICT"
    EXPAND = "EXPAND"
    TILE = "TILE"
    INTERCEPT = "INTERCEPT"
    HOLD_SCHEDULED = "HOLD_SCHEDULED"
    GIVE_UP = "GIVE_UP"


# Prediction-driven moves are only trustworthy while the estimate is fresh:
# beyond this many missed frames the filter is coasting on stale velocity
# and must yield to full-world TILE (cf. X8: INTERCEPT chased a diverged
# prediction for hundreds of frames).
FRESH_MISS_LIMIT = 15
# ... and only when the camera itself was steady: without an ego-motion
# input the filter's velocity is polluted by gimbal rate, so after a fast
# sweep-past loss the "prediction" is mostly camera motion. PID tracking of
# real targets stays well under this; raster sweeps (~4 deg/s) exceed it.
STEADY_EGO_LIMIT = 1.5


@dataclass
class SearchContext:
    state: Any = None
    missed: int = 0
    det_valid: bool = False
    det_conf: float = 0.0
    cand_frames: int = 0
    locked_frames: int = 0
    innovation: float = 0.0
    cov_trace: float = 5.0
    vel_mag_deg_s: float = 0.0
    in_fov: Optional[bool] = None
    saturated: bool = False
    at_limit: bool = False
    latched: bool = False
    scheduled_hold: bool = False
    search_frames: int = 0
    # Gimbal ego-motion rate (deg/s) at decision time. The filter has no
    # ego-motion input, so after a sweep-past loss (raster slewing at ~4
    # deg/s) its velocity estimate is mostly camera motion, not target
    # motion — prediction moves are only safe when the camera was steady.
    ego_rate_deg_s: float = 0.0


def classify_search_case(ctx: SearchContext, params: Optional[Dict[str, Any]] = None) -> SearchCase:
    """Phase-1 classifier: map backend facts to one search behaviour."""
    p = params or SEARCH_DEFAULTS
    try:
        give_up = int(p.get("give_up_frames", 600))
    except Exception:
        give_up = 600
    try:
        fast_vel = float(p.get("fast_vel_deg_s", 1.0))
    except Exception:
        fast_vel = 1.0
    state = ctx.state
    # Non-search tracker states stay on the PID path (with STARE/COAST modifiers).
    if state not in SEARCH_STATES:
        if ctx.scheduled_hold:
            return SearchCase.HOLD_SCHEDULED
        if ctx.det_valid and ctx.det_conf <= CONFIDENCE_THRESHOLD:
            return SearchCase.STARE
        return SearchCase.TRACK
    # Search states below.
    if ctx.scheduled_hold:
        return SearchCase.HOLD_SCHEDULED
    if ctx.search_frames >= give_up or ctx.missed >= give_up:
        return SearchCase.GIVE_UP
    # World-edge hold only restrains prediction-driven moves (SLEW/INTERCEPT)
    # that can wedge the gimbal against the clamp chasing an out-of-world
    # estimate. The open-loop TILE sweep flips on its own schedule and must
    # keep sweeping; EXPAND spirals around boresight and never wedges.
    # Fast-target intercept and prediction slew need a latched AND fresh
    # estimate; anything older yields to TILE (stale velocity diverges).
    try:
        _fresh = (bool(ctx.latched) and int(ctx.missed) <= FRESH_MISS_LIMIT
                  and float(ctx.ego_rate_deg_s) <= STEADY_EGO_LIMIT)
    except Exception:
        _fresh = False
    if _fresh and ctx.in_fov is False:
        if ctx.at_limit:
            return SearchCase.HOLD_SCHEDULED
        try:
            if ctx.vel_mag_deg_s >= fast_vel:
                return SearchCase.INTERCEPT
        except Exception:
            pass
        return SearchCase.SLEW_PREDICT
    # Long/cold search: tile the world; short search: uncertainty-scaled spiral.
    try:
        spiral_frames = int(float(p.get("spiral_phase_s", 3.0)) * 30.0)
    except Exception:
        spiral_frames = 90
    if ctx.search_frames >= spiral_frames or (not ctx.latched and ctx.missed > 30):
        return SearchCase.TILE
    return SearchCase.EXPAND


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
        return "search: case-routed (slew/expand/tile/intercept/hold)"
    return "acquire: PID converging"


def describe_case(case) -> str:
    try:
        name = case.value if hasattr(case, "value") else str(case)
    except Exception:
        name = str(case)
    return {
        "TRACK": "track: PID",
        "COAST": "track: coast on prediction",
        "STARE": "track/search: freeze, confirm weak cue",
        "SLEW_PREDICT": "search: slew to prediction",
        "EXPAND": "search: uncertainty-scaled spiral",
        "TILE": "search: full-world tile sweep",
        "INTERCEPT": "search: velocity intercept",
        "HOLD_SCHEDULED": "search: hold (scheduled absence/limit)",
        "GIVE_UP": "search: timed out, holding",
    }.get(name, f"search: {name}")


__all__ = [
    "SEARCH_STATES",
    "SEARCH_ANGLE_STEP",
    "SEARCH_RADIUS_STEP",
    "SEARCH_RADIUS_MAX",
    "SEARCH_RATE_SCALE",
    "SPIRAL_PHASE_S",
    "RASTER_PAN_SCALE",
    "RASTER_TILT_SCALE",
    "TEMP_LOST_GAIN",
    "REQUIRED_CANDIDATE_FRAMES",
    "REQUIRED_LOCK_FRAMES",
    "CONFIDENCE_THRESHOLD",
    "SEARCH_DEFAULTS",
    "FRESH_MISS_LIMIT",
    "STEADY_EGO_LIMIT",
    "SearchCase",
    "SearchContext",
    "classify_search_case",
    "get_search_params",
    "describe_case",
    "is_search_state",
    "is_track_state",
    "track_gain",
    "describe_state",
]
