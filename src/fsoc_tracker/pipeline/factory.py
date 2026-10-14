"""Legacy compatibility: canonical factories live in pat_pipeline.factory."""
from pat_pipeline.factory import make_detector, make_pipeline, make_tracker

__all__ = ["make_detector", "make_tracker", "make_pipeline"]
