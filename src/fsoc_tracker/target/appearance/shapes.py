"""Beacon shape helpers — user polygon + per-shape glow/core drawing (extracted from World)."""
import math

import cv2
import numpy as np


def get_user_polygon(cx, cy, half, custom_polygon=None):
    """Return polygon points for user-defined shape (custom or 5-point star fallback)."""
    if custom_polygon and isinstance(custom_polygon, list) and len(custom_polygon) >= 3:
        try:
            return np.array(
                [[cx + int(dx * half / 5), cy + int(dy * half / 5)] for dx, dy in custom_polygon],
                dtype=np.int32,
            )
        except Exception:
            pass
    # Default: 5-point star — distinct vs square/circle
    pts = []
    for i in range(10):
        r = half if i % 2 == 0 else half // 2
        ang = math.radians(90 + i * 36)
        pts.append([int(cx + r * math.cos(ang)), int(cy - r * math.sin(ang))])
    return np.array(pts, dtype=np.int32)


def draw_beacon(img, x, y, shape, half, glow_val, core_val, custom_polygon=None, bg=None):
    """Draw glow + core for one beacon (no blur). Supports square/circle/gaussian/cross/user-defined."""
    if shape == "circle":
        cv2.circle(img, (x, y), half + 2, int(glow_val), -1)
    elif shape == "gaussian":
        cv2.circle(img, (x, y), half + 3, int(glow_val), -1)
    elif shape == "cross":
        cv2.rectangle(img, (x - half - 1, y - 1), (x + half + 1, y + 1), int(glow_val), -1)
        cv2.rectangle(img, (x - 1, y - half - 1), (x + 1, y + half + 1), int(glow_val), -1)
    elif shape == "user-defined":
        cv2.fillPoly(img, [get_user_polygon(x, y, half + 2, custom_polygon)], int(glow_val))
    else:  # square
        cv2.rectangle(img, (x - half - 1, y - half - 1), (x + half + 1, y + half + 1), int(glow_val), -1)
    # core
    if shape == "circle":
        cv2.circle(img, (x, y), half, int(core_val), -1)
    elif shape == "gaussian":
        cv2.circle(img, (x, y), half, int(core_val), -1)
    elif shape == "cross":
        cv2.rectangle(img, (x - half, y - 1), (x + half, y + 1), int(core_val), -1)
        cv2.rectangle(img, (x - 1, y - half), (x + 1, y + half), int(core_val), -1)
    elif shape == "user-defined":
        cv2.fillPoly(img, [get_user_polygon(x, y, half, custom_polygon)], int(core_val))
    else:
        cv2.rectangle(img, (x - half, y - half), (x + half, y + half), int(core_val), -1)


__all__ = ["get_user_polygon", "draw_beacon"]
