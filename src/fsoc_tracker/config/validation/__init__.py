"""Legacy compatibility: canonical implementation lives in pat_common.config.validation."""
from pat_common.config.validation import (
    validate_controller,
    validate_disturbances,
    validate_environment,
    validate_scene,
    validate_target,
)

__all__ = [
    "validate_controller",
    "validate_disturbances",
    "validate_environment",
    "validate_scene",
    "validate_target",
]
