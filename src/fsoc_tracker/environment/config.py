"""Canonical defaults for the Environment module.

Single source of truth remains config/defaults.py:DEFAULT_CONFIG;
these are re-exported here for discoverability and standalone use.
"""
from ..config.defaults import DEFAULT_CONFIG

ENVIRONMENT_DEFAULTS = DEFAULT_CONFIG["environment"]
ATMOSPHERE_DEFAULTS = DEFAULT_CONFIG["atmosphere"]
NOISE_DEFAULTS = DEFAULT_CONFIG["noise"]
PLATFORM_DEFAULTS = DEFAULT_CONFIG["platform"]
WORLD_DEFAULTS = DEFAULT_CONFIG["world"]


def get_environment(cfg):
    return cfg.get("environment", {})


def get_atmosphere(cfg):
    return cfg.get("atmosphere", {"type": "clear", "strength": 0.0})


def get_noise(cfg):
    return cfg.get("noise", {})


def get_platform(cfg):
    return cfg.get("platform", {"type": "linear", "speed_px_per_frame": 0.0})


__all__ = [
    "ENVIRONMENT_DEFAULTS",
    "ATMOSPHERE_DEFAULTS",
    "NOISE_DEFAULTS",
    "PLATFORM_DEFAULTS",
    "WORLD_DEFAULTS",
    "get_environment",
    "get_atmosphere",
    "get_noise",
    "get_platform",
]
