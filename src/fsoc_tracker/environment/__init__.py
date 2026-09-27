"""Environment module — background scene construction lives here.

Disturbances (platform / jitter / atmosphere / sensor noise) are NOT
implemented here: single canonical home is disturbances/. This package
re-exports them for convenience only.

Structured layout:
    environment/
        background/      static scene: base, gradient, stars, vignetting
        builder.py       static-base orchestrator used by World
        config.py        defaults + cfg accessors (mirrors config/defaults.py)
"""
from ..disturbances import (
    PlatformMotion,
    apply_atmosphere,
    apply_gaussian,
    apply_jitter,
    apply_poisson,
    apply_salt_pepper,
)
from .background import add_stars, apply_twinkle, apply_vignetting, build_base, make_gradient
from .builder import build_environment_base, environment_changed
from .config import (
    ATMOSPHERE_DEFAULTS,
    ENVIRONMENT_DEFAULTS,
    NOISE_DEFAULTS,
    PLATFORM_DEFAULTS,
    WORLD_DEFAULTS,
    get_atmosphere,
    get_environment,
    get_noise,
    get_platform,
)

__all__ = [
    # background
    "build_base",
    "make_gradient",
    "add_stars",
    "apply_twinkle",
    "apply_vignetting",
    # atmosphere
    "apply_atmosphere",
    # sensor
    "apply_gaussian",
    "apply_salt_pepper",
    "apply_poisson",
    # disturbances
    "apply_jitter",
    "PlatformMotion",
    # builder / config
    "build_environment_base",
    "environment_changed",
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
