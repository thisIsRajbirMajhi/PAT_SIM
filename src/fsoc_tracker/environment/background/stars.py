"""Static star-field clutter (moved from simulation/world.py)."""
import numpy as np


def add_stars(base, env, seed):
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
    mags = rng.integers(min_mag, max_mag + 1, size=n, dtype=np.int16)
    # scale by overall brightness
    mags = (mags.astype(np.float32) * (brightness / 180.0)).astype(np.int16)
    mags = np.clip(mags, 60, 255).astype(np.uint8)

    out = base.copy()
    # draw stars: 1px core + optional 1px glow for bright stars
    for x, y, m in zip(xs, ys, mags):
        if m > int(max_mag * 0.85):
            # bright star: 3x3 glow
            y0, y1 = max(0, y - 1), min(h, y + 2)
            x0, x1 = max(0, x - 1), min(w, x + 2)
            patch = out[y0:y1, x0:x1].astype(np.int16)
            patch = np.maximum(patch, int(m * 0.45))
            out[y0:y1, x0:x1] = patch.astype(np.uint8)
        # core
        out[y, x] = max(int(out[y, x]), int(m))

    # optional twinkle: will be modulated per-frame in render_world if enabled
    return out


def apply_twinkle(img, frame_id, amount=6):
    """Per-frame star twinkle (whole-image dither used when stars_twinkle is on)."""
    jit = np.random.default_rng(frame_id * 9973).integers(
        -amount, amount + 1, size=img.shape, dtype=np.int16
    )
    return np.clip(img.astype(np.int16) + jit, 0, 255).astype(np.uint8)
