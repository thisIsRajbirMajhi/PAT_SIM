"""Beacon shape helpers — glow/core drawing for square and circle beacons."""
import cv2


def draw_beacon(img, x, y, shape, half, glow_val, core_val, custom_polygon=None, bg=None):
    """Draw glow + core for one beacon (no blur). Supports square/circle.

    `custom_polygon`/`bg` are accepted for backward compatibility and ignored.
    Unknown shapes fall back to square.
    """
    if shape != "circle":
        shape = "square"
    if shape == "circle":
        cv2.circle(img, (x, y), half + 2, int(glow_val), -1)
    else:  # square
        cv2.rectangle(img, (x - half - 1, y - half - 1), (x + half + 1, y + half + 1),
                      int(glow_val), -1)
    # core
    if shape == "circle":
        cv2.circle(img, (x, y), half, int(core_val), -1)
    else:
        cv2.rectangle(img, (x - half, y - half), (x + half, y + half), int(core_val), -1)


__all__ = ["draw_beacon"]
