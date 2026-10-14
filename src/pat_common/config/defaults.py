# Functional Parameters and Specifications — limits & defaults per problem statement
# All ranges are enforced in Control Deck spin boxes and validated in schema.py
#
# Structured layout: per-domain defaults live in sections/*.py (one file per
# DEFAULT_CONFIG key). This module aggregates them so DEFAULT_CONFIG stays
# byte-identical to the previous monolith. New code may import sections
# directly (e.g. `from .sections.camera import CAMERA_DEFAULTS`).
import copy

from .sections import (
    ATMOSPHERE_DEFAULTS,
    CAMERA_DEFAULTS,
    CONTROLLER_DEFAULTS,
    DETECTOR_DEFAULTS,
    ENVIRONMENT_DEFAULTS,
    EXPERIMENT_DEFAULTS,
    NOISE_DEFAULTS,
    PLATFORM_DEFAULTS,
    TARGET_DEFAULTS,
    TRACKER_DEFAULTS,
    WORLD_DEFAULTS,
)

DEFAULT_CONFIG = {
    # --- Camera Parameters ---
    "world": copy.deepcopy(WORLD_DEFAULTS),
    "camera": copy.deepcopy(CAMERA_DEFAULTS),
    # --- Target Parameters ---
    "target": copy.deepcopy(TARGET_DEFAULTS),
    "platform": copy.deepcopy(PLATFORM_DEFAULTS),
    "noise": copy.deepcopy(NOISE_DEFAULTS),
    "atmosphere": copy.deepcopy(ATMOSPHERE_DEFAULTS),
    "environment": copy.deepcopy(ENVIRONMENT_DEFAULTS),
    "detector": copy.deepcopy(DETECTOR_DEFAULTS),
    "tracker": copy.deepcopy(TRACKER_DEFAULTS),
    "controller": copy.deepcopy(CONTROLLER_DEFAULTS),
    "experiment": copy.deepcopy(EXPERIMENT_DEFAULTS),
}
# Limits reference (enforced in Control Deck & schema):
# World 1000-4000 (spec min 2000), default 2000
# Resolution W 320-1920 H 240-1080 default 640x480
# FOV 1-12° default 4x3
# FPS 20-60 default 30
# Size 5-20 default 10
# /14 Max Pan/Tilt 5-10 °/s default 5 (UI allows 1-15 for tuning but schema warns outside 5-10)
# Update Interval ≥20 Hz default 30
