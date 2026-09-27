"""Sensor noise models — canonical implementation (moved from environment/sensor/noise.py)."""
import numpy as np


def apply_gaussian(img, std, rng):
    if std <= 0:
        return img
    noise = rng.normal(0, std, img.shape).astype(np.float32)
    out = img.astype(np.float32) + noise
    return np.clip(out, 0, 255).astype(np.uint8)


def apply_salt_pepper(img, prob, rng):
    if prob <= 0:
        return img
    out = img.copy()
    h, w = img.shape
    num = int(prob * h * w)
    # salt
    ys = rng.integers(0, h, size=num)
    xs = rng.integers(0, w, size=num)
    vals = rng.integers(0, 2, size=num)  # 0 pepper 1 salt
    out[ys[vals == 1], xs[vals == 1]] = 255
    out[ys[vals == 0], xs[vals == 0]] = 0
    return out


def apply_poisson(img, rng):
    # scale to simulate photon noise: convert to float, apply poisson approx
    # Use numpy poisson on scaled image
    # Prevent overflow: use moderate scaling
    scaled = img.astype(np.float32) / 255.0 * 30.0
    noisy = rng.poisson(scaled).astype(np.float32)
    noisy = noisy / 30.0 * 255.0
    return np.clip(noisy, 0, 255).astype(np.uint8)
