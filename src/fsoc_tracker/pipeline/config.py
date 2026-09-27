"""Canonical defaults for the Pipeline module.

Single source of truth remains config/defaults.py:DEFAULT_CONFIG;
re-exported here for discoverability and standalone use.
"""
from ..config.defaults import DEFAULT_CONFIG

DETECTOR_DEFAULTS = DEFAULT_CONFIG["detector"]
TRACKER_DEFAULTS = DEFAULT_CONFIG["tracker"]
CONTROLLER_DEFAULTS = DEFAULT_CONFIG["controller"]


def get_detector(cfg):
    return cfg.get("detector", {})


def get_tracker(cfg):
    return cfg.get("tracker", {})


__all__ = ["DETECTOR_DEFAULTS", "TRACKER_DEFAULTS", "CONTROLLER_DEFAULTS", "get_detector", "get_tracker"]
