"""Lens vignetting (moved from simulation/world.py)."""
from functools import lru_cache

import numpy as np


@lru_cache(maxsize=32)
def _vignette_mask(h, w, strength, radius, falloff, cx, cy):
    """Cached float32 vignette multiplier in [0, 1]."""
    ys, xs = np.ogrid[0:h, 0:w]
    xs = (xs.astype(np.float32) - np.float32(cx))
    ys = (ys.astype(np.float32) - np.float32(cy))
    max_d = float(np.hypot(max(cx, w - cx), max(cy, h - cy))) + 1e-6
    d = np.hypot(xs, ys).astype(np.float32) / np.float32(max_d)  # 0..1
    denom = 1.0 - radius
    if denom < 1e-3:
        return np.ones((h, w), dtype=np.float32)
    t = np.clip((d - radius) / denom, 0, 1).astype(np.float32)
    vig = 1.0 - np.float32(strength) * np.power(t, np.float32(falloff))
    return np.clip(vig, 0, 1).astype(np.float32)


def apply_vignetting(base, env):
    h, w = base.shape
    strength = float(np.clip(env.get("vignetting_strength", 0.42), 0, 0.95))
    radius = float(np.clip(env.get("vignetting_radius", 0.72), 0.05, 1.0))
    falloff = float(np.clip(env.get("vignetting_falloff", 2.0), 0.3, 6.0))
    cx = float(np.clip(env.get("vignetting_center_x", 0.5), 0, 1)) * w
    cy = float(np.clip(env.get("vignetting_center_y", 0.5), 0, 1)) * h
    if strength <= 0:
        return base.copy()
    if radius >= 0.999:
        return base.copy()
    vig = _vignette_mask(h, w, strength, radius, falloff, cx, cy)
    return (base.astype(np.float32) * vig).astype(np.uint8)


def clear_vignette_cache():
    _vignette_mask.cache_clear()
