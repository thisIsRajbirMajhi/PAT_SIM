"""Shared config accessors — single home for get_* helpers.

Each domain module keeps its own thin config.py for discoverability, but new
code may import from here to avoid duplication.
"""


def get_world(cfg):
    return cfg.get("world", {})


def get_camera(cfg):
    return cfg.get("camera", {})


def get_target(cfg):
    return cfg.get("target", {})


def get_platform(cfg):
    return cfg.get("platform", {"type": "none", "speed_px_per_frame": 0.0})


def get_noise(cfg):
    return cfg.get("noise", {})


def get_atmosphere(cfg):
    return cfg.get("atmosphere", {"type": "clear", "strength": 0.0})


def get_environment(cfg):
    return cfg.get("environment", {})


def get_detector(cfg):
    return cfg.get("detector", {})


def get_tracker(cfg):
    return cfg.get("tracker", {})


def get_controller(cfg):
    return cfg.get("controller", {})


def get_experiment(cfg):
    return cfg.get("experiment", {})


def get_jitter(cfg):
    return float(cfg.get("camera", {}).get("jitter_px", 0.0))


def get_visibility_schedule(cfg):
    return cfg["target"].get("visibility_schedule") or cfg.get("visibility", {}).get("schedule")


__all__ = [
    "get_world",
    "get_camera",
    "get_target",
    "get_platform",
    "get_noise",
    "get_atmosphere",
    "get_environment",
    "get_detector",
    "get_tracker",
    "get_controller",
    "get_experiment",
    "get_jitter",
    "get_visibility_schedule",
]
