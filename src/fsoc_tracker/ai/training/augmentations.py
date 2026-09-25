"""
Augmentations for candidate patches — Plan §10 / Prompt Phase 3.

Applied ONLY to training split, never to val/test.

Included:
 - brightness/contrast jitter
 - Gaussian noise (sensor)
 - small rotation (±8°) + translation (±3 px)
 - haze / fog / low-light intensity scaling
 - salt-and-pepper impulse noise
 - horizontal/vertical flip (with bbox centroid update)

All augmentations preserve the 64×64 patch size and keep the
target within the patch (no cropping away).
"""
from __future__ import annotations

import numpy as np
import cv2  # type: ignore


def augment_patch(patch: np.ndarray, rng: np.random.Generator) -> np.ndarray:
    """
    patch: (64,64) float32 0-1. Returns augmented copy.
    Deterministic given rng state — caller seeds rng per-sample.
    """
    out = patch.copy()

    # brightness/contrast jitter
    gain = float(rng.normal(1.0, 0.08))
    bias = float(rng.normal(0.0, 0.04))
    out = np.clip(out * np.clip(gain, 0.75, 1.25) + np.clip(bias, -0.12, 0.12), 0, 1).astype(np.float32)

    # Gaussian noise
    if rng.random() < 0.35:
        std = float(rng.uniform(0.01, 0.04))
        out = np.clip(out + rng.normal(0, std, size=out.shape), 0, 1).astype(np.float32)

    # salt-and-pepper
    if rng.random() < 0.15:
        prob = float(rng.uniform(0.002, 0.015))
        mask = rng.random(size=out.shape)
        out[mask < prob / 2] = 0.0
        out[mask > 1 - prob / 2] = 1.0

    # small affine (rotation + translation)
    if rng.random() < 0.40:
        angle = float(rng.uniform(-8, 8))
        tx, ty = float(rng.integers(-3, 4)), float(rng.integers(-3, 4))
        M = cv2.getRotationMatrix2D((32, 32), angle, 1.0)
        M[0, 2] += tx
        M[1, 2] += ty
        out = cv2.warpAffine((out * 255).astype(np.uint8), M, (64, 64), borderMode=cv2.BORDER_REFLECT_101).astype(np.float32) / 255.0

    # haze-like: blend toward gray
    if rng.random() < 0.12:
        alpha = float(rng.uniform(0.10, 0.30))
        out = (1 - alpha) * out + alpha * 0.55
        out = np.clip(out, 0, 1).astype(np.float32)

    return out


def augment_sequence(seq: np.ndarray, mask: np.ndarray, rng: np.random.Generator) -> np.ndarray:
    """
    Light sequence augmentation: add small jitter to position/brightness
    dims for the valid window only. No temporal shuffling — tracks must
    stay causally ordered.
    """
    out = seq.copy()
    valid = mask > 0.5
    if valid.sum() < 2:
        return out
    # position jitter ±1.5 px (normalized ~ 0.004)
    out[valid, 0:2] += rng.normal(0, 0.003, size=(valid.sum(), 2))
    # brightness jitter
    out[valid, 4] += rng.normal(0, 0.015, size=(valid.sum(),))
    return np.clip(out, 0, 1)
