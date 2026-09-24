import numpy as np
import cv2
from .trajectories import make_trajectory

class World:
    def __init__(self, cfg, seed=42):
        self.cfg = cfg
        self.seed = seed
        w = cfg["world"]["width"]
        h = cfg["world"]["height"]
        self.w = w; self.h = h
        self.bg = int(cfg["world"].get("background", 18))
        # build base with all environment systems
        self.base = self._build_base(cfg, seed)
        # trajectory - support multiple independent targets (Sr.8)
        self.target_count = int(cfg["target"].get("count", 1))
        self.trajectories = []
        # Primary target uses selected trajectory with main seed
        self.traj = make_trajectory(cfg, seed=seed)
        self.trajectories.append(self.traj)
        # Additional targets use independent random trajectories with offset seeds
        for i in range(1, self.target_count):
            # Create a variant config for distractor targets: random trajectory
            distractor_cfg = cfg.copy()
            # For distractors, use random motion with different seed and slightly offset speed
            distractor_cfg["target"] = cfg["target"].copy()
            distractor_cfg["target"]["trajectory"] = "random"
            distractor_cfg["target"]["speed_px_per_frame"] = float(cfg["target"].get("speed_px_per_frame", 2.8)) * (0.7 + 0.6 * ((i % 3) / 2))
            self.trajectories.append(make_trajectory(distractor_cfg, seed=seed + i * 1009))
        self.target_size = int(cfg["target"]["size"])
        self.target_intensity = int(cfg["target"].get("intensity", 255))
        self.target_shape = cfg["target"].get("shape", "square")
        self.custom_polygon = cfg["target"].get("custom_polygon", None)
        self.frame_id = 0
        self.all_world_pos = [traj.step(0) for traj in self.trajectories]
        self.world_pos = self.all_world_pos[0] if self.all_world_pos else self.traj.step(0)

    # ---------- base building ----------
    def _build_base(self, cfg, seed):
        w, h = self.w, self.h
        env = cfg.get("environment", {})
        bg = int(cfg["world"].get("background", 18))

        # 1) Gradient or flat
        if env.get("gradient_enabled"):
            base = self._make_gradient(w, h, env, bg)
        else:
            base = np.full((h, w), bg, dtype=np.uint8)

        # 2) Subtle texture
        rng = np.random.default_rng(seed)
        noise = rng.integers(0, 6, size=(h, w), dtype=np.uint8)
        base = cv2.add(base, noise)

        # 3) Brightness gain/offset on world base (before stars/vignetting, keeps star contrast)
        gain = float(env.get("brightness_gain", 1.0))
        offset = int(env.get("brightness_offset", 0))
        if abs(gain - 1.0) > 1e-6 or offset != 0:
            base = np.clip(base.astype(np.float32) * gain + offset, 0, 255).astype(np.uint8)

        # 4) Stars clutter (static)
        if env.get("stars_enabled"):
            base = self._add_stars(base, env, seed)

        # 5) Vignetting (after stars so stars also vignetted like lens)
        if env.get("vignetting_enabled"):
            base = self._apply_vignetting(base, env)

        return base

    def _make_gradient(self, w, h, env, bg):
        gtype = env.get("gradient_type", "linear")
        top = int(np.clip(env.get("gradient_top", 22), 0, 80))
        bottom = int(np.clip(env.get("gradient_bottom", 38), 0, 80))
        angle = float(env.get("gradient_angle", 90))

        if gtype == "radial":
            # radial from center
            ys, xs = np.ogrid[0:h, 0:w]
            cx, cy = w/2, h/2
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

    def _add_stars(self, base, env, seed):
        density = float(np.clip(env.get("stars_density", 0.0007), 0, 0.006))
        if density <= 0:
            return base
        # separate seed for stars so main seed still controls trajectory
        s_seed = int(env.get("stars_seed", 1337)) ^ int(seed)
        rng = np.random.default_rng(s_seed)
        h, w = base.shape
        n = int(density * w * h)
        n = int(np.clip(n, 0, 12000))
        ys = rng.integers(0, h, size=n)
        xs = rng.integers(0, w, size=n)
        # magnitude per star: uniform between min/max but biased to dim
        min_mag = int(env.get("stars_min_mag", 90))
        max_mag = int(env.get("stars_max_mag", 255))
        brightness = int(env.get("stars_brightness", 185))
        # blend: star_intensity = min_mag + rand*(max_mag-min_mag) scaled by brightness/255
        mags = rng.integers(min_mag, max_mag+1, size=n, dtype=np.int16)
        # scale by overall brightness
        mags = (mags.astype(np.float32) * (brightness / 180.0)).astype(np.int16)
        mags = np.clip(mags, 60, 255).astype(np.uint8)

        out = base.copy()
        # draw stars: 1px core + optional 1px glow for bright stars
        # use vectorized: for each star, set pixel to max(base, mag)
        # faster loop in python is okay for ~3k stars
        for x, y, m in zip(xs, ys, mags):
            # avoid placing stars too close to border where vignetting would hide? keep all
            if m > int(max_mag * 0.85):
                # bright star: 3x3 glow
                y0, y1 = max(0, y-1), min(h, y+2)
                x0, x1 = max(0, x-1), min(w, x+2)
                # glow
                patch = out[y0:y1, x0:x1].astype(np.int16)
                patch = np.maximum(patch, int(m * 0.45))
                out[y0:y1, x0:x1] = patch.astype(np.uint8)
            # core
            out[y, x] = max(int(out[y, x]), int(m))

        # optional twinkle: will be modulated per-frame in render_world if enabled
        return out

    def _apply_vignetting(self, base, env):
        h, w = base.shape
        strength = float(np.clip(env.get("vignetting_strength", 0.42), 0, 0.95))
        radius = float(np.clip(env.get("vignetting_radius", 0.72), 0.05, 1.0))
        falloff = float(np.clip(env.get("vignetting_falloff", 2.0), 0.3, 6.0))
        cx = float(np.clip(env.get("vignetting_center_x", 0.5), 0, 1)) * w
        cy = float(np.clip(env.get("vignetting_center_y", 0.5), 0, 1)) * h
        ys, xs = np.ogrid[0:h, 0:w]
        # normalized distance from center (0=center, 1=corner)
        max_d = np.hypot(max(cx, w - cx), max(cy, h - cy)) + 1e-6
        d = np.hypot(xs - cx, ys - cy) / max_d  # 0..1
        # mask: 1 inside radius, falloff outside
        # smoothstep-like
        t = np.clip((d - radius) / (1.0 - radius + 1e-6), 0, 1)
        # falloff curve: t^falloff
        vig = 1.0 - strength * np.power(t, falloff)
        vig = np.clip(vig, 0, 1).astype(np.float32)
        # apply
        out = (base.astype(np.float32) * vig).astype(np.uint8)
        return out

    def _get_user_polygon(self, cx, cy, half):
        """Return polygon points for user-defined shape. Uses custom_polygon if provided, else default 5-point star."""
        if self.custom_polygon and isinstance(self.custom_polygon, list) and len(self.custom_polygon) >= 3:
            try:
                pts = np.array([[cx + int(dx * half / 5), cy + int(dy * half / 5)] for dx, dy in self.custom_polygon], dtype=np.int32)
                return pts
            except Exception:
                pass
        # Default: 5-point star (user-defined fallback) - meaningful distinct shape vs square/circle
        import math
        pts = []
        for i in range(10):
            r = half if i % 2 == 0 else half // 2
            ang = math.radians(90 + i * 36)
            pts.append([int(cx + r * math.cos(ang)), int(cy - r * math.sin(ang))])
        return np.array(pts, dtype=np.int32)

    def update_config(self, cfg, seed=None):
        """Rebuild base only if environment/world relevant fields changed; handle multi-target and shape."""
        old_env = self.cfg.get("environment", {})
        new_env = cfg.get("environment", {})
        old_w = (self.cfg["world"]["width"], self.cfg["world"]["height"], self.cfg["world"].get("background", 18))
        new_w = (cfg["world"]["width"], cfg["world"]["height"], cfg["world"].get("background", 18))
        old_count = int(self.cfg["target"].get("count", 1))
        new_count = int(cfg.get("target", {}).get("count", 1))
        old_shape = self.cfg["target"].get("shape", "square")
        new_shape = cfg.get("target", {}).get("shape", "square")
        # check if rebuild needed
        rebuild = (old_env != new_env) or (old_w != new_w) or (seed is not None and seed != self.seed)
        rebuild_traj = (old_count != new_count) or (old_shape != new_shape) or (self.cfg["target"].get("trajectory") != cfg.get("target", {}).get("trajectory"))
        self.cfg = cfg
        self.w, self.h = new_w[0], new_w[1]
        self.bg = int(new_w[2])
        if seed is not None:
            self.seed = seed
        if rebuild:
            self.base = self._build_base(cfg, self.seed)
        if rebuild_traj:
            # rebuild trajectories for count change
            self.target_count = new_count
            self.trajectories = []
            self.traj = make_trajectory(cfg, seed=self.seed)
            self.trajectories.append(self.traj)
            for i in range(1, self.target_count):
                distractor_cfg = cfg.copy()
                distractor_cfg["target"] = cfg["target"].copy()
                distractor_cfg["target"]["trajectory"] = "random"
                distractor_cfg["target"]["speed_px_per_frame"] = float(cfg["target"].get("speed_px_per_frame", 2.8)) * (0.7 + 0.6 * ((i % 3) / 2))
                self.trajectories.append(make_trajectory(distractor_cfg, seed=self.seed + i * 1009))
            self.all_world_pos = [traj.step(self.frame_id) for traj in self.trajectories]
        # update target size/intensity/shape live
        self.target_size = int(cfg["target"]["size"])
        self.target_intensity = int(cfg["target"].get("intensity", 255))
        self.target_shape = cfg["target"].get("shape", "square")
        self.custom_polygon = cfg["target"].get("custom_polygon", None)

    def step(self):
        # Update all targets independently (Sr.8 multi-target)
        self.all_world_pos = [traj.step(self.frame_id) for traj in self.trajectories]
        self.world_pos = self.all_world_pos[0] if self.all_world_pos else self.traj.step(self.frame_id)
        self.frame_id += 1
        return self.world_pos

    def render_world(self, world_pos=None):
        if world_pos is None:
            world_pos = self.world_pos
        img = self.base.copy()

        env = self.cfg.get("environment", {})
        if env.get("stars_enabled") and env.get("stars_twinkle"):
            jit = np.random.default_rng(self.frame_id * 9973).integers(-6, 7, size=img.shape, dtype=np.int16)
            img = np.clip(img.astype(np.int16) + jit, 0, 255).astype(np.uint8)

        # draw beacon(s) — support count (independent trajectories Sr.8) & shape Sr.9 (including user-defined)
        count = int(self.cfg["target"].get("count", 1))
        shape = self.cfg["target"].get("shape", "square")
        s = self.target_size
        half = s//2
        # Build list of positions: use independent trajectories if available
        if hasattr(self, 'all_world_pos') and len(self.all_world_pos) >= count and world_pos == self.world_pos:
            # Use independent positions for primary rendering (primary is world_pos, others from all_world_pos)
            positions = self.all_world_pos[:count]
        elif hasattr(self, 'all_world_pos') and len(self.all_world_pos) == count:
            positions = self.all_world_pos
        else:
            # Fallback: single world_pos with horizontal offsets for distractors
            positions = []
            for idx in range(max(1, count)):
                off = (idx - (count-1)/2) * (s + 22) if count > 1 else 0
                positions.append((world_pos[0] + off, world_pos[1]))
            # If world_pos is the primary, ensure first matches
            if positions and world_pos:
                positions[0] = world_pos
        for (x_f, y_f) in positions:
            x = int(round(x_f))
            y = int(round(y_f))
            if not (0 <= x < self.w and 0 <= y < self.h):
                continue
            # glow - supports square, circle, gaussian, cross, user-defined (Sr.9)
            if shape == "circle":
                cv2.circle(img, (x, y), half+2, int(self.bg+45), -1)
            elif shape == "gaussian":
                cv2.circle(img, (x, y), half+3, int(self.bg+35), -1)
            elif shape == "cross":
                cv2.rectangle(img, (x-half-1, y-1), (x+half+1, y+1), int(self.bg+45), -1)
                cv2.rectangle(img, (x-1, y-half-1), (x+1, y+half+1), int(self.bg+45), -1)
            elif shape == "user-defined":
                pts = self._get_user_polygon(x, y, half+2)
                cv2.fillPoly(img, [pts], int(self.bg+45))
            else: # square
                cv2.rectangle(img, (x-half-1, y-half-1), (x+half+1, y+half+1), int(self.bg+45), -1)
            # core - supports all shapes including user-defined polygon
            if shape == "circle":
                cv2.circle(img, (x, y), half, int(self.target_intensity), -1)
            elif shape == "gaussian":
                cv2.circle(img, (x, y), half, int(self.target_intensity), -1)
            elif shape == "cross":
                cv2.rectangle(img, (x-half, y-1), (x+half, y+1), int(self.target_intensity), -1)
                cv2.rectangle(img, (x-1, y-half), (x+1, y+half), int(self.target_intensity), -1)
            elif shape == "user-defined":
                pts = self._get_user_polygon(x, y, half)
                cv2.fillPoly(img, [pts], int(self.target_intensity))
            else:
                cv2.rectangle(img, (x-half, y-half), (x+half, y+half), int(self.target_intensity), -1)
            # blur small region for realism
            x0 = max(0, x-half-2); y0 = max(0, y-half-2)
            x1 = min(self.w, x+half+3); y1 = min(self.h, y+half+3)
            patch = img[y0:y1, x0:x1]
            if patch.size > 0:
                patch = cv2.GaussianBlur(patch, (3,3), 0)
                img[y0:y1, x0:x1] = patch
                # re-brighten core after blur - supports all shapes
                if shape == "circle":
                    cv2.circle(img, (x, y), half, int(self.target_intensity), -1)
                elif shape == "gaussian":
                    cv2.circle(img, (x, y), half, int(self.target_intensity), -1)
                elif shape == "cross":
                    cv2.rectangle(img, (x-half, y-1), (x+half, y+1), int(self.target_intensity), -1)
                    cv2.rectangle(img, (x-1, y-half), (x+1, y+half), int(self.target_intensity), -1)
                elif shape == "user-defined":
                    pts = self._get_user_polygon(x, y, half)
                    cv2.fillPoly(img, [pts], int(self.target_intensity))
                else:
                    cv2.rectangle(img, (x-half, y-half), (x+half, y+half), int(self.target_intensity), -1)
        return img

    def reset(self, seed=None):
        if seed is not None:
            self.seed = seed
        self.frame_id = 0
        self.target_count = int(self.cfg["target"].get("count", 1))
        self.trajectories = []
        self.traj = make_trajectory(self.cfg, seed=self.seed)
        self.trajectories.append(self.traj)
        for i in range(1, self.target_count):
            distractor_cfg = self.cfg.copy()
            distractor_cfg["target"] = self.cfg["target"].copy()
            distractor_cfg["target"]["trajectory"] = "random"
            distractor_cfg["target"]["speed_px_per_frame"] = float(self.cfg["target"].get("speed_px_per_frame", 2.8)) * (0.7 + 0.6 * ((i % 3) / 2))
            self.trajectories.append(make_trajectory(distractor_cfg, seed=self.seed + i * 1009))
        self.all_world_pos = [traj.step(0) for traj in self.trajectories]
        self.world_pos = self.all_world_pos[0] if self.all_world_pos else self.traj.step(0)
