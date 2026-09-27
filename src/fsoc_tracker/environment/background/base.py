"""Static world-base assembly: flat/gradient + texture + gain/offset + stars + vignetting."""
import numpy as np

from .gradient import make_gradient
from .stars import add_stars_with_mask
from .vignetting import apply_vignetting


def build_base(w, h, cfg, seed):
    base, _ = build_base_with_mask(w, h, cfg, seed)
    return base


def build_base_with_mask(w, h, cfg, seed):
    """Build static base plus boolean star mask (for star-only twinkle).

    Returns (base_uint8, star_mask_bool). star_mask is all-False when stars disabled.
    """
    env = cfg.get("environment", {})
    bg = int(np.clip(cfg["world"].get("background", 18), 0, 80))

    # 1) Gradient or flat
    if env.get("gradient_enabled"):
        base = make_gradient(w, h, env, bg)
    else:
        base = np.full((h, w), bg, dtype=np.uint8)

    # 2) Subtle texture (sensor non-uniformity), optional + configurable
    if env.get("texture_enabled", True):
        strength = int(env.get("texture_strength", 5))
        if strength > 0:
            rng = np.random.default_rng(int(seed))
            noise = rng.integers(0, strength + 1, size=(h, w)).astype(np.int16)
            base = np.clip(base.astype(np.int16) + noise, 0, 255).astype(np.uint8)

    # 3) Brightness gain/offset on world base (before stars/vignetting, keeps star contrast)
    gain = float(env.get("brightness_gain", 1.0))
    offset = float(env.get("brightness_offset", 0))
    if abs(gain - 1.0) > 1e-6 or offset != 0:
        base = np.clip(base.astype(np.float32) * gain + offset, 0, 255).astype(np.uint8)

    # 4) Stars clutter (static)
    star_mask = np.zeros((h, w), dtype=bool)
    if env.get("stars_enabled"):
        base, star_mask = add_stars_with_mask(base, env, seed)

    # 5) Vignetting (after stars so stars also vignetted like lens)
    if env.get("vignetting_enabled"):
        base = apply_vignetting(base, env)

    return base, star_mask
