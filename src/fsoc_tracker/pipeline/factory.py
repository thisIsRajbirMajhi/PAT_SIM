"""Factories for the Pipeline module."""
from .detection import BeaconDetector
from .orchestration import SearchTrackPipeline
from .track import Tracker


def make_detector(cfg):
    return BeaconDetector(cfg)


def make_tracker(cfg):
    return Tracker(cfg)


def make_pipeline(cfg, controller=None):
    return SearchTrackPipeline(cfg, controller=controller)


__all__ = ["make_detector", "make_tracker", "make_pipeline"]
