from typing import Any, Dict

from .validation import validate_disturbances, validate_environment, validate_scene, validate_target


def validate_config(cfg: Dict[str, Any]) -> Dict[str, Any]:
    validate_scene(cfg)
    validate_target(cfg)
    validate_disturbances(cfg)
    validate_environment(cfg)
    return cfg
