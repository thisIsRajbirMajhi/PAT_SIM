"""Frame-level geometric jitter — canonical implementation (moved from environment/disturbances/jitter.py)."""
import cv2
import numpy as np


def apply_jitter(img, jitter_px, rng):
    if jitter_px <= 0:
        return img
    dx = int(rng.integers(-int(jitter_px), int(jitter_px) + 1))
    dy = int(rng.integers(-int(jitter_px), int(jitter_px) + 1))
    if dx == 0 and dy == 0:
        return img
    h, w = img.shape
    M = np.float32([[1, 0, dx], [0, 1, dy]])
    return cv2.warpAffine(img, M, (w, h), borderMode=cv2.BORDER_REFLECT_101)
