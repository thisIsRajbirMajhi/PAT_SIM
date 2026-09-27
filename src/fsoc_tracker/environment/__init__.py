"""Environment module — background scene construction lives here.

Disturbances (platform / jitter / atmosphere / sensor noise) are NOT
implemented here: single canonical home is disturbances/. Import them
from ``fsoc_tracker.disturbances`` directly.

Structured layout:
    environment/
        background/      static scene: base, gradient, stars, vignetting
        builder.py       static-base orchestrator used by World
        config.py        defaults + cfg accessors (mirrors config/defaults.py)
"""
import warnings

from .background import (
    add_stars,
    add_stars_with_mask,
    apply_twinkle,
    apply_vignetting,
    build_base,
    build_base_with_mask,
    build_star_mask,
    clear_vignette_cache,
    make_gradient,
)
from .builder import (
    STATIC_ENV_KEYS,
    build_environment_base,
    build_environment_base_with_mask,
    environment_changed,
)
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
    "build_base_with_mask",
    "make_gradient",
    "add_stars",
    "add_stars_with_mask",
    "build_star_mask",
    "apply_twinkle",
    "apply_vignetting",
    "clear_vignette_cache",
    # builder / config
    "build_environment_base",
    "build_environment_base_with_mask",
    "environment_changed",
    "STATIC_ENV_KEYS",
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

_DEPRECATED_DISTURBANCE_NAMES = {
    "PlatformMotion",
    "apply_atmosphere",
    "apply_gaussian",
    "apply_jitter",
    "apply_poisson",
    "apply_salt_pepper",
}


def __getattr__(name):
    # Backward-compat shim: `from fsoc_tracker.environment import apply_jitter`
    # still works but warns; canonical home is fsoc_tracker.disturbances.
    if name in _DEPRECATED_DISTURBANCE_NAMES:
        warnings.warn(
            f"fsoc_tracker.environment.{name} is deprecated; "
            f"import from fsoc_tracker.disturbances instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        from .. import disturbances as _d
        return getattr(_d, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
