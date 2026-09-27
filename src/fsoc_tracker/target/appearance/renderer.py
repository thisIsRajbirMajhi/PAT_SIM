"""Beacon renderer — draws count beacons with diffuse glow + sharp core.

Pipeline per beacon: flat glow quad -> small Gaussian blur (diffuse halo) ->
sharp square/circle core on top. Blurring only the glow keeps the halo while
the core stays at full intensity, so no redraw pass is wasted.

`draw()` works in place on `img` (caller passes a scratch copy) and returns it.
`intensity_scale` dims the beacon for atmosphere (fog/haze/rain/low_light);
World.render_world() computes it from the atmosphere config.
"""
import cv2
import numpy as np

from .shapes import draw_beacon

#: fixed beacon core peak (before atmosphere dimming) — kept simple by design
PEAK_INTENSITY = 255


def atmosphere_intensity_scale(cfg):
    """Beacon dimming factor in [0.15, 1.0] for the configured atmosphere."""
    atmo = cfg.get("atmosphere", {}) if isinstance(cfg, dict) else {}
    atype = atmo.get("type", "clear")
    try:
        s = float(np.clip(atmo.get("strength", 0.0), 0, 1))
    except (TypeError, ValueError):
        s = 0.0
    if atype == "haze":
        scale = 1.0 - 0.30 * s
    elif atype == "fog":
        scale = 1.0 - 0.45 * s
    elif atype == "rain":
        scale = 1.0 - 0.20 * s
    elif atype == "low_light":
        scale = 0.45 + 0.55 * (1.0 - s)
    else:
        scale = 1.0
    return float(np.clip(scale, 0.15, 1.0))


class BeaconRenderer:
    def __init__(self, cfg):
        self.update_config(cfg)

    def update_config(self, cfg):
        self.cfg = cfg
        self.size = int(cfg["target"]["size"])
        self.intensity = PEAK_INTENSITY
        shape = cfg["target"].get("shape", "square")
        self.shape = shape if shape == "circle" else "square"
        self.bg = int(cfg["world"].get("background", 18))

    def draw(self, img, positions, w, h, intensity_scale=1.0):
        half = self.size // 2
        peak = int(np.clip(round(self.intensity * float(intensity_scale)), 0, 255))
        for (x_f, y_f) in positions:
            x = int(round(x_f))
            y = int(round(y_f))
            if not (0 <= x < w and 0 <= y < h):
                continue
            glow = int(np.clip(round((self.bg + 45) * float(intensity_scale)), 0, 255))
            draw_beacon(img, x, y, self.shape, half, glow, peak)
            # diffuse the glow halo, then restore the sharp core (single pass each)
            x0 = max(0, x - half - 3); y0 = max(0, y - half - 3)
            x1 = min(w, x + half + 4); y1 = min(h, y + half + 4)
            patch = img[y0:y1, x0:x1]
            if patch.size > 0:
                img[y0:y1, x0:x1] = cv2.GaussianBlur(patch, (3, 3), 0)
            self._redraw_core(img, x, y, half, peak)
        return img

    def _redraw_core(self, img, x, y, half, peak=None):
        peak = self.intensity if peak is None else int(peak)
        if self.shape == "circle":
            cv2.circle(img, (x, y), half, peak, -1)
        else:
            cv2.rectangle(img, (x - half, y - half), (x + half, y + half), peak, -1)


__all__ = ["BeaconRenderer", "atmosphere_intensity_scale", "PEAK_INTENSITY"]
