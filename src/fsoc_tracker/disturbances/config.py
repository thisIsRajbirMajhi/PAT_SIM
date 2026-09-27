"""Canonical defaults for the Disturbances module (shared by environment/camera/input).

Single source of truth remains config/defaults.py:DEFAULT_CONFIG;
re-exported here for discoverability and standalone use.
"""
from ..config.defaults import DEFAULT_CONFIG

PLATFORM_DEFAULTS = DEFAULT_CONFIG["platform"]
ATMOSPHERE_DEFAULTS = DEFAULT_CONFIG["atmosphere"]
NOISE_DEFAULTS = DEFAULT_CONFIG["noise"]
# jitter lives under camera.jitter_px (spec ±20 px/frame max)
JITTER_DEFAULT = DEFAULT_CONFIG["camera"].get("jitter_px", 0.0)


def get_platform(cfg):
    return cfg.get("platform", {"type": "none", "speed_px_per_frame": 0.0})


def get_atmosphere(cfg):
    return cfg.get("atmosphere", {"type": "clear", "strength": 0.0})


def get_noise(cfg):
    return cfg.get("noise", {})


def get_jitter(cfg):
    return float(cfg.get("camera", {}).get("jitter_px", 0.0))


def is_disturbances_active(cfg):
    """True if any shared disturbance would alter a frame (fast path for pipeline)."""
    if get_jitter(cfg) > 0:
        return True
    atmo = get_atmosphere(cfg)
    if atmo.get("type", "clear") != "clear" and float(atmo.get("strength", 0)) > 0:
        return True
    noise = get_noise(cfg)
    if noise.get("gaussian_enabled") and float(noise.get("gaussian_std", 0)) > 0:
        return True
    if noise.get("salt_pepper_enabled") and float(noise.get("salt_pepper_prob", 0)) > 0:
        return True
    if noise.get("poisson"):
        return True
    plat = get_platform(cfg)
    if plat.get("type", "none") != "none" and float(plat.get("speed_px_per_frame", 0)) > 0:
        return True
    return False


__all__ = [
    "PLATFORM_DEFAULTS",
    "ATMOSPHERE_DEFAULTS",
    "NOISE_DEFAULTS",
    "JITTER_DEFAULT",
    "get_platform",
    "get_atmosphere",
    "get_noise",
    "get_jitter",
    "is_disturbances_active",
]
