"""Sensor noise models — canonical implementation.

Camera-side effects applied post-viewport (after atmosphere + geometry).
All functions are pure (no hidden global RNG): caller passes `rng`.
Supports gray (H, W) and color (H, W, C) uint8 images.
"""
import numpy as np


def apply_gaussian(img, std, rng):
    """Additive white Gaussian noise (read noise), sigma in gray levels."""
    std = float(std)
    if std <= 0:
        return img
    noise = rng.normal(0.0, std, img.shape).astype(np.float32)
    return np.clip(img.astype(np.float32) + noise, 0, 255).astype(np.uint8)


def apply_salt_pepper(img, prob, rng):
    """Impulse noise: random pixels forced to 0 or 255 (dead/hot pixels)."""
    prob = float(prob)
    if prob <= 0:
        return img
    out = img.copy()
    h, w = img.shape[:2]
    num = int(prob * h * w)
    if num <= 0:
        return out
    ys = rng.integers(0, h, size=num)
    xs = rng.integers(0, w, size=num)
    salt = rng.integers(0, 2, size=num).astype(bool)  # True=salt, False=pepper
    if out.ndim == 2:
        out[ys[salt], xs[salt]] = 255
        out[ys[~salt], xs[~salt]] = 0
    else:
        out[ys[salt], xs[salt]] = 255
        out[ys[~salt], xs[~salt]] = 0
    return out


def apply_poisson(img, rng, gain=30.0):
    """Photon shot noise: Poisson(stat) with peak ~gain photo-electrons.

    gain trades realism vs cost; 30 matches the previous behavior.
    """
    gain = float(gain)
    if gain <= 0:
        return img.copy() if isinstance(img, np.ndarray) else img
    lam = img.astype(np.float32) / 255.0 * gain
    noisy = rng.poisson(lam).astype(np.float32)
    return np.clip(noisy / gain * 255.0, 0, 255).astype(np.uint8)
