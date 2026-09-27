"""Canonical defaults for the Camera module.

Single source of truth remains config/defaults.py:DEFAULT_CONFIG;
re-exported here for discoverability and standalone use.
"""
from ..config.defaults import DEFAULT_CONFIG

CAMERA_DEFAULTS = DEFAULT_CONFIG["camera"]
CONTROLLER_DEFAULTS = DEFAULT_CONFIG["controller"]


def get_camera(cfg):
    return cfg.get("camera", {})


def get_controller(cfg):
    return cfg.get("controller", {})


__all__ = ["CAMERA_DEFAULTS", "CONTROLLER_DEFAULTS", "get_camera", "get_controller"]
