"""Legacy compatibility: canonical implementation lives in pat_common.config."""
from pat_common.config.accessors import (
    get_atmosphere,
    get_camera,
    get_controller,
    get_detector,
    get_environment,
    get_experiment,
    get_jitter,
    get_noise,
    get_platform,
    get_target,
    get_tracker,
    get_visibility_schedule,
    get_world,
)

__all__ = [
    "get_world",
    "get_camera",
    "get_target",
    "get_platform",
    "get_noise",
    "get_atmosphere",
    "get_environment",
    "get_detector",
    "get_tracker",
    "get_controller",
    "get_experiment",
    "get_jitter",
    "get_visibility_schedule",
]
