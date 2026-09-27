"""Atmospheric effects — canonical implementation (moved from environment/atmosphere/atmosphere.py)."""
import cv2
import numpy as np


def apply_atmosphere(img, atmo_type, strength):
    if atmo_type == "clear" or strength <= 0:
        return img
    out = img.astype(np.float32)
    if atmo_type == "haze":
        # reduce contrast, add veil
        out = out * (1 - 0.5 * strength) + 60 * strength
        out = cv2.GaussianBlur(out.astype(np.uint8), (5, 5), 0).astype(np.float32) * 0.15 + out * 0.85
    elif atmo_type == "fog":
        out = out * (1 - 0.65 * strength) + 90 * strength
        out = cv2.GaussianBlur(out.astype(np.uint8), (7, 7), 0).astype(np.float32) * 0.25 + out * 0.75
    elif atmo_type == "rain":
        # contrast reduction + streaks
        out = out * (1 - 0.3 * strength)
        # add vertical streaks
        h, w = img.shape
        streak = np.zeros_like(img, dtype=np.uint8)
        for _ in range(int(120 * strength)):
            x = np.random.randint(0, w)
            y = np.random.randint(0, h - 20)
            cv2.line(streak, (x, y), (x + 2, y + 12), 180, 1)
        out = cv2.addWeighted(out.astype(np.uint8), 1, streak, 0.25 * strength, 0).astype(np.float32)
    elif atmo_type == "low_light":
        out = out * (0.45 + 0.55 * (1 - strength))  # darken
        out = np.clip(out, 0, 255)
    return np.clip(out, 0, 255).astype(np.uint8)
