"""Disturbances module — single canonical home for ALL shared disturbances.

Layout:
    disturbances/
        platform/    PlatformMotion (environment-side ego-motion -> perturbs camera centre)
        atmosphere/  apply_atmosphere (environment-side veil: haze/fog/rain/low_light)
        sensor/      apply_gaussian / apply_salt_pepper / apply_poisson (camera-side)
        frame/       apply_jitter (camera-side mount vibration)
        pipeline.py  apply_environment() + apply_camera() + apply_disturbances()
                     + DisturbancePipeline
                     (canonical order: atmosphere -> gaussian -> salt&pepper -> poisson -> jitter)
        config.py    defaults + getters + is_image_active/is_motion_active/is_disturbances_active
        factory.py   make_platform_motion(cfg, seed) / make_pipeline(cfg)

Shared-ownership rule: environment/ and camera/input MUST import from here —
no duplicated disturbance logic anywhere else.
"""
from .atmosphere import apply_atmosphere
from .config import (
    ATMOSPHERE_DEFAULTS,
    JITTER_DEFAULT,
    NOISE_DEFAULTS,
    PLATFORM_DEFAULTS,
    get_atmosphere,
    get_jitter,
    get_noise,
    get_platform,
    is_disturbances_active,
    is_image_active,
    is_motion_active,
)
from .factory import make_pipeline, make_platform_motion
from .frame import apply_jitter
from .pipeline import DisturbancePipeline, apply_camera, apply_disturbances, apply_environment
from .platform import PlatformMotion, normalize_platform_type
from .sensor import apply_gaussian, apply_poisson, apply_salt_pepper

__all__ = [
    # platform / frame
    "PlatformMotion",
    "normalize_platform_type",
    "apply_jitter",
    # atmosphere
    "apply_atmosphere",
    # sensor
    "apply_gaussian",
    "apply_salt_pepper",
    "apply_poisson",
    # pipeline / factory
    "apply_disturbances",
    "apply_environment",
    "apply_camera",
    "DisturbancePipeline",
    "make_pipeline",
    "make_platform_motion",
    # config
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
