"""Pure pixel <-> angle geometry shared by optics and gimbal control.

Canonical scale: px_per_deg = res_w / fov_h (= res_h / fov_v = 160 for 640x480 4x3deg),
i.e. 0.00625 deg/px. Mirrors VirtualCamera + SimpleEKF (fx*pi/180 ~= 160).
"""
import math


def px_per_deg(resolution, fov_deg):
    res_w, _ = resolution
    fov_h, _ = fov_deg
    return res_w / fov_h


def deg_per_px(resolution, fov_deg):
    return 1.0 / px_per_deg(resolution, fov_deg)


def pixel_to_angle(image_pos, resolution, fov_deg):
    """Image pixel (u,v) -> angular error (alpha,beta) deg relative to boresight."""
    if image_pos is None:
        return None
    res_w, res_h = resolution
    fov_h, fov_v = fov_deg
    u, v = image_pos
    alpha = (u - res_w / 2) * (fov_h / res_w)
    beta = -(v - res_h / 2) * (fov_v / res_h)
    return (alpha, beta)


def angle_to_pixel(alpha, beta, resolution, fov_deg):
    res_w, res_h = resolution
    fov_h, fov_v = fov_deg
    u = res_w / 2 + alpha * (res_w / fov_h)
    v = res_h / 2 - beta * (res_h / fov_v)
    return (float(u), float(v))


def viewport_bounds(center_world, resolution):
    res_w, res_h = resolution
    cx, cy = center_world
    return (cx - res_w / 2, cy - res_h / 2, cx + res_w / 2, cy + res_h / 2)


def focal_px_rad(resolution, fov_deg):
    """Pinhole focal length in px/rad (as used by SimpleEKF)."""
    res_w, res_h = resolution
    fov_h, fov_v = fov_deg
    fx = (res_w / 2) / math.tan(math.radians(fov_h) / 2)
    fy = (res_h / 2) / math.tan(math.radians(fov_v) / 2)
    return (fx, fy)


__all__ = [
    "px_per_deg",
    "deg_per_px",
    "pixel_to_angle",
    "angle_to_pixel",
    "viewport_bounds",
    "focal_px_rad",
]
