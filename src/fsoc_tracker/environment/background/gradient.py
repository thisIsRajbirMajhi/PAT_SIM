"""Background gradient generation (moved from simulation/world.py)."""
import numpy as np


def make_gradient(w, h, env, bg):
    gtype = env.get("gradient_type", "linear")
    top = int(np.clip(env.get("gradient_top", 22), 0, 80))
    bottom = int(np.clip(env.get("gradient_bottom", 38), 0, 80))
    angle = float(env.get("gradient_angle", 90))

    if gtype == "radial":
        # radial from center
        ys, xs = np.ogrid[0:h, 0:w]
        cx, cy = w / 2, h / 2
        max_r = np.hypot(cx, cy)
        r = np.hypot(xs - cx, ys - cy) / (max_r + 1e-6)
        # r=0 -> top, r=1 -> bottom
        vals = (top + (bottom - top) * r).astype(np.uint8)
        return vals
    elif gtype == "diagonal":
        # diagonal 45deg blend
        ys = np.linspace(0, 1, h)[:, None]
        xs = np.linspace(0, 1, w)[None, :]
        t = (xs + ys) / 2.0
        vals = (top + (bottom - top) * t).astype(np.uint8)
        return vals
    else:  # linear
        rad = np.deg2rad(angle)
        if abs(np.cos(rad)) < 0.15:  # near vertical: top -> bottom
            col = np.linspace(top, bottom, h, dtype=np.float32)[:, None]
            vals = np.tile(col, (1, w)).astype(np.uint8)
            return vals
        elif abs(np.sin(rad)) < 0.15:  # near horizontal: left -> right
            row = np.linspace(top, bottom, w, dtype=np.float32)[None, :]
            vals = np.tile(row, (h, 1)).astype(np.uint8)
            return vals
        else:
            ys, xs = np.ogrid[0:h, 0:w]
            proj = xs * np.cos(rad) + ys * np.sin(rad)
            pmin, pmax = proj.min(), proj.max()
            t = (proj - pmin) / (pmax - pmin + 1e-6)
            vals = (top + (bottom - top) * t).astype(np.uint8)
            return vals
