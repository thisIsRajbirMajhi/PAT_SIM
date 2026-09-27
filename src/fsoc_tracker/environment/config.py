"""Canonical defaults for the Environment module.

Single source of truth remains config/defaults.py:DEFAULT_CONFIG;
these are deep copies for discoverability and standalone use — mutating
them never affects the global DEFAULT_CONFIG.

Accessors delegate to config/accessors.py (single home for get_* helpers).
"""
import copy

from ..config.accessors import (
    get_atmosphere as _get_atmosphere,
    get_environment as _get_environment,
    get_noise as _get_noise,
    get_platform as _get_platform,
)
from ..config.defaults import DEFAULT_CONFIG

ENVIRONMENT_DEFAULTS = copy.deepcopy(DEFAULT_CONFIG["environment"])
ATMOSPHERE_DEFAULTS = copy.deepcopy(DEFAULT_CONFIG["atmosphere"])
NOISE_DEFAULTS = copy.deepcopy(DEFAULT_CONFIG["noise"])
PLATFORM_DEFAULTS = copy.deepcopy(DEFAULT_CONFIG["platform"])
WORLD_DEFAULTS = copy.deepcopy(DEFAULT_CONFIG["world"])


def get_environment(cfg):
    env = _get_environment(cfg)
    return dict(env) if isinstance(env, dict) else {}


def get_atmosphere(cfg):
    atmo = _get_atmosphere(cfg)
    return dict(atmo) if isinstance(atmo, dict) else {"type": "clear", "strength": 0.0}


def get_noise(cfg):
    noise = _get_noise(cfg)
    return dict(noise) if isinstance(noise, dict) else {}


def get_platform(cfg):
    plat = _get_platform(cfg)
    return dict(plat) if isinstance(plat, dict) else {"type": "linear", "speed_px_per_frame": 0.0}


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
