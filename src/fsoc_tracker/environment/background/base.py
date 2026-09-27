"""Static world-base assembly: flat/gradient + texture + gain/offset + stars + vignetting."""
import cv2
import numpy as np

from .gradient import make_gradient
from .stars import add_stars
from .vignetting import apply_vignetting


def build_base(w, h, cfg, seed):
    env = cfg.get("environment", {})
    bg = int(cfg["world"].get("background", 18))

    # 1) Gradient or flat
    if env.get("gradient_enabled"):
        base = make_gradient(w, h, env, bg)
    else:
        base = np.full((h, w), bg, dtype=np.uint8)

    # 2) Subtle texture (sensor non-uniformity)
    rng = np.random.default_rng(seed)
    noise = rng.integers(0, 6, size=(h, w), dtype=np.uint8)
    base = cv2.add(base, noise)

    # 3) Brightness gain/offset on world base (before stars/vignetting, keeps star contrast)
    gain = float(env.get("brightness_gain", 1.0))
    offset = int(env.get("brightness_offset", 0))
    if abs(gain - 1.0) > 1e-6 or offset != 0:
        base = np.clip(base.astype(np.float32) * gain + offset, 0, 255).astype(np.uint8)

    # 4) Stars clutter (static)
    if env.get("stars_enabled"):
        base = add_stars(base, env, seed)

    # 5) Vignetting (after stars so stars also vignetted like lens)
    if env.get("vignetting_enabled"):
        base = apply_vignetting(base, env)

    return base
