"""Lens vignetting (moved from simulation/world.py)."""
import numpy as np


def apply_vignetting(base, env):
    h, w = base.shape
    strength = float(np.clip(env.get("vignetting_strength", 0.42), 0, 0.95))
    radius = float(np.clip(env.get("vignetting_radius", 0.72), 0.05, 1.0))
    falloff = float(np.clip(env.get("vignetting_falloff", 2.0), 0.3, 6.0))
    cx = float(np.clip(env.get("vignetting_center_x", 0.5), 0, 1)) * w
    cy = float(np.clip(env.get("vignetting_center_y", 0.5), 0, 1)) * h
    ys, xs = np.ogrid[0:h, 0:w]
    # normalized distance from center (0=center, 1=corner)
    max_d = np.hypot(max(cx, w - cx), max(cy, h - cy)) + 1e-6
    d = np.hypot(xs - cx, ys - cy) / max_d  # 0..1
    # mask: 1 inside radius, falloff outside
    t = np.clip((d - radius) / (1.0 - radius + 1e-6), 0, 1)
    # falloff curve: t^falloff
    vig = 1.0 - strength * np.power(t, falloff)
    vig = np.clip(vig, 0, 1).astype(np.float32)
    # apply
    out = (base.astype(np.float32) * vig).astype(np.uint8)
    return out
