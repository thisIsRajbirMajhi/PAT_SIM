"""Canonical defaults for the Disturbances module (shared by environment/camera/input).

Single source of truth remains config/defaults.py:DEFAULT_CONFIG;
deep copies are re-exported here so mutating them never affects globals.
Accessors return copies (mutating the result never mutates the cfg).
"""
import copy

from ..config.accessors import (
    get_atmosphere as _get_atmosphere,
    get_jitter as _get_jitter,
    get_noise as _get_noise,
    get_platform as _get_platform,
)
from ..config.defaults import DEFAULT_CONFIG

PLATFORM_DEFAULTS = copy.deepcopy(DEFAULT_CONFIG["platform"])
ATMOSPHERE_DEFAULTS = copy.deepcopy(DEFAULT_CONFIG["atmosphere"])
NOISE_DEFAULTS = copy.deepcopy(DEFAULT_CONFIG["noise"])
JITTER_DEFAULT = copy.deepcopy(DEFAULT_CONFIG["camera"].get("jitter_px", 0.0))


def get_platform(cfg):
    plat = _get_platform(cfg)
    return dict(plat) if isinstance(plat, dict) else {"type": "none", "speed_px_per_frame": 0.0}


def get_atmosphere(cfg):
    atmo = _get_atmosphere(cfg)
    return dict(atmo) if isinstance(atmo, dict) else {"type": "clear", "strength": 0.0}


def get_noise(cfg):
    noise = _get_noise(cfg)
    return dict(noise) if isinstance(noise, dict) else {}


def get_jitter(cfg):
    try:
        return float(_get_jitter(cfg))
    except (TypeError, ValueError):
        return 0.0


def _atmo_on(cfg):
    atmo = _get_atmosphere(cfg) or {}
    return atmo.get("type", "clear") != "clear" and float(atmo.get("strength", 0) or 0) > 0


def _noise_on(cfg):
    noise = _get_noise(cfg) or {}
    if noise.get("gaussian_enabled") and float(noise.get("gaussian_std", 0) or 0) > 0:
        return True
    if noise.get("salt_pepper_enabled") and float(noise.get("salt_pepper_prob", 0) or 0) > 0:
        return True
    return bool(noise.get("poisson"))


def _motion_on(cfg):
    from .platform.platform_motion import normalize_platform_type
    plat = _get_platform(cfg) or {}
    ptype = normalize_platform_type(plat.get("type", "none"))
    return ptype != "none" and float(plat.get("speed_px_per_frame", 0) or 0) > 0


def is_image_active(cfg):
    """True if any pixel-domain disturbance (atmosphere/sensor/jitter) is on."""
    return _atmo_on(cfg) or _noise_on(cfg) or get_jitter(cfg) > 0


def is_motion_active(cfg):
    """True if platform ego-motion geometry is on."""
    return _motion_on(cfg)


def is_disturbances_active(cfg):
    """True if any disturbance (image or motion) would alter the stream."""
    return is_image_active(cfg) or is_motion_active(cfg)


__all__ = [
    "PLATFORM_DEFAULTS",
    "ATMOSPHERE_DEFAULTS",
    "NOISE_DEFAULTS",
    "JITTER_DEFAULT",
    "get_platform",
    "get_atmosphere",
    "get_noise",
    "get_jitter",
    "is_image_active",
    "is_motion_active",
    "is_disturbances_active",
]
