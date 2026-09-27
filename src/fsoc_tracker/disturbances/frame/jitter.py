"""Frame-level geometric jitter — camera mount vibration (camera-side).

Applied post-viewport as a sub-pixel rigid shift. Caller passes `rng`
so streams stay reproducible. Supports gray and color images.
"""
import cv2
import numpy as np


def apply_jitter(img, jitter_px, rng):
    jitter_px = float(jitter_px)
    if jitter_px <= 0:
        return img
    dx = float(rng.uniform(-jitter_px, jitter_px))
    dy = float(rng.uniform(-jitter_px, jitter_px))
    if dx == 0 and dy == 0:
        return img
    h, w = img.shape[:2]
    M = np.float32([[1, 0, dx], [0, 1, dy]])
    if img.ndim == 2:
        return cv2.warpAffine(img, M, (w, h), borderMode=cv2.BORDER_REFLECT_101)
    # color: warp each channel (warpAffine is single-channel)
    channels = cv2.split(img) if img.shape[2] <= 4 else [img[:, :, i] for i in range(img.shape[2])]
    warped = [cv2.warpAffine(c, M, (w, h), borderMode=cv2.BORDER_REFLECT_101) for c in channels]
    if img.shape[2] <= 4:
        return cv2.merge(warped)
    return np.stack(warped, axis=-1)
