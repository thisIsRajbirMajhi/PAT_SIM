"""Shared per-frame image pipeline: atmosphere -> sensor noise -> frame jitter.

Single ordering used by SyntheticSource.read(). Both environment and camera/input
consume this — no duplicated inline pipeline code.
Order per spec: atmosphere, gaussian, salt&pepper, poisson, jitter.
"""
from .atmosphere import apply_atmosphere
from .config import get_atmosphere, get_jitter, get_noise
from .frame import apply_jitter
from .sensor import apply_gaussian, apply_poisson, apply_salt_pepper


def apply_disturbances(frame_img, cfg, rng):
    """Stateless one-shot: apply all active image disturbances in canonical order."""
    atmo = get_atmosphere(cfg)
    out = apply_atmosphere(frame_img, atmo.get("type", "clear"), float(atmo.get("strength", 0)))
    noise = get_noise(cfg)
    if noise.get("gaussian_enabled") and float(noise.get("gaussian_std", 0)) > 0:
        out = apply_gaussian(out, noise["gaussian_std"], rng)
    if noise.get("salt_pepper_enabled") and float(noise.get("salt_pepper_prob", 0)) > 0:
        out = apply_salt_pepper(out, noise["salt_pepper_prob"], rng)
    if noise.get("poisson"):
        out = apply_poisson(out, rng)
    jitter = get_jitter(cfg)
    if jitter > 0:
        out = apply_jitter(out, jitter, rng)
    return out


class DisturbancePipeline:
    """Stateful wrapper caching cfg snapshot; shares rng owned by the caller (e.g. SyntheticSource)."""

    def __init__(self, cfg):
        self.update_config(cfg)

    def update_config(self, cfg):
        self.cfg = cfg
        atmo = get_atmosphere(cfg)
        self.atmo_type = atmo.get("type", "clear")
        self.atmo_strength = float(atmo.get("strength", 0))
        self.noise_cfg = get_noise(cfg)
        self.jitter = get_jitter(cfg)

    def apply(self, frame_img, rng):
        out = apply_atmosphere(frame_img, self.atmo_type, self.atmo_strength)
        if self.noise_cfg.get("gaussian_enabled") and float(self.noise_cfg.get("gaussian_std", 0)) > 0:
            out = apply_gaussian(out, self.noise_cfg["gaussian_std"], rng)
        if self.noise_cfg.get("salt_pepper_enabled") and float(self.noise_cfg.get("salt_pepper_prob", 0)) > 0:
            out = apply_salt_pepper(out, self.noise_cfg["salt_pepper_prob"], rng)
        if self.noise_cfg.get("poisson"):
            out = apply_poisson(out, rng)
        if self.jitter > 0:
            out = apply_jitter(out, self.jitter, rng)
        return out


__all__ = ["apply_disturbances", "DisturbancePipeline"]
