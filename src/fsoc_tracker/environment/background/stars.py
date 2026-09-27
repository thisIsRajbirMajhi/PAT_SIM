"""Static star-field clutter (moved from simulation/world.py)."""
import numpy as np

BRIGHTNESS_REFERENCE = 185.0
DEFAULT_TWINKLE_AMOUNT = 6


def _star_coords(h, w, env, seed):
    """Shared coordinate/magnitude sampling used by add_stars and build_star_mask."""
    density = float(np.clip(env.get("stars_density", 0.0007), 0, 0.006))
    if density <= 0:
        return (np.empty(0, dtype=np.int64), np.empty(0, dtype=np.int64),
                np.empty(0, dtype=np.uint8), 0, 255)
    s_seed = int(env.get("stars_seed", 1337)) ^ int(seed)
    rng = np.random.default_rng(s_seed)
    n = int(density * w * h)
    max_count = int(env.get("stars_max_count", 12000))
    n = int(np.clip(n, 0, max_count))
    if n == 0:
        return (np.empty(0, dtype=np.int64), np.empty(0, dtype=np.int64),
                np.empty(0, dtype=np.uint8), 0, 255)
    ys = rng.integers(0, h, size=n)
    xs = rng.integers(0, w, size=n)
    min_mag = int(env.get("stars_min_mag", 90))
    max_mag = int(env.get("stars_max_mag", 255))
    if min_mag > max_mag:
        min_mag, max_mag = max_mag, min_mag
    min_mag = int(np.clip(min_mag, 0, 255))
    max_mag = int(np.clip(max_mag, 0, 255))
    brightness = float(env.get("stars_brightness", 185))
    mags = rng.integers(min_mag, max_mag + 1, size=n).astype(np.float32)
    # scale so default brightness (185) is unity gain
    mags = mags * (brightness / BRIGHTNESS_REFERENCE)
    mags = np.clip(mags, 0, 255).astype(np.uint8)
    return xs, ys, mags, min_mag, max_mag


def build_star_mask(h, w, env, seed):
    """Boolean mask of star core pixels (used for star-only twinkle)."""
    xs, ys, _, _, _ = _star_coords(h, w, env, seed)
    mask = np.zeros((h, w), dtype=bool)
    if xs.size:
        mask[ys, xs] = True
    return mask


def add_stars(base, env, seed):
    img, _ = add_stars_with_mask(base, env, seed)
    return img


def add_stars_with_mask(base, env, seed):
    """Vectorized star drawing. Returns (image, star_mask)."""
    h, w = base.shape
    xs, ys, mags, _, max_mag = _star_coords(h, w, env, seed)
    if xs.size == 0:
        return base.copy() if isinstance(base, np.ndarray) else base, np.zeros((h, w), dtype=bool)
    out = base.copy()
    bright_threshold = int(max_mag * 0.85)
    bright = mags > bright_threshold
    if np.any(bright):
        # 3x3 glow for bright stars only (usually a small subset): keep loop tight
        bx, by, bm = xs[bright], ys[bright], mags[bright]
        glow_vals = (bm.astype(np.int16) * 0.45).astype(np.int16)
        for x, y, g in zip(bx.tolist(), by.tolist(), glow_vals.tolist()):
            y0, y1 = max(0, y - 1), min(h, y + 2)
            x0, x1 = max(0, x - 1), min(w, x + 2)
            patch = out[y0:y1, x0:x1].astype(np.int16)
            np.maximum(patch, g, out=patch)
            out[y0:y1, x0:x1] = patch.astype(np.uint8)
    # 1px cores, vectorized (np.maximum.at keeps brightest on overlap)
    np.maximum.at(out, (ys, xs), mags)
    mask = np.zeros((h, w), dtype=bool)
    mask[ys, xs] = True
    return out, mask


def apply_twinkle(img, frame_id, amount=DEFAULT_TWINKLE_AMOUNT, mask=None):
    """Per-frame star twinkle applied to star pixels only.

    Backward compatible: apply_twinkle(img, frame_id) still works.
    When mask is None (legacy callers), falls back to whole-image dither.
    New callers should pass the star mask so background is untouched.
    """
    amount = int(np.clip(int(amount), 0, 30))
    if amount == 0:
        return img.copy() if isinstance(img, np.ndarray) else img
    seed = (int(frame_id) * 9973 + 0x9E3779B9) & 0xFFFFFFFF
    rng = np.random.default_rng(seed)
    if mask is None:
        jit = rng.integers(-amount, amount + 1, size=img.shape, dtype=np.int16)
        return np.clip(img.astype(np.int16) + jit, 0, 255).astype(np.uint8)
    mask = np.asarray(mask, dtype=bool)
    if not np.any(mask):
        return img.copy()
    out = img.copy()
    jit_vals = rng.integers(-amount, amount + 1, size=int(mask.sum()), dtype=np.int16)
    tmp = out[mask].astype(np.int16) + jit_vals
    out[mask] = np.clip(tmp, 0, 255).astype(np.uint8)
    return out
