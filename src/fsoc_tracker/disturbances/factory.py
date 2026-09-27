"""Factories for shared disturbances."""
from .pipeline import DisturbancePipeline
from .platform import PlatformMotion


def make_platform_motion(cfg, seed=42):
    return PlatformMotion(cfg, seed=seed)


def make_pipeline(cfg):
    return DisturbancePipeline(cfg)


__all__ = ["make_platform_motion", "make_pipeline"]
