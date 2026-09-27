"""Background gradient generation (moved from simulation/world.py)."""
import numpy as np


def make_gradient(w, h, env, bg):
    gtype = env.get("gradient_type", "linear")
    top = int(np.clip(env.get("gradient_top", 22), 0, 80))
    bottom = int(np.clip(env.get("gradient_bottom", 38), 0, 80))
    angle = float(env.get("gradient_angle", 90)) % 360.0

    if gtype == "radial":
        # radially symmetric around (optional) center; angle is N/A by definition
        cx = float(env.get("gradient_center_x", 0.5)) * w
        cy = float(env.get("gradient_center_y", 0.5)) * h
        ys, xs = np.ogrid[0:h, 0:w]
        xs = (xs - cx).astype(np.float32, copy=False)
        ys = (ys - cy).astype(np.float32, copy=False)
        max_r = float(np.hypot(max(cx, w - cx), max(cy, h - cy))) + 1e-6
        r = np.sqrt(xs * xs + ys * ys) / max_r  # 0..1
        # r=0 -> top, r=1 -> bottom
        vals = (top + (bottom - top) * r).astype(np.uint8)
        return vals
    if gtype == "diagonal":
        # diagonal blend along gradient_angle (default 45deg); normalized coords
        rad = np.deg2rad(angle)
        dx, dy = float(np.cos(rad)), float(np.sin(rad))
        xs = np.linspace(0, 1, w, dtype=np.float32)[None, :]
        ys = np.linspace(0, 1, h, dtype=np.float32)[:, None]
        proj = xs * dx + ys * dy
        pmin, pmax = proj.min(), proj.max()
        t = (proj - pmin) / (pmax - pmin + 1e-6)
        vals = (top + (bottom - top) * t).astype(np.uint8)
        return vals
    # linear: project pixel coords onto gradient direction
    rad = np.deg2rad(angle)
    dx, dy = float(np.cos(rad)), float(np.sin(rad))
    if abs(dy) >= abs(dx):  # mostly vertical: top -> bottom
        if abs(dx) < 1e-6:
            col = np.linspace(top, bottom, h, dtype=np.float32)[:, None]
            return np.tile(col, (1, w)).astype(np.uint8)
    else:  # mostly horizontal: left -> right
        if abs(dy) < 1e-6:
            row = np.linspace(top, bottom, w, dtype=np.float32)[None, :]
            return np.tile(row, (h, 1)).astype(np.uint8)
    ys, xs = np.ogrid[0:h, 0:w]
    proj = xs.astype(np.float32) * dx + ys.astype(np.float32) * dy
    pmin, pmax = proj.min(), proj.max()
    t = (proj - pmin) / (pmax - pmin + 1e-6)
    vals = (top + (bottom - top) * t).astype(np.uint8)
    return vals
