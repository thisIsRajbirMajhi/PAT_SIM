"""Orchestrator for static environment-base construction + rebuild detection."""
from .background.base import build_base, build_base_with_mask

# Keys that affect the cached static base. Per-frame-only keys
# (stars_twinkle, stars_twinkle_amount) are intentionally excluded.
STATIC_ENV_KEYS = frozenset({
    "gradient_enabled", "gradient_type", "gradient_top", "gradient_bottom",
    "gradient_angle", "gradient_center_x", "gradient_center_y",
    "texture_enabled", "texture_strength",
    "stars_enabled", "stars_density", "stars_brightness",
    "stars_min_mag", "stars_max_mag", "stars_seed", "stars_max_count",
    "vignetting_enabled", "vignetting_strength", "vignetting_radius",
    "vignetting_falloff", "vignetting_center_x", "vignetting_center_y",
    "brightness_gain", "brightness_offset",
})

_STATIC_WORLD_KEYS = ("width", "height", "background")


def build_environment_base(cfg, seed):
    """Build the static world base image (background + texture + stars + vignetting)."""
    w = cfg["world"]["width"]
    h = cfg["world"]["height"]
    return build_base(w, h, cfg, seed)


def build_environment_base_with_mask(cfg, seed):
    """Build static base plus star mask. Returns (base, star_mask)."""
    w = cfg["world"]["width"]
    h = cfg["world"]["height"]
    return build_base_with_mask(w, h, cfg, seed)


def environment_changed(old_cfg, new_cfg):
    """True if any static-base environment/world field changed."""
    old_env = old_cfg.get("environment", {}) if isinstance(old_cfg, dict) else {}
    new_env = new_cfg.get("environment", {}) if isinstance(new_cfg, dict) else {}
    keys = set(old_env) | set(new_env) | set(STATIC_ENV_KEYS)
    for k in keys:
        if k in STATIC_ENV_KEYS and old_env.get(k) != new_env.get(k):
            return True
    old_w = old_cfg.get("world", {}) if isinstance(old_cfg, dict) else {}
    new_w = new_cfg.get("world", {}) if isinstance(new_cfg, dict) else {}
    return any(old_w.get(k) != new_w.get(k) for k in _STATIC_WORLD_KEYS)


__all__ = [
    "build_environment_base",
    "build_environment_base_with_mask",
    "environment_changed",
    "STATIC_ENV_KEYS",
]
