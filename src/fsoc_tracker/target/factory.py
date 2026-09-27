"""Factories for the Target module."""
from .appearance import BeaconRenderer
from .dynamics import TargetManager, make_trajectory


def make_manager(cfg, seed=42):
    return TargetManager(cfg, seed=seed)


def make_renderer(cfg):
    return BeaconRenderer(cfg)


__all__ = ["make_trajectory", "make_manager", "make_renderer"]
