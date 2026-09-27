"""Disturbances module — single canonical home for ALL shared disturbances.

Layout:
    disturbances/
        platform/    PlatformMotion (ego-motion / vibration -> perturbs camera centre)
        frame/       apply_jitter (geometric frame shift)
        atmosphere/  apply_atmosphere (haze/fog/rain/low_light/clear)
        sensor/      apply_gaussian / apply_salt_pepper / apply_poisson
        pipeline.py  apply_disturbances() + DisturbancePipeline
                     (canonical order: atmosphere -> gaussian -> salt&pepper -> poisson -> jitter)
        config.py    defaults + get_platform/get_atmosphere/get_noise/get_jitter/is_disturbances_active
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
)
from .factory import make_pipeline, make_platform_motion
from .frame import apply_jitter
from .pipeline import DisturbancePipeline, apply_disturbances
from .platform import PlatformMotion
from .sensor import apply_gaussian, apply_poisson, apply_salt_pepper

__all__ = [
    # platform / frame
    "PlatformMotion",
    "apply_jitter",
    # atmosphere
    "apply_atmosphere",
    # sensor
    "apply_gaussian",
    "apply_salt_pepper",
    "apply_poisson",
    # pipeline / factory
    "apply_disturbances",
    "DisturbancePipeline",
    "make_platform_motion",
    "make_pipeline",
    # config
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
