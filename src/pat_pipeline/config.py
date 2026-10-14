"""Canonical defaults accessors for the pat_pipeline package.

Single source of truth remains fsoc_tracker.config.defaults:DEFAULT_CONFIG
(shared dependency, deliberately not copied). Re-exported here for
discoverability and standalone use.
"""
from fsoc_tracker.config.defaults import DEFAULT_CONFIG

DETECTOR_DEFAULTS = DEFAULT_CONFIG["detector"]
TRACKER_DEFAULTS = DEFAULT_CONFIG["tracker"]
CONTROLLER_DEFAULTS = DEFAULT_CONFIG["controller"]
CAMERA_DEFAULTS = DEFAULT_CONFIG["camera"]


def get_detector(cfg):
    return cfg.get("detector", {})


def get_tracker(cfg):
    return cfg.get("tracker", {})


def get_camera(cfg):
    return cfg.get("camera", {})


def get_controller(cfg):
    return cfg.get("controller", {})


__all__ = [
    "DETECTOR_DEFAULTS",
    "TRACKER_DEFAULTS",
    "CONTROLLER_DEFAULTS",
    "CAMERA_DEFAULTS",
    "get_detector",
    "get_tracker",
    "get_camera",
    "get_controller",
]
