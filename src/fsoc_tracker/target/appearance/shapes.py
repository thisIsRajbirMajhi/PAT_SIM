"""Beacon shape helpers — glow/core drawing for square, circle, diamond, cross, triangle, custom."""
import cv2
import numpy as np


_VALID_SHAPES = ("square", "circle", "diamond", "cross", "triangle", "custom")


def normalize_shape(shape):
    s = str(shape or "square").strip().lower()
    return s if s in _VALID_SHAPES else "square"


def _poly_points(x, y, shape, half, custom_polygon=None):
    if shape == "circle":
        return None
    if shape == "diamond":
        return np.array([[x, y - half - 1], [x + half + 1, y], [x, y + half + 1], [x - half - 1, y]], np.int32)
    if shape == "triangle":
        return np.array([[x, y - half - 1], [x + half + 1, y + half + 1], [x - half - 1, y + half + 1]], np.int32)
    if shape == "custom" and custom_polygon:
        try:
            pts = [(x + int(round(float(dx))), y + int(round(float(dy)))) for dx, dy in custom_polygon]
            if len(pts) >= 3:
                return np.array(pts, np.int32)
        except Exception:
            pass
        return None
    return None


def draw_beacon(img, x, y, shape, half, glow_val, core_val, custom_polygon=None, bg=None):
    """Draw glow + core for one beacon (no blur). Supports square/circle/diamond/cross/triangle/custom.

    `custom_polygon` is a list of [dx,dy] offsets used when shape == "custom".
    Unknown shapes fall back to square.
    """
    shape = normalize_shape(shape)
    if shape == "circle":
        cv2.circle(img, (x, y), half + 2, int(glow_val), -1)
    elif shape in ("diamond", "triangle", "custom"):
        pts = _poly_points(x, y, shape, half, custom_polygon)
        if pts is not None:
            # glow: slightly enlarged polygon
            cx, cy = float(x), float(y)
            enlarged = []
            for px, py in pts.reshape(-1, 2):
                vx, vy = float(px) - cx, float(py) - cy
                n = (vx * vx + vy * vy) ** 0.5 or 1.0
                enlarged.append([int(round(cx + vx * (1.0 + 1.5 / n))), int(round(cy + vy * (1.0 + 1.5 / n)))])
            cv2.fillPoly(img, [np.array(enlarged, np.int32)], int(glow_val))
        else:
            cv2.rectangle(img, (x - half - 1, y - half - 1), (x + half + 1, y + half + 1),
                          int(glow_val), -1)
    elif shape == "cross":
        t = max(1, half // 2)
        cv2.rectangle(img, (x - half - 1, y - t - 1), (x + half + 1, y + t + 1), int(glow_val), -1)
        cv2.rectangle(img, (x - t - 1, y - half - 1), (x + t + 1, y + half + 1), int(glow_val), -1)
    else:  # square
        cv2.rectangle(img, (x - half - 1, y - half - 1), (x + half + 1, y + half + 1),
                      int(glow_val), -1)
    # core
    if shape == "circle":
        cv2.circle(img, (x, y), half, int(core_val), -1)
    elif shape in ("diamond", "triangle", "custom"):
        pts = _poly_points(x, y, shape, half, custom_polygon)
        if pts is not None:
            cv2.fillPoly(img, [pts], int(core_val))
        else:
            cv2.rectangle(img, (x - half, y - half), (x + half, y + half), int(core_val), -1)
    elif shape == "cross":
        t = max(1, half // 2)
        cv2.rectangle(img, (x - half, y - t), (x + half, y + t), int(core_val), -1)
        cv2.rectangle(img, (x - t, y - half), (x + t, y + half), int(core_val), -1)
    else:
        cv2.rectangle(img, (x - half, y - half), (x + half, y + half), int(core_val), -1)


__all__ = ["draw_beacon", "normalize_shape"]
