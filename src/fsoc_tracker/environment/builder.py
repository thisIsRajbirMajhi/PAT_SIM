"""Orchestrator for static environment-base construction + rebuild detection."""
from .background.base import build_base


def build_environment_base(cfg, seed):
    """Build the static world base image (background + texture + stars + vignetting)."""
    w = cfg["world"]["width"]
    h = cfg["world"]["height"]
    return build_base(w, h, cfg, seed)


def environment_changed(old_cfg, new_cfg):
    """True if any environment/world field affecting the static base changed."""
    return old_cfg.get("environment", {}) != new_cfg.get("environment", {}) or (
        old_cfg["world"]["width"],
        old_cfg["world"]["height"],
        old_cfg["world"].get("background", 18),
    ) != (
        new_cfg["world"]["width"],
        new_cfg["world"]["height"],
        new_cfg["world"].get("background", 18),
    )


__all__ = ["build_environment_base", "environment_changed"]
