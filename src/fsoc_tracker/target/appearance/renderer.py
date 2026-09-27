"""Beacon renderer — draws count beacons with glow + blur + re-brightened core."""
import cv2

from .shapes import draw_beacon, get_user_polygon


class BeaconRenderer:
    def __init__(self, cfg):
        self.update_config(cfg)

    def update_config(self, cfg):
        self.cfg = cfg
        self.size = int(cfg["target"]["size"])
        self.intensity = int(cfg["target"].get("intensity", 255))
        self.shape = cfg["target"].get("shape", "square")
        self.custom_polygon = cfg["target"].get("custom_polygon", None)
        self.bg = int(cfg["world"].get("background", 18))

    def draw(self, img, positions, w, h):
        half = self.size // 2
        for (x_f, y_f) in positions:
            x = int(round(x_f))
            y = int(round(y_f))
            if not (0 <= x < w and 0 <= y < h):
                continue
            glow = self.bg + 35 if self.shape == "gaussian" else self.bg + 45
            draw_beacon(img, x, y, self.shape, half, glow, self.intensity, self.custom_polygon)
            # blur small region for realism
            x0 = max(0, x - half - 2); y0 = max(0, y - half - 2)
            x1 = min(w, x + half + 3); y1 = min(h, y + half + 3)
            patch = img[y0:y1, x0:x1]
            if patch.size > 0:
                img[y0:y1, x0:x1] = cv2.GaussianBlur(patch, (3, 3), 0)
                # re-brighten core after blur (mirrors World legacy behaviour)
                self._redraw_core(img, x, y, half)
        return img

    def _redraw_core(self, img, x, y, half):
        if self.shape == "circle":
            cv2.circle(img, (x, y), half, int(self.intensity), -1)
        elif self.shape == "gaussian":
            cv2.circle(img, (x, y), half, int(self.intensity), -1)
        elif self.shape == "cross":
            cv2.rectangle(img, (x - half, y - 1), (x + half, y + 1), int(self.intensity), -1)
            cv2.rectangle(img, (x - 1, y - half), (x + 1, y + half), int(self.intensity), -1)
        elif self.shape == "user-defined":
            cv2.fillPoly(img, [get_user_polygon(x, y, half, self.custom_polygon)], int(self.intensity))
        else:
            cv2.rectangle(img, (x - half, y - half), (x + half, y + half), int(self.intensity), -1)


__all__ = ["BeaconRenderer"]
