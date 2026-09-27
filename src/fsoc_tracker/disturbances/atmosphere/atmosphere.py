"""Atmospheric effects — environment-side (world) disturbance.

Physically this acts on incoming light before the sensor, but it is
applied post-viewport: for a spatially uniform veil
crop-then-veil == veil-then-crop, so operating on the small viewport
is exactly equivalent and ~50x cheaper than processing the 2000px world.

Models (strength in [0, 1]):
    haze:      veil + contrast loss (Koschmieder-like: I' = I*t + A*(1-t))
    fog:       stronger veil than haze
    rain:      contrast loss + sparse bright streaks (rng-driven, reproducible)
    low_light: global dimming; sensor noise (if enabled) then dominates,
               which is the realistic low-light behavior
No cv2 dependency; O(N) per frame. Gray and color safe.
"""
import numpy as np


def apply_atmosphere(img, atmo_type, strength, rng=None):
    if atmo_type == "clear" or float(strength) <= 0:
        return img
    strength = float(np.clip(strength, 0, 1))
    out = img.astype(np.float32)
    if atmo_type == "haze":
        t = 1.0 - 0.5 * strength  # transmission
        out = out * t + 60.0 * strength
    elif atmo_type == "fog":
        t = 1.0 - 0.65 * strength
        out = out * t + 90.0 * strength
    elif atmo_type == "rain":
        out = out * (1.0 - 0.3 * strength)
        out = _add_rain_streaks(out, strength, rng)
    elif atmo_type == "low_light":
        out = out * (0.45 + 0.55 * (1.0 - strength))
    # unknown types pass through (validation rejects them at load time)
    return np.clip(out, 0, 255).astype(np.uint8)


def _add_rain_streaks(out, strength, rng):
    h, w = out.shape[:2]
    rng = np.random.default_rng() if rng is None else rng
    n = int(120 * strength)
    if n <= 0:
        return out
    xs = rng.integers(0, w, size=n)
    ys = rng.integers(0, max(h - 12, 1), size=n)
    streak_val = 180.0 * 0.25 * strength
    for x, y in zip(xs.tolist(), ys.tolist()):
        y1 = min(h, y + 12)
        seg = out[y:y1, x] if out.ndim == 2 else out[y:y1, x, :]
        seg += streak_val * np.linspace(1.0, 0.3, y1 - y).reshape(-1, *([1] * (seg.ndim - 1)))
    return out
