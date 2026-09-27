"""Shared per-frame image pipeline: environment-side atmosphere, then camera-side sensor + jitter.

Ownership split:
    environment-side (world): atmosphere veil (haze/fog/rain/low_light)
        + platform ego-motion geometry (applied in SyntheticSource, not here)
    camera-side (viewport):   gaussian -> salt&pepper -> poisson -> jitter

Canonical order is preserved: atmosphere, gaussian, salt&pepper, poisson, jitter.
The pipeline snapshots plain-value flags at update_config() so read() pays
only a few attribute checks per frame (fast path returns the input untouched).
"""
from .atmosphere import apply_atmosphere
from .config import get_atmosphere, get_jitter, get_noise
from .frame import apply_jitter
from .sensor import apply_gaussian, apply_poisson, apply_salt_pepper


def _snapshot(cfg):
    atmo = get_atmosphere(cfg)
    noise = get_noise(cfg)
    return {
        "atmo_type": atmo.get("type", "clear"),
        "atmo_strength": float(atmo.get("strength", 0) or 0),
        "gauss_on": bool(noise.get("gaussian_enabled")) and float(noise.get("gaussian_std", 0) or 0) > 0,
        "gauss_std": float(noise.get("gaussian_std", 0) or 0),
        "spp_on": bool(noise.get("salt_pepper_enabled")) and float(noise.get("salt_pepper_prob", 0) or 0) > 0,
        "spp_prob": float(noise.get("salt_pepper_prob", 0) or 0),
        "poisson_on": bool(noise.get("poisson")),
        "jitter": float(get_jitter(cfg) or 0),
        "noise_cfg": dict(noise),
    }


def apply_environment(frame_img, cfg, rng=None):
    """Environment-side stage: atmosphere only (world effect, applied on viewport for cost)."""
    atmo = get_atmosphere(cfg)
    return apply_atmosphere(frame_img, atmo.get("type", "clear"),
                            float(atmo.get("strength", 0) or 0), rng=rng)


def apply_camera(frame_img, cfg, rng):
    """Camera-side stage: sensor noise + frame jitter."""
    noise = get_noise(cfg)
    out = frame_img
    if noise.get("gaussian_enabled") and float(noise.get("gaussian_std", 0) or 0) > 0:
        out = apply_gaussian(out, float(noise["gaussian_std"]), rng)
    if noise.get("salt_pepper_enabled") and float(noise.get("salt_pepper_prob", 0) or 0) > 0:
        out = apply_salt_pepper(out, float(noise["salt_pepper_prob"]), rng)
    if noise.get("poisson"):
        out = apply_poisson(out, rng)
    if float(get_jitter(cfg) or 0) > 0:
        out = apply_jitter(out, float(get_jitter(cfg)), rng)
    return out


def apply_disturbances(frame_img, cfg, rng):
    """Stateless one-shot: environment stage then camera stage (canonical order)."""
    snap = _snapshot(cfg)
    out = apply_atmosphere(frame_img, snap["atmo_type"], snap["atmo_strength"], rng=rng)
    if snap["gauss_on"]:
        out = apply_gaussian(out, snap["gauss_std"], rng)
    if snap["spp_on"]:
        out = apply_salt_pepper(out, snap["spp_prob"], rng)
    if snap["poisson_on"]:
        out = apply_poisson(out, rng)
    if snap["jitter"] > 0:
        out = apply_jitter(out, snap["jitter"], rng)
    return out


class DisturbancePipeline:
    """Stateful wrapper caching a cfg snapshot; rng stays owned by the caller."""

    def __init__(self, cfg):
        self.update_config(cfg)

    def update_config(self, cfg):
        snap = _snapshot(cfg)
        self.cfg = cfg
        self.atmo_type = snap["atmo_type"]
        self.atmo_strength = snap["atmo_strength"]
        self.noise_cfg = snap["noise_cfg"]
        self.jitter = snap["jitter"]
        self._gauss_on = snap["gauss_on"]
        self._gauss_std = snap["gauss_std"]
        self._spp_on = snap["spp_on"]
        self._spp_prob = snap["spp_prob"]
        self._poisson_on = snap["poisson_on"]
        self._image_active = (
            (self.atmo_type != "clear" and self.atmo_strength > 0)
            or self._gauss_on or self._spp_on or self._poisson_on or self.jitter > 0
        )

    @property
    def image_active(self):
        return self._image_active

    def apply_environment(self, frame_img, rng=None):
        if self.atmo_type == "clear" or self.atmo_strength <= 0:
            return frame_img
        return apply_atmosphere(frame_img, self.atmo_type, self.atmo_strength, rng=rng)

    def apply_camera(self, frame_img, rng):
        out = frame_img
        if self._gauss_on:
            out = apply_gaussian(out, self._gauss_std, rng)
        if self._spp_on:
            out = apply_salt_pepper(out, self._spp_prob, rng)
        if self._poisson_on:
            out = apply_poisson(out, rng)
        if self.jitter > 0:
            out = apply_jitter(out, self.jitter, rng)
        return out

    def apply(self, frame_img, rng):
        if not self._image_active:
            return frame_img
        out = self.apply_environment(frame_img, rng=rng)
        return self.apply_camera(out, rng)


__all__ = ["apply_disturbances", "apply_environment", "apply_camera", "DisturbancePipeline"]
