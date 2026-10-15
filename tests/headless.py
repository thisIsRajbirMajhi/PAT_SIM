""".
ONE SUITE. 80 cases under --extreme (alias --gauntlet / --full):
  X1..X14 hybrid families x 3 seeds = 42 cases
  E1..E26 edges                     = 26 cases
  R1..R12 robustness                = 12 cases

Every case:
  - far-start enforced (camera centre + target far corner)
  - distinct star clutter (density 0-0.006 cap)
  - verdict: STRICT-PASS / INTERMITTENT-PASS / FAIL / ERROR

Usage:
    python.exe headless.py --extreme --workers 4-8
    python.exe headless.py --extreme --workers 4 --timeout 600 --> For slower machines
"""

import argparse
import concurrent.futures
import copy
import csv
import glob
import hashlib
import json
import math
import os
import sys
import time
import traceback
import headless_report as R

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

import numpy as np

from pat_common.config.defaults import DEFAULT_CONFIG
from pat_common.config.loader import deep_merge

FAR_CORNERS = [[300, 300], [1700, 300], [300, 1700], [1700, 1700]]
FULL_SEEDS = (42, 7, 99)

ALL_TAGS = ("noise", "motion", "atmosphere", "sensor", "clutter",
            "control", "detection", "throughput", "ambiguity",
            "determinism", "robustness")
ALL_SEVERITIES = ("CORE", "HARD", "EXTREME", "EXPECTED-HARD")

# ---------------------------------------------------------------------------
# X family definitions: key, scenario name, corner index, frames, star,
# intermittent flag, base config, tags, severity.
# ---------------------------------------------------------------------------
X_DEFS = [
    {"key": "X1", "name": "X1-baseline", "desc": "Far-start baseline (must PASS).",
     "corner": 0, "frames": 900,
     "base": {"target": {"trajectory": "straight", "speed_px_per_frame": 3.0}},
     "star": (0.0005, 165), "intermittent": False,
     "tags": ["detection"], "severity": "CORE"},

    {"key": "X2", "name": "X2-sensor-hell", "desc": "Far start + heavy noise.",
     "corner": 1, "frames": 600,
     "base": {"target": {"trajectory": "straight", "speed_px_per_frame": 4.0, "size": 8},
              "noise": {"gaussian_enabled": True, "gaussian_std": 20.0,
                        "salt_pepper_enabled": True, "salt_pepper_prob": 0.10, "poisson": True}},
     "star": (0.0010, 175), "intermittent": False,
     "tags": ["noise", "sensor"], "severity": "HARD"},

    {"key": "X3", "name": "X3-motion-hell", "desc": "Far start + jitter + random platform.",
     "corner": 2, "frames": 600,
     "base": {"target": {"trajectory": "straight", "speed_px_per_frame": 6.0},
              "camera": {"jitter_px": 10.0},
              "platform": {"type": "random", "speed_px_per_frame": 15.0}},
     "star": (0.0015, 175), "intermittent": False,
     "tags": ["motion", "control"], "severity": "HARD"},

    {"key": "X4", "name": "X4-speed-demon", "desc": "Far start + max-speed figure-eight + jitter.",
     "corner": 3, "frames": 600,
     "base": {"target": {"trajectory": "figure_eight", "speed_px_per_frame": 20.0},
              "camera": {"jitter_px": 6.0},
              "platform": {"type": "linear", "speed_px_per_frame": 5.0}},
     "star": (0.0020, 185), "intermittent": False,
     "tags": ["motion", "control"], "severity": "EXTREME"},

    {"key": "X5", "name": "X5-tiny-target", "desc": "Far start + small fast target + star clutter.",
     "corner": 1, "frames": 900,
     "base": {"target": {"trajectory": "straight", "speed_px_per_frame": 6.0, "size": 6}},
     "star": (0.0030, 185), "intermittent": False,
     "tags": ["detection", "clutter"], "severity": "HARD"},

    {"key": "X6", "name": "X6-blink-dropout", "desc": "Far start + 5Hz blink + hidden dropout + drift.",
     "corner": 0, "frames": 900,
     "base": {"target": {"trajectory": "straight", "speed_px_per_frame": 3.0,
                         "blink_rate_hz": 5.0,
                         "visibility_schedule": [[1.0, 3.0, "hidden"]]},
              "platform": {"type": "random", "speed_px_per_frame": 3.0}},
     "star": (0.0012, 170), "intermittent": True,
     "tags": ["detection", "control"], "severity": "HARD"},

    {"key": "X7", "name": "X7-atmo-soup", "desc": "Far start + fog + jitter.",
     "corner": 0, "frames": 600,
     "base": {"target": {"trajectory": "straight", "speed_px_per_frame": 4.0, "size": 10},
              "atmosphere": {"type": "fog", "strength": 0.3},
              "camera": {"jitter_px": 8.0}},
     "star": (0.0008, 165), "intermittent": False,
     "tags": ["atmosphere", "motion"], "severity": "HARD"},

    {"key": "X8", "name": "X8-cold-start", "desc": "Far-corner crossing + stars + slow drift.",
     "corner": 0, "frames": 900,
     "base": {"target": {"trajectory": "straight", "speed_px_per_frame": 3.0},
              "platform": {"type": "linear", "speed_px_per_frame": 3.0}},
     "star": (0.0025, 185), "intermittent": False,
     "tags": ["clutter", "control"], "severity": "CORE"},

    {"key": "X9", "name": "X9-crowded", "desc": "Far start + 5 targets + dense stars + vignetting.",
     "corner": 1, "frames": 600,
     "base": {"target": {"trajectory": "figure_eight", "speed_px_per_frame": 6.0, "count": 5},
              "environment": {"vignetting_enabled": True, "vignetting_strength": 0.42}},
     "star": (0.0040, 190), "intermittent": True,
     "tags": ["clutter", "ambiguity"], "severity": "EXTREME"},

    {"key": "X10", "name": "X10-combined-hell", "desc": "Far start + noise + jitter + blink + fog + platform.",
     "corner": 0, "frames": 900,
     "base": {"target": {"trajectory": "straight", "speed_px_per_frame": 8.0,
                         "size": 12, "blink_rate_hz": 2.0},
              "noise": {"gaussian_enabled": True, "gaussian_std": 8.0,
                        "salt_pepper_enabled": True, "salt_pepper_prob": 0.05},
              "camera": {"jitter_px": 10.0},
              "atmosphere": {"type": "fog", "strength": 0.6},
              "platform": {"type": "linear", "speed_px_per_frame": 8.0}},
     "star": (0.0035, 185), "intermittent": True,
     "tags": ["noise", "atmosphere", "motion", "detection"], "severity": "EXTREME"},

    {"key": "X11", "name": "X11-subpixel-aliasing",
     "desc": "Size-5 @ 18px/f + jitter 14 + narrow FOV (sub-pixel aliasing).",
     "corner": 2, "frames": 600,
     "base": {"target": {"trajectory": "straight", "speed_px_per_frame": 18.0, "size": 5},
              "camera": {"jitter_px": 14.0, "resolution": [640, 480], "fov_deg": [3.0, 2.25]}},
     "star": (0.0025, 185), "intermittent": False,
     "tags": ["motion", "sensor", "detection"], "severity": "HARD"},

    {"key": "X12", "name": "X12-crossing-targets",
     "desc": "Two targets crossing on opposite straight trajectories (ambiguity).",
     "corner": 0, "frames": 600,
     "base": {"target": {"count": 2, "trajectories": ["straight", "straight"],
                         "speeds": [8.0, 8.0], "size": 8}},
     "star": (0.0030, 185), "intermittent": True,
     "tags": ["ambiguity", "clutter"], "severity": "HARD"},

    {"key": "X13", "name": "X13-aggressive-manoeuvre",
     "desc": "Sinusoidal target + spiral platform + heavy jitter (control stress).",
     "corner": 3, "frames": 600,
     "base": {"target": {"trajectory": "sinusoidal", "speed_px_per_frame": 15.0, "size": 8},
              "camera": {"jitter_px": 16.0},
              "platform": {"type": "spiral", "speed_px_per_frame": 12.0}},
     "star": (0.0028, 185), "intermittent": False,
     "tags": ["motion", "control"], "severity": "EXTREME"},

    {"key": "X14", "name": "X14-long-tail-drift",
     "desc": "1200 frames slow target + star storm + linear platform drift.",
     "corner": 0, "frames": 1200,
     "base": {"target": {"trajectory": "straight", "speed_px_per_frame": 2.5, "size": 8},
              "platform": {"type": "linear", "speed_px_per_frame": 2.0}},
     "star": (0.0050, 190), "intermittent": False,
     "tags": ["clutter", "motion", "control"], "severity": "HARD"},
]

# ---------------------------------------------------------------------------
# E definitions: one-shot edges.
# ---------------------------------------------------------------------------
E_DEFS = [
    {"key": "E1", "name": "E1-max-corners", "desc": "Max-separation opposite corners.",
     "over": {"target": {"trajectory": "straight", "speed_px_per_frame": 3.0, "size": 10}},
     "corner": 3, "frames": 600, "star": (0.0018, 175), "intermittent": False,
     "tags": ["detection"], "severity": "CORE"},
    {"key": "E2", "name": "E2-at-limit-grind", "desc": "Start at world edge, sweep grinds wall.",
     "over": {"target": {"trajectory": "straight", "speed_px_per_frame": 2.0, "size": 10}},
     "corner": 2, "frames": 600, "star": (0.0022, 180), "intermittent": False,
     "tags": ["control"], "severity": "HARD"},
    {"key": "E3", "name": "E3-min-size-max-speed", "desc": "Size 5 at 20px/f.",
     "over": {"target": {"trajectory": "straight", "speed_px_per_frame": 20.0, "size": 5}},
     "corner": 1, "frames": 600, "star": (0.0028, 185), "intermittent": False,
     "tags": ["motion", "detection"], "severity": "EXTREME"},
    {"key": "E4", "name": "E4-overlap-swarm", "desc": "5 targets same trajectory overlap.",
     "over": {"target": {"trajectory": "circular", "speed_px_per_frame": 4.0, "count": 5}},
     "corner": 0, "frames": 600, "star": (0.0032, 185), "intermittent": True,
     "tags": ["ambiguity"], "severity": "HARD"},
    {"key": "E5", "name": "E5-strobe-50hz", "desc": "50Hz strobe blink.",
     "over": {"target": {"trajectory": "straight", "speed_px_per_frame": 3.0, "blink_rate_hz": 50.0}},
     "corner": 0, "frames": 600, "star": (0.0011, 170), "intermittent": True,
     "tags": ["detection"], "severity": "EXTREME"},
    {"key": "E6", "name": "E6-fog-blind", "desc": "Fog 1.0 blinding (EXPECTED-HARD).",
     "over": {"target": {"trajectory": "straight", "speed_px_per_frame": 3.0},
              "atmosphere": {"type": "fog", "strength": 1.0}},
     "corner": 0, "frames": 600, "star": (0.0009, 165), "intermittent": False,
     "tags": ["atmosphere"], "severity": "EXPECTED-HARD"},
    {"key": "E7", "name": "E7-jitter-cap", "desc": "Jitter 20px cap (EXPECTED-HARD).",
     "over": {"target": {"trajectory": "straight", "speed_px_per_frame": 3.0},
              "camera": {"jitter_px": 20.0}},
     "corner": 2, "frames": 600, "star": (0.0016, 175), "intermittent": False,
     "tags": ["motion", "control"], "severity": "EXPECTED-HARD"},
    {"key": "E8", "name": "E8-fps-mismatch", "desc": "FPS 20 / update 20Hz.",
     "over": {"target": {"trajectory": "straight", "speed_px_per_frame": 3.0},
              "camera": {"fps": 20.0, "update_interval_hz": 20.0}},
     "corner": 0, "frames": 400, "star": (0.0007, 165), "intermittent": False,
     "tags": ["sensor", "throughput"], "severity": "HARD"},
    {"key": "E9", "name": "E9-narrow-fov", "desc": "320x240 narrow FOV.",
     "over": {"target": {"trajectory": "straight", "speed_px_per_frame": 3.0},
              "camera": {"resolution": [320, 240], "fov_deg": [2.0, 1.5]}},
     "corner": 1, "frames": 600, "star": (0.0014, 172), "intermittent": False,
     "tags": ["sensor"], "severity": "HARD"},
    {"key": "E10", "name": "E10-colour-mode", "desc": "Colour camera mode.",
     "over": {"target": {"trajectory": "circular", "speed_px_per_frame": 3.0},
              "camera": {"type": "colour"}},
     "corner": 3, "frames": 600, "star": (0.0019, 178), "intermittent": False,
     "tags": ["sensor"], "severity": "CORE"},
    {"key": "E11", "name": "E11-lowlight-rain", "desc": "Low-light 0.8 + rain.",
     "over": {"target": {"trajectory": "straight", "speed_px_per_frame": 3.0},
              "atmosphere": {"type": "low_light", "strength": 0.8}},
     "corner": 0, "frames": 600, "star": (0.0026, 182), "intermittent": False,
     "tags": ["atmosphere"], "severity": "HARD"},
    {"key": "E12", "name": "E12-per-target-list", "desc": "Per-target trajectories+speeds.",
     "over": {"target": {"count": 5,
                         "trajectories": ["straight", "circular", "figure_eight", "random", "sinusoidal"],
                         "speeds": [3.0, 8.0, 15.0, 5.0, 20.0]}},
     "corner": 1, "frames": 600, "star": (0.0045, 190), "intermittent": True,
     "tags": ["motion", "ambiguity"], "severity": "EXTREME"},
    {"key": "E13", "name": "E13-gimbal-saturation",
     "desc": "20px/f fig8 + random platform 20 + jitter 15 (saturates gimbal).",
     "over": {"target": {"trajectory": "figure_eight", "speed_px_per_frame": 20.0, "size": 8},
              "camera": {"jitter_px": 15.0},
              "platform": {"type": "random", "speed_px_per_frame": 20.0}},
     "corner": 3, "frames": 600, "star": (0.0033, 186), "intermittent": False,
     "tags": ["motion", "control"], "severity": "EXTREME"},
    {"key": "E14", "name": "E14-blackout-gauntlet",
     "desc": "8Hz blink + 3 hidden windows + drift.",
     "over": {"target": {"trajectory": "sinusoidal", "speed_px_per_frame": 5.0, "blink_rate_hz": 8.0,
                         "visibility_schedule": [[1.0, 2.0, "hidden"], [4.0, 5.5, "hidden"],
                                                 [8.0, 10.0, "hidden"]]},
              "platform": {"type": "random", "speed_px_per_frame": 4.0}},
     "corner": 0, "frames": 900, "star": (0.0021, 178), "intermittent": True,
     "tags": ["detection", "control"], "severity": "EXTREME"},
    {"key": "E15", "name": "E15-star-storm",
     "desc": "Max star density 0.006 + vignetting + size-5 target.",
     "over": {"target": {"trajectory": "straight", "speed_px_per_frame": 5.0, "size": 5},
              "environment": {"vignetting_enabled": True, "vignetting_strength": 0.5}},
     "corner": 1, "frames": 600, "star": (0.006, 195), "intermittent": False,
     "tags": ["clutter", "detection"], "severity": "EXTREME"},
    {"key": "E16", "name": "E16-low-contrast",
     "desc": "Size 6 + haze 0.8 + jitter 12 (dim vs veil).",
     "over": {"target": {"trajectory": "straight", "speed_px_per_frame": 4.0, "size": 6},
              "atmosphere": {"type": "haze", "strength": 0.8},
              "camera": {"jitter_px": 12.0}},
     "corner": 2, "frames": 600, "star": (0.0013, 172), "intermittent": False,
     "tags": ["atmosphere", "detection"], "severity": "HARD"},
    {"key": "E17", "name": "E17-blink-swarm",
     "desc": "5 targets + 8Hz global blink + dense stars.",
     "over": {"target": {"trajectory": "circular", "speed_px_per_frame": 6.0, "count": 5,
                         "blink_rate_hz": 8.0}},
     "corner": 0, "frames": 600, "star": (0.005, 192), "intermittent": True,
     "tags": ["detection", "ambiguity"], "severity": "EXTREME"},
    {"key": "E18", "name": "E18-wide-fov-hd",
     "desc": "1280x960 @ 8x6deg wide FOV (small px/deg).",
     "over": {"target": {"trajectory": "figure_eight", "speed_px_per_frame": 8.0, "size": 8},
              "camera": {"resolution": [1280, 960], "fov_deg": [8.0, 6.0]}},
     "corner": 3, "frames": 600, "star": (0.0029, 184), "intermittent": False,
     "tags": ["sensor"], "severity": "HARD"},
    {"key": "E19", "name": "E19-spiral-ambush",
     "desc": "Spiral 12px/f + linear platform 10 + jitter 8.",
     "over": {"target": {"trajectory": "spiral", "speed_px_per_frame": 12.0, "size": 8},
              "camera": {"jitter_px": 8.0},
              "platform": {"type": "linear", "speed_px_per_frame": 10.0}},
     "corner": 2, "frames": 600, "star": (0.0038, 188), "intermittent": False,
     "tags": ["motion", "control"], "severity": "HARD"},
    {"key": "E20", "name": "E20-sensor-max",
     "desc": "Gauss 20 + spp 0.15 max + poisson + size 5 (worst sensor).",
     "over": {"target": {"trajectory": "straight", "speed_px_per_frame": 4.0, "size": 5},
              "noise": {"gaussian_enabled": True, "gaussian_std": 20.0,
                        "salt_pepper_enabled": True, "salt_pepper_prob": 0.15, "poisson": True}},
     "corner": 1, "frames": 600, "star": (0.0055, 194), "intermittent": False,
     "tags": ["noise", "detection"], "severity": "EXPECTED-HARD"},

    # ---- new edges ----
    {"key": "E21", "name": "E21-hd60-throughput",
     "desc": "1920x1080 @ 60fps (max pipeline throughput).",
     "over": {"target": {"trajectory": "straight", "speed_px_per_frame": 5.0, "size": 8},
              "camera": {"resolution": [1920, 1080], "fps": 60.0, "update_interval_hz": 60.0}},
     "corner": 0, "frames": 600, "star": (0.0010, 170), "intermittent": False,
     "tags": ["sensor", "throughput"], "severity": "HARD"},
    {"key": "E22", "name": "E22-mini60-fast",
     "desc": "320x240 @ 60fps + speed 15 (tiny + fast + high rate).",
     "over": {"target": {"trajectory": "figure_eight", "speed_px_per_frame": 15.0, "size": 5},
              "camera": {"resolution": [320, 240], "fps": 60.0, "update_interval_hz": 60.0,
                         "fov_deg": [2.0, 1.5]}},
     "corner": 1, "frames": 600, "star": (0.0020, 180), "intermittent": False,
     "tags": ["sensor", "motion", "throughput"], "severity": "EXTREME"},
    {"key": "E23", "name": "E23-opposite-crossing",
     "desc": "Two targets on opposite circular trajectories (crossing ambiguity).",
     "over": {"target": {"count": 2, "trajectories": ["circular", "circular"],
                         "speeds": [10.0, 10.0], "size": 8}},
     "corner": 3, "frames": 600, "star": (0.0035, 188), "intermittent": True,
     "tags": ["ambiguity", "motion"], "severity": "HARD"},
    {"key": "E24", "name": "E24-full-trajectory-matrix",
     "desc": "5 targets, one per trajectory type (straight/circ/fig8/random/sinusoid).",
     "over": {"target": {"count": 5,
                         "trajectories": ["straight", "circular", "figure_eight", "random", "sinusoidal"],
                         "speeds": [4.0, 8.0, 12.0, 6.0, 10.0], "size": 8}},
     "corner": 0, "frames": 600, "star": (0.0040, 188), "intermittent": True,
     "tags": ["motion", "ambiguity"], "severity": "EXTREME"},
    {"key": "E25", "name": "E25-zero-star-void",
     "desc": "Zero stars, pure black background — detector sees only target.",
     "over": {"target": {"trajectory": "straight", "speed_px_per_frame": 4.0, "size": 8},
              "environment": {"stars_density": 0.0, "stars_enabled": True}},
     "corner": 0, "frames": 600, "star": (0.0, 0), "intermittent": False,
     "tags": ["detection"], "severity": "CORE"},
    {"key": "E26", "name": "E26-triple-threat",
     "desc": "Max stars + max noise + size-5 target (triple threat).",
     "over": {"target": {"trajectory": "straight", "speed_px_per_frame": 6.0, "size": 5},
              "noise": {"gaussian_enabled": True, "gaussian_std": 20.0,
                        "salt_pepper_enabled": True, "salt_pepper_prob": 0.15, "poisson": True}},
     "corner": 2, "frames": 600, "star": (0.006, 195), "intermittent": False,
     "tags": ["clutter", "noise", "detection"], "severity": "EXPECTED-HARD"},
]

# ---------------------------------------------------------------------------
# R robustness definitions.
# ---------------------------------------------------------------------------
R_DEFS = [
    {"key": "R1",  "name": "R1-midrun-fog-switch",  "desc": "Fog 0->0.5 at frame 200.",
     "tags": ["atmosphere", "robustness"], "severity": "HARD"},
    {"key": "R2",  "name": "R2-reset-repro",        "desc": "Reset(seed) twice identical hash.",
     "tags": ["determinism", "robustness"], "severity": "CORE"},
    {"key": "R3",  "name": "R3-none-frame-guard",   "desc": "None/empty frame -> invalid, no crash.",
     "tags": ["robustness"], "severity": "CORE"},
    {"key": "R4",  "name": "R4-at-limit-truth",     "desc": "is_at_limit true at wall + push-out.",
     "tags": ["control", "robustness"], "severity": "CORE"},
    {"key": "R5",  "name": "R5-latency-budget",     "desc": "Avg proc <33ms at 30fps.",
     "tags": ["throughput", "robustness"], "severity": "CORE"},
    {"key": "R6",  "name": "R6-long-soak",          "desc": "1200-frame X1 soak: no drift, no error growth.",
     "tags": ["robustness"], "severity": "HARD"},
    {"key": "R7",  "name": "R7-seed-variance",      "desc": "Same X, seeds 42 vs 7 differ (fuzz varies).",
     "tags": ["determinism", "robustness"], "severity": "HARD"},
    {"key": "R8",  "name": "R8-saturation-clamp",   "desc": "Cmd rates never exceed max pan/tilt under E13 drive.",
     "tags": ["control", "robustness"], "severity": "CORE"},

    # ---- new robustness ----
    {"key": "R9",  "name": "R9-config-validation-gate",
     "desc": "load_config() validates defaults and rejects obvious out-of-range.",
     "tags": ["robustness", "determinism"], "severity": "CORE"},
    {"key": "R10", "name": "R10-determinism-hash",
     "desc": "Same seed -> identical frame hash twice (source-level).",
     "tags": ["determinism", "robustness"], "severity": "HARD"},
    {"key": "R11", "name": "R11-nan-inf-guard",
     "desc": "NaN/Inf frames do not crash or poison pipeline state.",
     "tags": ["robustness"], "severity": "HARD"},
    {"key": "R12", "name": "R12-reset-isolation",
     "desc": "reset() clears all pipeline state (fresh run reproducible).",
     "tags": ["robustness", "determinism"], "severity": "CORE"},
]

# ---------------------------------------------------------------------------
# Benchmarks to beat.
# ---------------------------------------------------------------------------
BENCHMARKS = {
    "X1":  {"lock": 50.0, "rmse": 5.0, "first": 450, "losses": 2, "note": "baseline must PASS"},
    "X2":  {"lock": 20.0, "rmse": 12.0, "first": 550, "losses": 5, "note": "heavy noise"},
    "X3":  {"lock": 15.0, "rmse": 15.0, "first": 550, "losses": 6, "note": "jitter+platform"},
    "X4":  {"lock": 10.0, "rmse": 15.0, "first": 550, "losses": 8, "note": "max speed"},
    "X5":  {"lock": 30.0, "rmse": 8.0, "first": 500, "losses": 4, "note": "tiny vs clutter"},
    "X6":  {"lock": 10.0, "rmse": 12.0, "first": 600, "losses": 8, "acq": 2, "valid": 15.0, "note": "blink: intermittent ok"},
    "X7":  {"lock": 20.0, "rmse": 12.0, "first": 550, "losses": 5, "note": "fog+jitter"},
    "X8":  {"lock": 50.0, "rmse": 8.0, "first": 450, "losses": 3, "note": "cold start must PASS"},
    "X9":  {"lock": 10.0, "rmse": 15.0, "first": 600, "losses": 8, "acq": 2, "valid": 15.0, "note": "crowded: intermittent ok"},
    "X10": {"lock": 5.0, "rmse": 15.0, "first": 800, "losses": 10, "acq": 1, "valid": 10.0, "note": "EXPECTED-HARD combined"},
    "X11": {"lock": 10.0, "rmse": 15.0, "first": 600, "losses": 8, "note": "sub-pixel aliasing"},
    "X12": {"lock": 10.0, "rmse": 15.0, "first": 600, "losses": 8, "acq": 2, "valid": 10.0, "note": "crossing: intermittent ok"},
    "X13": {"lock": 5.0, "rmse": 18.0, "first": 700, "losses": 10, "note": "aggressive manoeuvre"},
    "X14": {"lock": 40.0, "rmse": 10.0, "first": 500, "losses": 5, "note": "long-tail drift"},

    "E1":  {"lock": 40.0, "rmse": 10.0, "first": 500, "losses": 4, "note": "max corners"},
    "E2":  {"lock": 40.0, "rmse": 10.0, "first": 500, "losses": 4, "note": "wall grind"},
    "E3":  {"lock": 15.0, "rmse": 12.0, "first": 550, "losses": 6, "note": "min size max speed"},
    "E4":  {"lock": 10.0, "rmse": 15.0, "first": 600, "losses": 8, "acq": 2, "valid": 10.0, "note": "swarm: intermittent ok"},
    "E5":  {"lock": 5.0, "rmse": 15.0, "first": 600, "losses": 10, "acq": 2, "valid": 10.0, "note": "strobe: intermittent ok"},
    "E6":  {"lock": 0.0, "rmse": 30.0, "first": 9999, "losses": 99, "note": "EXPECTED-HARD blind: must complete, no crash"},
    "E7":  {"lock": 5.0, "rmse": 20.0, "first": 800, "losses": 10, "note": "EXPECTED-HARD jitter cap"},
    "E8":  {"lock": 40.0, "rmse": 10.0, "first": 400, "losses": 4, "note": "fps mismatch"},
    "E9":  {"lock": 40.0, "rmse": 10.0, "first": 500, "losses": 4, "note": "narrow FOV"},
    "E10": {"lock": 40.0, "rmse": 10.0, "first": 500, "losses": 4, "note": "colour mode"},
    "E11": {"lock": 15.0, "rmse": 15.0, "first": 600, "losses": 6, "note": "low-light"},
    "E12": {"lock": 10.0, "rmse": 15.0, "first": 600, "losses": 8, "acq": 2, "valid": 10.0, "note": "per-target: intermittent ok"},
    "E13": {"lock": 5.0, "rmse": 18.0, "first": 700, "losses": 10, "note": "EXPECTED-HARD saturation"},
    "E14": {"lock": 5.0, "rmse": 15.0, "first": 700, "losses": 10, "acq": 2, "valid": 10.0, "note": "blackout: intermittent ok"},
    "E15": {"lock": 10.0, "rmse": 12.0, "first": 600, "losses": 8, "note": "star storm vs tiny"},
    "E16": {"lock": 10.0, "rmse": 15.0, "first": 600, "losses": 8, "note": "low contrast haze"},
    "E17": {"lock": 5.0, "rmse": 15.0, "first": 700, "losses": 10, "acq": 2, "valid": 10.0, "note": "blink swarm: intermittent ok"},
    "E18": {"lock": 30.0, "rmse": 12.0, "first": 550, "losses": 5, "note": "wide FOV HD"},
    "E19": {"lock": 10.0, "rmse": 15.0, "first": 600, "losses": 8, "note": "spiral ambush"},
    "E20": {"lock": 5.0, "rmse": 18.0, "first": 700, "losses": 10, "note": "EXPECTED-HARD worst sensor"},
    "E21": {"lock": 40.0, "rmse": 10.0, "first": 500, "losses": 4, "note": "HD60 throughput"},
    "E22": {"lock": 10.0, "rmse": 15.0, "first": 600, "losses": 8, "note": "tiny fast 60fps"},
    "E23": {"lock": 10.0, "rmse": 15.0, "first": 600, "losses": 8, "acq": 2, "valid": 10.0, "note": "opposite crossing: intermittent ok"},
    "E24": {"lock": 10.0, "rmse": 15.0, "first": 600, "losses": 8, "acq": 2, "valid": 10.0, "note": "full trajectory matrix: intermittent ok"},
    "E25": {"lock": 50.0, "rmse": 6.0, "first": 450, "losses": 3, "note": "zero-clutter baseline"},
    "E26": {"lock": 5.0, "rmse": 18.0, "first": 700, "losses": 10, "note": "EXPECTED-HARD triple threat"},

    "R1":  {"note": "must complete without ERROR"},
    "R2":  {"note": "reset twice identical"},
    "R3":  {"note": "None/empty guarded"},
    "R4":  {"note": "is_at_limit true"},
    "R5":  {"note": "avg proc <33ms"},
    "R6":  {"lock": 40.0, "rmse": 8.0, "first": 500, "losses": 4, "note": "1200f soak stability"},
    "R7":  {"note": "seeds differ (dynamic sampling active)"},
    "R8":  {"note": "cmd clamp respected"},
    "R9":  {"note": "config validation"},
    "R10": {"note": "source determinism hash"},
    "R11": {"note": "nan/inf guard"},
    "R12": {"note": "reset isolation"},
}

# ---------------------------------------------------------------------------
# Helpers.
# ---------------------------------------------------------------------------

def bench_str(bkey):
    b = BENCHMARKS.get(bkey, {})
    parts = []
    for k in ("lock", "rmse", "first", "losses", "acq", "valid"):
        if k in b:
            parts.append(f"{k}={b[k]}")
    s = " ".join(parts) if parts else "complete/no-crash"
    if b.get("note"):
        s += f" [{b['note']}]"
    return s


def _tags_str(tags):
    if not tags:
        return ""
    return ",".join(tags)


def _safe_float(v, default=0.0):
    try:
        f = float(v)
        if math.isnan(f) or math.isinf(f):
            return default
        return f
    except Exception:
        return default


def _compute_in_fov(source, gt):
    """Robust in-FOV flag.

    Handles NumPy arrays / lists for `gt.world_pos` without triggering the
    ambiguous-truth-value error inside `... not in (None, (0, 0))`. Returns
    None when `gt` or `world_pos` is missing/zero, or the projection fails.
    """
    if gt is None:
        return None
    wp = getattr(gt, "world_pos", None)
    if wp is None:
        return None
    try:
        is_zero = (len(wp) == 2
                   and bool(wp[0] == 0)
                   and bool(wp[1] == 0))
    except (TypeError, IndexError, ValueError):
        is_zero = False
    if is_zero:
        return None
    try:
        return source.camera.world_to_image(wp) is not None
    except Exception:
        return None


def _sanitize_result(r):
    """Replace NaN/Inf and clamp obviously-bad metric fields."""
    for k, d in (("lock_pct", 0.0), ("rmse", 0.0), ("p95", 0.0),
                 ("valid_pct", 0.0), ("avg_ms", 0.0), ("max_ms", 0.0)):
        if k in r:
            r[k] = _safe_float(r.get(k), d)
    if r.get("first_lock") is not None:
        fl = _safe_float(r["first_lock"], None)
        r["first_lock"] = int(fl) if fl is not None else None
    for k in ("frames", "losses", "acq", "seed"):
        if k in r:
            try:
                r[k] = int(r[k])
            except Exception:
                r[k] = 0
    return r


def enforce_far_start(cfg, corner_idx=0):
    """Force camera centre + target far corner."""
    cfg = copy.deepcopy(cfg)
    cfg.setdefault("camera", {})["initial_position"] = "centre"
    cfg["camera"].pop("initial_pan", None)
    cfg["camera"].pop("initial_tilt", None)
    corner = list(FAR_CORNERS[int(corner_idx) % len(FAR_CORNERS)])
    t = cfg.setdefault("target", {})
    t["initial_mode"] = "user-defined"
    t["initial_pos"] = corner
    return cfg


def apply_stars(cfg, density, brightness):
    cfg = copy.deepcopy(cfg)
    e = cfg.setdefault("environment", {})
    e["stars_enabled"] = True
    e["stars_density"] = float(np.clip(density, 0.0, 0.006))
    e["stars_brightness"] = int(brightness)
    return cfg


def _stable_key_offset(key):
    return sum(ord(c) * (i + 1) for i, c in enumerate(str(key))) % 1000


def sample_dynamic(xkey, seed, rng):
    """Seeded dynamic jitter inside validated caps (seed 42 = baseline {})."""
    if int(seed) == 42:
        return {}
    u = lambda a, b: float(rng.uniform(a, b))
    if xkey == "X1":
        return {"target": {"speed_px_per_frame": u(2.5, 3.5)},
                "environment": {"stars_density": u(0.0004, 0.0008)}}
    if xkey == "X2":
        return {"target": {"speed_px_per_frame": u(3.0, 5.0)},
                "noise": {"gaussian_enabled": True, "gaussian_std": u(12, 20),
                          "salt_pepper_enabled": True, "salt_pepper_prob": u(0.05, 0.12), "poisson": True},
                "environment": {"stars_density": u(0.0008, 0.0015)}}
    if xkey == "X3":
        return {"target": {"speed_px_per_frame": u(5.0, 8.0)},
                "camera": {"jitter_px": u(8, 16)},
                "platform": {"type": "random", "speed_px_per_frame": u(10, 18)},
                "environment": {"stars_density": u(0.001, 0.002)}}
    if xkey == "X4":
        return {"target": {"speed_px_per_frame": u(15, 20)},
                "camera": {"jitter_px": u(4, 8)},
                "platform": {"type": "linear", "speed_px_per_frame": u(3, 6)},
                "environment": {"stars_density": u(0.0015, 0.0025)}}
    if xkey == "X5":
        return {"target": {"speed_px_per_frame": u(5.0, 7.0), "size": int(rng.integers(5, 7))},
                "environment": {"stars_density": u(0.0025, 0.005)}}
    if xkey == "X6":
        s, e = u(0.5, 2.5), u(0.5, 2.5) + u(1.0, 2.0)
        return {"target": {"blink_rate_hz": u(2, 10),
                           "visibility_schedule": [[round(s, 2), round(e, 2), "hidden"]]},
                "environment": {"stars_density": u(0.001, 0.0018)}}
    if xkey == "X7":
        return {"target": {"speed_px_per_frame": u(3.0, 5.0)},
                "atmosphere": {"type": "fog", "strength": u(0.3, 0.6)},
                "camera": {"jitter_px": u(6, 10)},
                "environment": {"stars_density": u(0.0006, 0.0012)}}
    if xkey == "X8":
        return {"target": {"speed_px_per_frame": u(2.5, 3.5)},
                "platform": {"type": "linear", "speed_px_per_frame": u(2, 4)},
                "environment": {"stars_density": u(0.002, 0.003)}}
    if xkey == "X9":
        return {"target": {"speed_px_per_frame": u(5.0, 7.0), "count": int(rng.integers(3, 6))},
                "environment": {"stars_density": u(0.003, 0.005)}}
    if xkey == "X10":
        return {"target": {"speed_px_per_frame": u(7.0, 9.0), "blink_rate_hz": u(2, 5)},
                "noise": {"gaussian_enabled": True, "gaussian_std": u(6, 10),
                          "salt_pepper_enabled": True, "salt_pepper_prob": u(0.03, 0.06)},
                "camera": {"jitter_px": u(8, 12)},
                "atmosphere": {"type": "fog", "strength": u(0.4, 0.6)},
                "platform": {"type": "linear", "speed_px_per_frame": u(5, 9)},
                "environment": {"stars_density": u(0.003, 0.004)}}
    if xkey == "X11":
        return {"target": {"speed_px_per_frame": u(15, 20), "size": int(rng.integers(5, 7))},
                "camera": {"jitter_px": u(10, 18)},
                "environment": {"stars_density": u(0.002, 0.003)}}
    if xkey == "X12":
        return {"target": {"count": 2,
                           "trajectories": ["straight", "straight"],
                           "speeds": [u(6, 10), u(6, 10)],
                           "size": int(rng.integers(7, 10))},
                "environment": {"stars_density": u(0.0025, 0.0035)}}
    if xkey == "X13":
        return {"target": {"trajectory": "sinusoidal", "speed_px_per_frame": u(12, 18)},
                "camera": {"jitter_px": u(12, 18)},
                "platform": {"type": "spiral", "speed_px_per_frame": u(8, 15)},
                "environment": {"stars_density": u(0.002, 0.0035)}}
    if xkey == "X14":
        return {"target": {"speed_px_per_frame": u(2.0, 3.0), "size": int(rng.integers(7, 10))},
                "platform": {"type": "linear", "speed_px_per_frame": u(1.5, 3.0)},
                "environment": {"stars_density": u(0.004, 0.006)}}
    return {}


WINNER_OVERRIDES: dict = {}

# Camera keys a winner file may override. Fixed hardware (fps,
# max_pan/tilt_speed, fov_deg, resolution, ...) is always dropped.
_CAMERA_ALLOWLIST = frozenset(
    {"initial_position", "initial_pan", "initial_tilt", "update_interval_hz"})
# Camera start keys applied AFTER enforce_far_start (which resets the
# camera to centre and pops pan/tilt), so tuned starts survive.
_CAMERA_START_KEYS = ("initial_position", "initial_pan", "initial_tilt")
# update_interval_hz values below this are rejected (kept out of overrides).
_UPDATE_INTERVAL_HZ_FLOOR = 20.0


def set_winner_overrides(path: str | None) -> dict:
    """Load winner system params from a JSON file, keeping only tunable keys.

    Keeps `detector`/`tracker`/`controller` subtrees and the camera
    allowlist (`initial_position`, `initial_pan`, `initial_tilt`,
    `update_interval_hz`). Drops everything else, including fixed hardware
    (camera `fps`, `max_pan/tilt_speed`, `fov_deg`, `resolution`) and test
    conditions (world/target/noise/atmosphere/platform/environment/
    experiment). `update_interval_hz` below 20 Hz is rejected. `None`
    resets to {}.
    """
    global WINNER_OVERRIDES
    if path is None:
        WINNER_OVERRIDES = {}
        return {}
    with open(path) as f:
        data = json.load(f)
    if not isinstance(data, dict):
        data = {}
    kept: dict = {}
    for key in ("detector", "tracker", "controller"):
        if isinstance(data.get(key), dict):
            kept[key] = copy.deepcopy(data[key])
    cam = data.get("camera")
    if isinstance(cam, dict):
        kept_cam = {}
        for key in sorted(_CAMERA_ALLOWLIST):
            if key not in cam:
                continue
            if key == "update_interval_hz":
                try:
                    if float(cam[key]) < _UPDATE_INTERVAL_HZ_FLOOR:
                        continue
                except (TypeError, ValueError):
                    continue
            kept_cam[key] = copy.deepcopy(cam[key])
        if kept_cam:
            kept["camera"] = kept_cam
    WINNER_OVERRIDES = kept
    return copy.deepcopy(WINNER_OVERRIDES)


def _split_winner_overrides():
    """Split WINNER_OVERRIDES into pre/post far-start batches.

    Returns (pre, post): `post` holds the camera start keys
    (`initial_position`, `initial_pan`, `initial_tilt`) merged AFTER
    `enforce_far_start`; `pre` holds everything else, merged after the
    base config and before stars/far-start.
    """
    pre = copy.deepcopy(WINNER_OVERRIDES)
    post: dict = {}
    cam = pre.get("camera")
    if isinstance(cam, dict):
        for key in _CAMERA_START_KEYS:
            if key in cam:
                post.setdefault("camera", {})[key] = cam.pop(key)
        if not cam:
            pre.pop("camera", None)
    return pre, post


def _apply_spec_winner(spec):
    """Restore WINNER_OVERRIDES inside a worker from the spec dict.

    ProcessPoolExecutor on spawn platforms (Windows) does not inherit
    module globals, so main() embeds a copy of the overrides in each spec.
    """
    global WINNER_OVERRIDES
    w = spec.get("winner")
    if isinstance(w, dict) and w:
        WINNER_OVERRIDES = copy.deepcopy(w)
    else:
        WINNER_OVERRIDES = {}


def build_case_config(xdef, seed):
    rng = np.random.default_rng(int(seed) * 7919 + _stable_key_offset(xdef["key"]))
    cfg = deep_merge(copy.deepcopy(DEFAULT_CONFIG), copy.deepcopy(xdef["base"]))
    cfg = deep_merge(cfg, sample_dynamic(xdef["key"], seed, rng))
    pre_winner, post_winner = _split_winner_overrides()
    if pre_winner:
        cfg = deep_merge(cfg, pre_winner)
    dens, bri = xdef["star"]
    try:
        dyn_dens = cfg.get("environment", {}).get("stars_density", None)
        if int(seed) != 42 and dyn_dens is not None:
            dens = float(dyn_dens)
    except Exception:
        pass
    cfg = apply_stars(cfg, dens, bri)
    cfg = enforce_far_start(cfg, xdef["corner"])
    if post_winner:
        cfg = deep_merge(cfg, post_winner)
    fps = max(float(cfg["camera"].get("fps", 30.0)), 1)
    cfg["experiment"]["duration_s"] = round(xdef["frames"] / fps, 2)
    cfg["experiment"]["seed"] = int(seed)
    return cfg


def build_edge_config(edef, seed=42):
    cfg = deep_merge(copy.deepcopy(DEFAULT_CONFIG), copy.deepcopy(edef["over"]))
    pre_winner, post_winner = _split_winner_overrides()
    if pre_winner:
        cfg = deep_merge(cfg, pre_winner)
    cfg = apply_stars(cfg, *edef["star"])
    cfg = enforce_far_start(cfg, edef["corner"])
    if post_winner:
        cfg = deep_merge(cfg, post_winner)
    fps = max(float(cfg["camera"].get("fps", 30.0)), 1)
    cfg["experiment"]["duration_s"] = round(edef["frames"] / fps, 2)
    cfg["experiment"]["seed"] = int(seed)
    return cfg


def verdict(summary, intermittent_allowed, bkey=None):
    if bkey == "E6":
        return "STRICT-PASS", "blind: completed without crash (EXPECTED-HARD)"
    lock = _safe_float(summary.get("lock_retention_pct", 0.0))
    rmse = _safe_float(summary.get("rmse_px", 1e9), 1e9)
    first = summary.get("first_lock_frame", None)
    loss_raw = summary.get("loss_count", None)
    losses = 99 if loss_raw is None else int(loss_raw)
    acq = int(summary.get("acquisition_count", 0) or 0)
    valid = _safe_float(summary.get("valid_detection_pct", 0.0))
    b = BENCHMARKS.get(bkey, {}) if bkey else {}
    r_lock = b.get("lock", 50.0)
    r_rmse = b.get("rmse", 10.0)
    r_first = b.get("first", 500)
    r_loss = b.get("losses", 3)
    first_ok = (first is not None and first <= r_first)
    if lock >= r_lock and rmse < r_rmse and first_ok and losses <= r_loss:
        return "STRICT-PASS", f"beat bench [{bench_str(bkey)}]"
    if intermittent_allowed and acq >= int(b.get("acq", 2)) and valid >= float(b.get("valid", 15.0)):
        return "INTERMITTENT-PASS", (f"intermittent rule acq={acq} valid={valid:.1f}% "
                                     f"(bench [{bench_str(bkey)}])")
    reasons = []
    if lock < r_lock:
        reasons.append(f"lock {lock:.1f}%<{r_lock}")
    if rmse >= r_rmse:
        reasons.append(f"rmse {rmse:.1f}>={r_rmse}")
    if not first_ok:
        reasons.append(f"first_lock {first}>{r_first}")
    if losses > r_loss:
        reasons.append(f"losses {losses}>{r_loss}")
    return "FAIL", ("; ".join(reasons) if reasons else "no gate met") + f" (bench [{bench_str(bkey)}])"


# ---------------------------------------------------------------------------
# Core tracking runner.
# ---------------------------------------------------------------------------

def run_tracking_case(case_id, name, desc, cfg, frames, seed,
                      intermittent, cue=False, bkey=None, timeout_s=None):
    from pat_pipeline.factory import make_pipeline
    from fsoc_tracker.input.synthetic_source import SyntheticSource
    from fsoc_tracker.evaluation.metrics import MetricsCollector
    t_all = time.perf_counter()
    bk = bkey or case_id.split("-s")[0].split("@")[0]
    try:
        source = SyntheticSource(cfg, seed=seed)
        pipe = make_pipeline(cfg)
        metrics = MetricsCollector()
        metrics.start_run()
        fps_cfg = max(float(cfg["camera"].get("fps", 30.0)), 1)
        metrics.input_fps = fps_cfg
        upd = max(float(cfg["camera"].get("update_interval_hz", fps_cfg)), 1)
        dt_ctrl = 1.0 / upd
        pipe.reset()
        if cue and hasattr(source, "cue_camera_to_target"):
            source.cue_camera_to_target()
        timed_out = False
        for _ in range(frames):
            if timeout_s and (time.perf_counter() - t_all) > timeout_s:
                timed_out = True
                break
            frame, gt = source.read()
            iv = _compute_in_fov(source, gt)
            try:
                lim = bool(source.camera.is_at_limit(
                    getattr(pipe.controller, "prev_pan_rate", 0.0),
                    getattr(pipe.controller, "prev_tilt_rate", 0.0)))
            except Exception:
                lim = False
            try:
                ego = (float(getattr(pipe.controller, "prev_pan_rate", 0.0)),
                       float(getattr(pipe.controller, "prev_tilt_rate", 0.0)))
            except Exception:
                ego = (0.0, 0.0)
            t0 = time.perf_counter()
            detection, estimate, cmd = pipe.step_frame(frame, dt=dt_ctrl, in_fov=iv,
                                                       at_limit=lim, ego_rate=ego)
            proc_ms = (time.perf_counter() - t0) * 1000.0
            try:
                source.apply_camera_command(cmd.pan_rate, cmd.tilt_rate, dt_ctrl)
            except Exception:
                pass
            metrics.update(frame.frame_id, frame.timestamp, detection.valid, estimate, gt,
                           proc_ms, fps_cfg, cmd.pan_rate, cmd.tilt_rate,
                           detection_confidence=detection.confidence,
                           saturated=getattr(cmd, "saturated", False), input_fps=fps_cfg,
                           detection_centroid=(detection.centroid_px
                                               if detection.valid else None),
                           search_case=getattr(cmd, "search_case", ""))
        summary = metrics.summary()
        if timed_out:
            return _sanitize_result({
                "case": case_id, "name": name, "desc": desc, "seed": seed,
                "frames": frames, "verdict": "ERROR",
                "reason": f"timeout after {timeout_s}s",
                "benchmark": bench_str(bk), "bkey": bk,
                "lock_pct": round(_safe_float(summary.get("lock_retention_pct", 0)), 1),
                "rmse": round(_safe_float(summary.get("rmse_px", 0)), 2),
                "p95": round(_safe_float(summary.get("p95_error_px", 0)), 2),
                "first_lock": summary.get("first_lock_frame"),
                "valid_pct": round(_safe_float(summary.get("valid_detection_pct", 0)), 1),
                "losses": int(summary.get("loss_count", 0) or 0),
                "acq": int(summary.get("acquisition_count", 0) or 0),
                "avg_ms": round(_safe_float(summary.get("avg_processing_ms", 0)), 2),
                "max_ms": round(_safe_float(summary.get("max_processing_ms", 0)), 2),
                "error": None,
                "wall_s": round(time.perf_counter() - t_all, 2),
                "tags": [], "severity": "",
            })
        v, reason = verdict(summary, intermittent, bk)
        hard = ""
        try:
            fog = (cfg.get("atmosphere", {}).get("strength", 0)
                   if cfg.get("atmosphere", {}).get("type") == "fog" else 0)
            jit = float(cfg.get("camera", {}).get("jitter_px", 0))
            if float(fog) >= 0.5 or jit >= 12:
                hard = "EXPECTED-HARD"
        except Exception:
            pass
        return _sanitize_result({
            "case": case_id, "name": name, "desc": desc, "seed": seed,
            "frames": frames, "verdict": v,
            "reason": reason + (" | " + hard if hard else ""),
            "benchmark": bench_str(bk), "bkey": bk,
            "lock_pct": round(_safe_float(summary.get("lock_retention_pct", 0)), 1),
            "rmse": round(_safe_float(summary.get("rmse_px", 0)), 2),
            "p95": round(_safe_float(summary.get("p95_error_px", 0)), 2),
            "first_lock": summary.get("first_lock_frame"),
            "valid_pct": round(_safe_float(summary.get("valid_detection_pct", 0)), 1),
            "losses": int(summary.get("loss_count", 0) or 0),
            "acq": int(summary.get("acquisition_count", 0) or 0),
            "avg_ms": round(_safe_float(summary.get("avg_processing_ms", 0)), 2),
            "max_ms": round(_safe_float(summary.get("max_processing_ms", 0)), 2),
            "error": None,
            "wall_s": round(time.perf_counter() - t_all, 2),
            "tags": [], "severity": "",
        })
    except Exception as ex:
        return _sanitize_result({
            "case": case_id, "name": name, "desc": desc, "seed": seed,
            "frames": frames, "verdict": "ERROR",
            "reason": f"{type(ex).__name__}: {ex}",
            "benchmark": bench_str(bk), "bkey": bk,
            "lock_pct": 0, "rmse": 0, "p95": 0, "first_lock": None,
            "valid_pct": 0, "losses": 0, "acq": 0, "avg_ms": 0, "max_ms": 0,
            "error": traceback.format_exc(limit=3),
            "wall_s": round(time.perf_counter() - t_all, 2),
            "tags": [], "severity": "",
        })


def _empty_result(rkey, seed, verdict="ERROR", reason="", frames=0):
    return _sanitize_result({
        "case": rkey, "name": rkey, "desc": "",
        "seed": seed, "frames": frames, "verdict": verdict,
        "reason": reason, "benchmark": bench_str(rkey), "bkey": rkey,
        "lock_pct": 0, "rmse": 0, "p95": 0, "first_lock": None,
        "valid_pct": 0, "losses": 0, "acq": 0, "avg_ms": 0, "max_ms": 0,
        "error": None, "tags": [], "severity": "",
    })


# ---------------------------------------------------------------------------
# Robustness runners (R1..R12).
# ---------------------------------------------------------------------------

def run_robustness(rkey, seed):
    if rkey == "R3":
        try:
            from pat_common.config.loader import load_config
            from pat_pipeline.factory import make_pipeline
            cfg = load_config()
            pipe = make_pipeline(cfg)
            d1 = pipe.detector.detect(None)
            d2 = pipe.detector.detect(np.zeros((0, 0), dtype=np.uint8))
            blank = np.zeros((480, 640), dtype=np.uint8)
            det, _est, _cmd = pipe.step_frame(blank)
            ok = (not d1.valid) and (not d2.valid) and (det is not None)
            return _empty_result("R3", seed,
                                 "STRICT-PASS" if ok else "FAIL",
                                 "None/empty guarded" if ok else "guard failed")
        except Exception as ex:
            r = _empty_result("R3", seed, "ERROR", str(ex))
            r["error"] = traceback.format_exc(limit=3)
            return r

    if rkey == "R4":
        try:
            from pat_common.config.loader import load_config
            from pat_pipeline.factory import make_camera
            cfg = load_config()
            cam = make_camera(cfg)
            cam.pan = -20.0
            cam.tilt = 20.0
            if hasattr(cam, "_update_center"):
                cam._update_center()
            at = cam.is_at_limit(-5.0, 5.0)
            return _empty_result("R4", seed,
                                 "STRICT-PASS" if at else "FAIL",
                                 f"is_at_limit={at}")
        except Exception as ex:
            r = _empty_result("R4", seed, "ERROR", str(ex))
            r["error"] = traceback.format_exc(limit=3)
            return r

    if rkey == "R1":
        try:
            from pat_pipeline.factory import make_pipeline
            from fsoc_tracker.input.synthetic_source import SyntheticSource
            from fsoc_tracker.evaluation.metrics import MetricsCollector
            xd = next(d for d in X_DEFS if d["key"] == "X7")
            cfg = build_case_config(xd, seed)
            cfg["atmosphere"] = {"type": "clear", "strength": 0.0}
            source = SyntheticSource(cfg, seed=seed)
            pipe = make_pipeline(cfg)
            metrics = MetricsCollector()
            metrics.start_run()
            fps_cfg = max(float(cfg["camera"].get("fps", 30.0)), 1)
            metrics.input_fps = fps_cfg
            dt_ctrl = 1.0 / max(float(cfg["camera"].get("update_interval_hz", fps_cfg)), 1)
            pipe.reset()
            for i in range(400):
                if i == 200:
                    cfg = deep_merge(cfg, {"atmosphere": {"type": "fog", "strength": 0.5}})
                    try:
                        source.update_config(cfg)
                    except Exception:
                        source.cfg = cfg
                    try:
                        pipe.update_config(cfg)
                    except Exception:
                        pass
                frame, gt = source.read()
                iv = _compute_in_fov(source, gt)
                t0 = time.perf_counter()
                detection, estimate, cmd = pipe.step_frame(frame, dt=dt_ctrl, in_fov=iv)
                proc_ms = (time.perf_counter() - t0) * 1000.0
                try:
                    source.apply_camera_command(cmd.pan_rate, cmd.tilt_rate, dt_ctrl)
                except Exception:
                    pass
                metrics.update(frame.frame_id, frame.timestamp, detection.valid, estimate, gt,
                               proc_ms, fps_cfg, cmd.pan_rate, cmd.tilt_rate,
                               detection_confidence=detection.confidence,
                               saturated=getattr(cmd, "saturated", False), input_fps=fps_cfg,
                               detection_centroid=(detection.centroid_px
                                                   if detection.valid else None),
                               search_case=getattr(cmd, "search_case", ""))
            summary = metrics.summary()
            r = _empty_result("R1", seed, "STRICT-PASS",
                              f"mid-run fog 0->0.5 at f200 completed "
                              f"lock={_safe_float(summary.get('lock_retention_pct', 0)):.1f}%",
                              frames=400)
            r["lock_pct"] = round(_safe_float(summary.get("lock_retention_pct", 0)), 1)
            r["rmse"] = round(_safe_float(summary.get("rmse_px", 0)), 2)
            r["p95"] = round(_safe_float(summary.get("p95_error_px", 0)), 2)
            r["first_lock"] = summary.get("first_lock_frame")
            r["valid_pct"] = round(_safe_float(summary.get("valid_detection_pct", 0)), 1)
            r["losses"] = int(summary.get("loss_count", 0) or 0)
            r["acq"] = int(summary.get("acquisition_count", 0) or 0)
            r["avg_ms"] = round(_safe_float(summary.get("avg_processing_ms", 0)), 2)
            r["max_ms"] = round(_safe_float(summary.get("max_processing_ms", 0)), 2)
            return r
        except Exception as ex:
            r = _empty_result("R1", seed, "ERROR", str(ex), frames=400)
            r["error"] = traceback.format_exc(limit=3)
            return r

    if rkey == "R2":
        xd = next(d for d in X_DEFS if d["key"] == "X1")
        cfg = build_case_config(xd, seed)
        r1 = run_tracking_case("R2a", "R2-reset-repro", R_DEFS[1]["desc"], cfg, 200, seed, False, bkey="R2")
        r2 = run_tracking_case("R2b", "R2-reset-repro", R_DEFS[1]["desc"], cfg, 200, seed, False, bkey="R2")
        same = ((r1["lock_pct"], r1["rmse"], r1["first_lock"], r1["acq"])
                == (r2["lock_pct"], r2["rmse"], r2["first_lock"], r2["acq"]))
        r1.update({"case": "R2",
                   "verdict": "STRICT-PASS" if same else "FAIL",
                   "benchmark": bench_str("R2"), "bkey": "R2",
                   "reason": f"repro hash identical={same}"})
        return r1

    if rkey == "R5":
        xd = next(d for d in X_DEFS if d["key"] == "X1")
        cfg = build_case_config(xd, seed)
        res = run_tracking_case("R5", "R5-latency-budget", R_DEFS[4]["desc"],
                                cfg, 200, seed, False, bkey="R5")
        ok = res["avg_ms"] < 33.0 and res["verdict"] != "ERROR"
        res["verdict"] = ("STRICT-PASS" if ok
                          else ("FAIL" if res["verdict"] != "ERROR" else "ERROR"))
        res["reason"] = (res["reason"] + f" | avg {res['avg_ms']}ms"
                         if res.get("reason") else f"avg {res['avg_ms']}ms")
        res["benchmark"] = bench_str("R5")
        res["bkey"] = "R5"
        return res

    if rkey == "R6":
        xd = next(d for d in X_DEFS if d["key"] == "X1")
        cfg = build_case_config(xd, seed)
        return run_tracking_case("R6", "R6-long-soak", R_DEFS[5]["desc"],
                                 cfg, 1200, seed, False, bkey="R6")

    if rkey == "R7":
        try:
            xd = next(d for d in X_DEFS if d["key"] == "X2")
            c1 = build_case_config(xd, 42)
            c2 = build_case_config(xd, 7)
            diff = ((c1.get("noise", {}).get("gaussian_std"),
                     c1.get("target", {}).get("speed_px_per_frame"))
                    != (c2.get("noise", {}).get("gaussian_std"),
                        c2.get("target", {}).get("speed_px_per_frame")))
            return _empty_result("R7", seed,
                                 "STRICT-PASS" if diff else "FAIL",
                                 f"seeds differ={diff}")
        except Exception as ex:
            r = _empty_result("R7", seed, "ERROR", str(ex))
            r["error"] = traceback.format_exc(limit=3)
            return r

    if rkey == "R8":
        try:
            from pat_pipeline.factory import make_pipeline
            from fsoc_tracker.input.synthetic_source import SyntheticSource
            ed = next(d for d in E_DEFS if d["key"] == "E13")
            cfg = build_edge_config(ed, seed)
            source = SyntheticSource(cfg, seed=seed)
            pipe = make_pipeline(cfg)
            pipe.reset()
            maxp = float(cfg["camera"]["max_pan_speed"])
            maxt = float(cfg["camera"]["max_tilt_speed"])
            worst_p, worst_t = 0.0, 0.0
            for _ in range(200):
                frame, _gt = source.read()
                _d, _e, cmd = pipe.step_frame(frame)
                worst_p = max(worst_p, abs(_safe_float(cmd.pan_rate)))
                worst_t = max(worst_t, abs(_safe_float(cmd.tilt_rate)))
                source.apply_camera_command(cmd.pan_rate, cmd.tilt_rate, 1.0 / 30.0)
            ok = worst_p <= maxp + 1e-6 and worst_t <= maxt + 1e-6
            r = _empty_result("R8", seed, "STRICT-PASS" if ok else "FAIL",
                              f"max|pan|={worst_p:.2f}<={maxp} max|tilt|={worst_t:.2f}<={maxt}",
                              frames=200)
            return r
        except Exception as ex:
            r = _empty_result("R8", seed, "ERROR", str(ex), frames=200)
            r["error"] = traceback.format_exc(limit=3)
            return r

    if rkey == "R9":
        try:
            from pat_common.config.loader import load_config
            cfg = load_config()  # defaults should validate
            ok = cfg is not None and "camera" in cfg and "target" in cfg
            return _empty_result("R9", seed,
                                 "STRICT-PASS" if ok else "FAIL",
                                 "defaults validate" if ok else "config missing keys")
        except Exception as ex:
            r = _empty_result("R9", seed, "ERROR", str(ex))
            r["error"] = traceback.format_exc(limit=3)
            return r

    if rkey == "R10":
        try:
            from fsoc_tracker.input.synthetic_source import SyntheticSource
            xd = next(d for d in X_DEFS if d["key"] == "X1")
            cfg = build_case_config(xd, seed)
            h = hashlib.sha256()
            for _ in range(2):
                src = SyntheticSource(cfg, seed=seed)
                for _ in range(50):
                    frame, _gt = src.read()
                    data = getattr(frame, "data", None)
                    if data is None:
                        data = getattr(frame, "image", None)
                    if data is not None:
                        try:
                            h.update(np.asarray(data).tobytes())
                        except Exception:
                            pass
                    h.update(str(getattr(frame, "frame_id", 0)).encode())
            digest = h.hexdigest()
            return _empty_result("R10", seed, "STRICT-PASS" if digest else "FAIL",
                                 f"source digest={digest[:16]}", frames=100)
        except Exception as ex:
            r = _empty_result("R10", seed, "ERROR", str(ex), frames=100)
            r["error"] = traceback.format_exc(limit=3)
            return r

    if rkey == "R11":
        try:
            from pat_pipeline.factory import make_pipeline
            pipe = make_pipeline(copy.deepcopy(DEFAULT_CONFIG))
            pipe.reset()
            ok = True
            for bad in (np.full((480, 640), np.nan, dtype=np.float32),
                        np.full((480, 640), np.inf, dtype=np.float32),
                        np.zeros((0, 0), dtype=np.uint8)):
                try:
                    d, _e, _c = pipe.step_frame(bad)
                    if d is None:
                        ok = False
                except Exception:
                    # explicit exception is acceptable as long as it's controlled
                    pass
            return _empty_result("R11", seed,
                                 "STRICT-PASS" if ok else "FAIL",
                                 "NaN/Inf frames handled" if ok else "None detection returned",
                                 frames=3)
        except Exception as ex:
            r = _empty_result("R11", seed, "ERROR", str(ex), frames=3)
            r["error"] = traceback.format_exc(limit=3)
            return r

    if rkey == "R12":
        try:
            from pat_pipeline.factory import make_pipeline
            from fsoc_tracker.input.synthetic_source import SyntheticSource
            xd = next(d for d in X_DEFS if d["key"] == "X1")
            cfg = build_case_config(xd, seed)
            src = SyntheticSource(cfg, seed=seed)
            pipe = make_pipeline(cfg)
            pipe.reset()
            # Warm up
            for _ in range(30):
                frame, _ = src.read()
                pipe.step_frame(frame)
            # reset and run 30 more
            pipe.reset()
            first_after_reset = []
            for _ in range(30):
                frame, _ = src.read()
                d, _e, _c = pipe.step_frame(frame)
                first_after_reset.append(bool(getattr(d, "valid", False)))
            # reset again, run again — result should be identical
            pipe.reset()
            second_after_reset = []
            for _ in range(30):
                frame, _ = src.read()
                d, _e, _c = pipe.step_frame(frame)
                second_after_reset.append(bool(getattr(d, "valid", False)))
            ok = first_after_reset == second_after_reset
            return _empty_result("R12", seed,
                                 "STRICT-PASS" if ok else "FAIL",
                                 f"reset-isolated={ok}", frames=60)
        except Exception as ex:
            r = _empty_result("R12", seed, "ERROR", str(ex), frames=60)
            r["error"] = traceback.format_exc(limit=3)
            return r

    return _empty_result(rkey, seed, "ERROR", "unknown robustness key")


# ---------------------------------------------------------------------------
# Suite construction.
# ---------------------------------------------------------------------------

def _def_tags(defn):
    return set(defn.get("tags", []))


def _def_severity(defn):
    return defn.get("severity", "HARD")


def _filter_defs(defs, tags=None, severities=None):
    if not tags and not severities:
        return defs
    out = []
    tagset = set(tags) if tags else None
    sevset = set(severities) if severities else None
    for d in defs:
        if tagset and not (tagset & _def_tags(d)):
            continue
        if sevset and _def_severity(d) not in sevset:
            continue
        out.append(d)
    return out


def build_suite(seed_default=42, fuzz_n=0, scenario=None, frames_override=None,
                tags=None, severities=None):
    specs = []
    if scenario:
        for xd in X_DEFS:
            if xd["name"] == scenario or xd["key"] == scenario:
                specs.append({"kind": "X", "xkey": xd["key"], "seed": seed_default,
                              "frames": frames_override})
                return specs
        for ed in E_DEFS:
            if ed["name"] == scenario or ed["key"] == scenario:
                specs.append({"kind": "E", "xkey": ed["key"], "seed": seed_default,
                              "frames": frames_override})
                return specs
        for rd in R_DEFS:
            if rd["name"] == scenario or rd["key"] == scenario:
                specs.append({"kind": "R", "xkey": rd["key"], "seed": seed_default,
                              "frames": 0})
                return specs
        raise SystemExit(f"unknown scenario {scenario}; use --list")

    if fuzz_n and fuzz_n > 0:
        rng = np.random.default_rng(seed_default)
        pool = _filter_defs(X_DEFS, tags, severities)
        if not pool:
            raise SystemExit("no X families match the tag/severity filter")
        keys = [d["key"] for d in pool]
        for _ in range(fuzz_n):
            k = keys[int(rng.integers(0, len(keys)))]
            s = int(rng.integers(1, 100000))
            specs.append({"kind": "X", "xkey": k, "seed": s, "frames": frames_override})
        return specs

    xdefs = _filter_defs(X_DEFS, tags, severities)
    edefs = _filter_defs(E_DEFS, tags, severities)
    rdefs = _filter_defs(R_DEFS, tags, severities)
    for xd in xdefs:
        for s in FULL_SEEDS:
            specs.append({"kind": "X", "xkey": xd["key"], "seed": s,
                          "frames": frames_override})
    for ed in edefs:
        specs.append({"kind": "E", "xkey": ed["key"], "seed": seed_default,
                      "frames": frames_override})
    for rd in rdefs:
        specs.append({"kind": "R", "xkey": rd["key"], "seed": seed_default, "frames": 0})
    return specs


def _decorate_result(r, defn):
    r["tags"] = list(defn.get("tags", []))
    r["severity"] = defn.get("severity", "HARD")
    return r


def _resolve_frames(spec_frames, default_frames):
    """Explicit None means 'use default'; explicit 0 (or other int) is respected."""
    return default_frames if spec_frames is None else spec_frames


def _worker(spec):
    _apply_spec_winner(spec)
    kind = spec["kind"]
    cue = spec.get("cue", False)
    timeout_s = spec.get("timeout_s", None)
    if kind == "X":
        xd = next(d for d in X_DEFS if d["key"] == spec["xkey"])
        cfg = build_case_config(xd, spec["seed"])
        frames = _resolve_frames(spec.get("frames"), xd["frames"])
        r = run_tracking_case(f'{xd["key"]}-s{spec["seed"]}',
                              f'{xd["name"]}@s{spec["seed"]}',
                              xd["desc"], cfg, frames, spec["seed"],
                              xd["intermittent"], cue=cue, bkey=xd["key"],
                              timeout_s=timeout_s)
        return _decorate_result(r, xd)
    if kind == "E":
        ed = next(d for d in E_DEFS if d["key"] == spec["xkey"])
        cfg = build_edge_config(ed, spec["seed"])
        frames = _resolve_frames(spec.get("frames"), ed["frames"])
        r = run_tracking_case(ed["key"], ed["name"], ed["desc"], cfg, frames,
                              spec["seed"], ed["intermittent"], cue=cue,
                              bkey=ed["key"], timeout_s=timeout_s)
        return _decorate_result(r, ed)
    rd = next(d for d in R_DEFS if d["key"] == spec["xkey"])
    r = run_robustness(spec["xkey"], spec["seed"])
    return _decorate_result(r, rd)


# ---------------------------------------------------------------------------
# Reporting.
# ---------------------------------------------------------------------------

def _family_of(case):
    base = case.split("-s")[0].split("@")[0]
    i = 0
    while i < len(base) and base[i].isalpha():
        i += 1
    return base[:i] + base[i:].split("-")[0]


def summarize_families(results):
    fam = {}
    for r in results:
        key = _family_of(r["case"])
        d = fam.setdefault(key, {"total": 0, "strict": 0, "intermittent": 0,
                                 "fail": 0, "error": 0, "locks": [], "rmses": []})
        d["total"] += 1
        v = r["verdict"]
        if v == "STRICT-PASS":
            d["strict"] += 1
        elif v == "INTERMITTENT-PASS":
            d["intermittent"] += 1
        elif v == "FAIL":
            d["fail"] += 1
        else:
            d["error"] += 1
        if r.get("frames"):
            d["locks"].append(_safe_float(r.get("lock_pct", 0)))
            d["rmses"].append(_safe_float(r.get("rmse", 0)))
    return fam


def print_table(results):
    hdr = (f'{"CASE":<12}{"SEED":<7}{"FR":<5}{"LOCK%":<7}{"RMSE":<7}{"P95":<7}'
           f'{"1ST":<6}{"VALID%":<7}{"LOSS":<5}{"ACQ":<4}{"AVGms":<7}'
           f'{"VERDICT":<17}BENCH')
    print(hdr)
    print("-" * len(hdr))
    for r in results:
        bench = str(r.get("benchmark", ""))[:60]
        print(f'{r["case"]:<12}{r["seed"]:<7}{r["frames"]:<5}{r["lock_pct"]:<7}'
              f'{r["rmse"]:<7}{r["p95"]:<7}{str(r["first_lock"]):<6}'
              f'{r["valid_pct"]:<7}{r["losses"]:<5}{r["acq"]:<4}{r["avg_ms"]:<7}'
              f'{r["verdict"]:<17}{bench} :: {r["reason"]}'[:220])


def print_family_summary(results):
    fam = summarize_families(results)
    if not fam:
        return
    print()
    print("=== Family aggregate ===")
    print(f'{"FAM":<6}{"TOTAL":<7}{"STRICT":<8}{"INT":<6}{"FAIL":<6}{"ERR":<6}'
          f'{"MEAN_LOCK":<11}{"WORST_RMSE":<12}TAGS')
    print("-" * 100)
    for key in sorted(fam.keys(), key=lambda s: (s[0], int("".join(c for c in s if c.isdigit()) or 0))):
        d = fam[key]
        ml = float(np.mean(d["locks"])) if d["locks"] else 0.0
        wr = max(d["rmses"]) if d["rmses"] else 0.0
        tags = set()
        for r in results:
            if _family_of(r["case"]) == key:
                tags |= set(r.get("tags", []))
        print(f'{key:<6}{d["total"]:<7}{d["strict"]:<8}{d["intermittent"]:<6}'
              f'{d["fail"]:<6}{d["error"]:<6}{ml:<11.1f}{wr:<12.2f}{_tags_str(sorted(tags))}')


# ---------------------------------------------------------------------------
# Main.
# ---------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(description="Headless single-suite PAT challenger")
    ap.add_argument("--extreme", action="store_true", help="full 80-case suite")
    ap.add_argument("--gauntlet", action="store_true", help="alias for --extreme")
    ap.add_argument("--full", action="store_true", help="alias for --extreme")
    ap.add_argument("--scenario", default=None, help="single X/E/R key or name")
    ap.add_argument("--config", default=None,
                    help="winner JSON: detector/tracker/controller (+camera start/update_interval_hz) overrides applied to every case")
    ap.add_argument("--fuzz", type=int, default=0, help="N random X-family draws")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--frames", type=int, default=None,
                    help="override frames for all tracking cases")
    ap.add_argument("--cue", action="store_true", help="assisted start (default uncued)")
    ap.add_argument("--workers", type=int, default=1)
    ap.add_argument("--json", default=None)
    ap.add_argument("--md", default=None)
    ap.add_argument("--fail-fast", action="store_true")
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--tag", default=None,
                    help="comma-separated tags to include (e.g. noise,motion)")
    ap.add_argument("--severity", default=None,
                    help="comma-separated severities to include (CORE,HARD,EXTREME,EXPECTED-HARD)")
    ap.add_argument("--timeout", type=float, default=300.0,
                    help="per tracking-case timeout in seconds")
    ap.add_argument("--retries", type=int, default=0,
                    help="retries for ERROR cases (sequential only)")
    ap.add_argument("--keep", type=int, default=20,
                    help="keep newest N auto-logged runs in runs/")
    ap.add_argument("--no-color", action="store_true", help="disable ANSI colors")
    ap.add_argument("--color", choices=["auto", "always", "never"], default="auto")
    ap.add_argument("--no-html", action="store_true", help="skip HTML report")
    ap.add_argument("--no-diff", action="store_true", help="skip regression diff")
    args = ap.parse_args()
    R.set_color_mode("never" if args.no_color else args.color)
    try:
        set_winner_overrides(args.config)
    except FileNotFoundError:
        print(f"error: --config file not found: {args.config}")
        return 2
    except json.JSONDecodeError:
        print(f"error: --config file is not valid JSON: {args.config}")
        return 2

    tags = [t.strip() for t in args.tag.split(",")] if args.tag else None
    severities = [s.strip() for s in args.severity.split(",")] if args.severity else None

    if args.list:
        def _show(defs, header):
            print(header)
            for d in defs:
                stars = d.get("star", ("-", "-"))
                corner = FAR_CORNERS[d.get("corner", 0)] if "corner" in d else "-"
                print(f'  {d["key"]:<4} {d["name"]:<28} '
                      f'{d.get("frames", 0)}f star={stars} corner={corner}')
                print(f'      SEV={d.get("severity","?"):<14} TAGS={_tags_str(d.get("tags", []))}')
                print(f'      BENCH: {bench_str(d["key"])}')
                print(f'      {d.get("desc", "")}')
        _show(_filter_defs(X_DEFS, tags, severities), "X families (benchmark to beat):")
        _show(_filter_defs(E_DEFS, tags, severities), "Edges (benchmark to beat):")
        _show(_filter_defs(R_DEFS, tags, severities), "Robustness:")
        return 0

    if args.scenario:
        specs = build_suite(args.seed, 0, args.scenario, args.frames, tags, severities)
    elif args.fuzz:
        specs = build_suite(args.seed, args.fuzz, None, args.frames, tags, severities)
    else:
        # --extreme / --gauntlet / --full / default: full suite
        specs = build_suite(args.seed, 0, None, args.frames, tags, severities)

    for s in specs:
        s["cue"] = args.cue
        s["timeout_s"] = args.timeout if s["kind"] in ("X", "E") else None
        if WINNER_OVERRIDES:
            s["winner"] = copy.deepcopy(WINNER_OVERRIDES)

    if not specs:
        print("No cases matched the filter.")
        return 0

    print(f"Suite: {len(specs)} cases | tags={tags or 'ALL'} | severity={severities or 'ALL'}")

    results = []
    t0 = time.perf_counter()
    per_case_times = []
    if args.workers and args.workers > 1:
        with concurrent.futures.ProcessPoolExecutor(max_workers=args.workers) as ex:
            for i, r in enumerate(ex.map(_worker, specs), 1):
                results.append(r)
                per_case_times.append(time.perf_counter() - t0)
                eta = ((sum(per_case_times) / len(per_case_times)) * (len(specs) - i)
                       if per_case_times else 0)
                print(f'[{i}/{len(specs)}] [{r["case"]}] {r["verdict"]} '
                      f'(bench: {r.get("benchmark", "")}) lock={r["lock_pct"]}% '
                      f'rmse={r["rmse"]} 1st={r["first_lock"]} ETA~{eta:.0f}s :: {r["reason"]}')
                if args.fail_fast and r["verdict"] in ("FAIL", "ERROR"):
                    break
    else:
        for i, s in enumerate(specs, 1):
            if s["kind"] == "R":
                rd = next(d for d in R_DEFS if d["key"] == s["xkey"])
                r = _decorate_result(run_robustness(s["xkey"], s["seed"]), rd)
            elif s["kind"] == "X":
                xd = next(d for d in X_DEFS if d["key"] == s["xkey"])
                cfg = build_case_config(xd, s["seed"])
                frames = _resolve_frames(s.get("frames"), xd["frames"])
                r = run_tracking_case(f'{xd["key"]}-s{s["seed"]}',
                                      f'{xd["name"]}@s{s["seed"]}',
                                      xd["desc"], cfg, frames, s["seed"],
                                      xd["intermittent"], cue=args.cue,
                                      bkey=xd["key"], timeout_s=args.timeout)
                r = _decorate_result(r, xd)
            else:
                ed = next(d for d in E_DEFS if d["key"] == s["xkey"])
                cfg = build_edge_config(ed, s["seed"])
                frames = _resolve_frames(s.get("frames"), ed["frames"])
                r = run_tracking_case(ed["key"], ed["name"], ed["desc"], cfg, frames,
                                      s["seed"], ed["intermittent"], cue=args.cue,
                                      bkey=ed["key"], timeout_s=args.timeout)
                r = _decorate_result(r, ed)
            # retry once on ERROR (sequential only)
            if r["verdict"] == "ERROR" and args.retries > 0:
                for attempt in range(args.retries):
                    print(f'  retry {attempt + 1}/{args.retries} on {r["case"]}')
                    if s["kind"] == "X":
                        xd = next(d for d in X_DEFS if d["key"] == s["xkey"])
                        cfg = build_case_config(xd, s["seed"])
                        frames = _resolve_frames(s.get("frames"), xd["frames"])
                        r = _decorate_result(
                            run_tracking_case(f'{xd["key"]}-s{s["seed"]}',
                                              f'{xd["name"]}@s{s["seed"]}',
                                              xd["desc"], cfg, frames, s["seed"],
                                              xd["intermittent"], cue=args.cue,
                                              bkey=xd["key"], timeout_s=args.timeout),
                            xd)
                    elif s["kind"] == "E":
                        ed = next(d for d in E_DEFS if d["key"] == s["xkey"])
                        cfg = build_edge_config(ed, s["seed"])
                        frames = _resolve_frames(s.get("frames"), ed["frames"])
                        r = _decorate_result(
                            run_tracking_case(ed["key"], ed["name"], ed["desc"],
                                              cfg, frames, s["seed"], ed["intermittent"],
                                              cue=args.cue, bkey=ed["key"],
                                              timeout_s=args.timeout),
                            ed)
                    else:
                        rd = next(d for d in R_DEFS if d["key"] == s["xkey"])
                        r = _decorate_result(run_robustness(s["xkey"], s["seed"]), rd)
                    if r["verdict"] != "ERROR":
                        break
            results.append(r)
            eta = ((time.perf_counter() - t0) / i) * (len(specs) - i) if i else 0
            print(f'[{i}/{len(specs)}] [{r["case"]}] {r["verdict"]} '
                  f'(bench: {r.get("benchmark", "")}) lock={r["lock_pct"]}% '
                  f'rmse={r["rmse"]} 1st={r["first_lock"]} ETA~{eta:.0f}s :: {r["reason"]}')
            if args.fail_fast and r["verdict"] in ("FAIL", "ERROR"):
                break

    dt = time.perf_counter() - t0
    family = summarize_families(results)
    sp = sum(1 for r in results if r["verdict"] == "STRICT-PASS")
    ip = sum(1 for r in results if r["verdict"] == "INTERMITTENT-PASS")
    fl = sum(1 for r in results if r["verdict"] == "FAIL")
    er = sum(1 for r in results if r["verdict"] == "ERROR")
    passed = [r["case"] for r in results if r["verdict"] in ("STRICT-PASS", "INTERMITTENT-PASS")]
    failed = [r["case"] for r in results if r["verdict"] in ("FAIL", "ERROR")]
    final = ("FINAL VERDICT: PASS - all benchmarks beaten" if (fl == 0 and er == 0)
             else f"FINAL VERDICT: FAIL - {fl + er} case(s) below benchmark")

    os.makedirs("runs", exist_ok=True)
    stamp = time.strftime("%Y%m%d_%H%M%S")
    auto_json = os.path.join("runs", f"headless_{stamp}.json")
    auto_md   = os.path.join("runs", f"headless_{stamp}.md")

    prev_payload, prev_path = (None, None)
    if not args.no_diff:
        prev_payload, prev_path = R.load_previous_run("runs")

    payload = {
        "results": results,
        "family": family,
        "summary": {"strict": sp, "intermittent": ip, "fail": fl, "error": er,
                    "passed": passed, "failed": failed, "final": final,
                    "wall_s": round(dt, 1), "stamp": stamp,
                    "tags_filter": tags, "severity_filter": severities},
    }
    tmp = auto_json + ".tmp"
    try:
        with open(tmp, "w") as f:
            json.dump(payload, f, indent=2, allow_nan=False)
        os.replace(tmp, auto_json)
    except Exception as ex:
        print(R.c(f"warning: failed to write {auto_json}: {ex}", R.C.B_YELLOW))
        try:
            os.remove(tmp)
        except OSError:
            pass

    # --- enriched report ---
    R.report(results, family, payload["summary"], prev_payload, runs_dir="runs",
             write_html=not args.no_html)
    if prev_path:
        print(R.c(f"Diffed against -> {prev_path}", R.C.DIM))

    print()
    print(R.c("=== Raw results ===", R.C.BOLD, R.C.B_CYAN))
    print_table(results)
    print_family_summary(results)
    print(f'\nSuite: {len(results)} cases in {dt:.1f}s | '
          f'STRICT {sp} INTERMITTENT {ip} FAIL {fl} ERROR {er}')
    print(R.c(final, R.C.B_GREEN if (fl == 0 and er == 0) else R.C.B_RED, R.C.BOLD))

    with open(auto_md, "w") as f:
        f.write("# Headless PAT results\n\n")
        f.write(f"{final}\n\nPASSED: {', '.join(passed) if passed else '-'}\n\n"
                f"FAILED: {', '.join(failed) if failed else '-'}\n\n")
        f.write("| case | seed | fr | lock% | rmse | p95 | 1st | valid% | "
                "loss | acq | avgms | sev | tags | benchmark | verdict | reason |\n")
        f.write("|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|\n")
        for r in results:
            f.write(f'| {r["case"]} | {r["seed"]} | {r["frames"]} | {r["lock_pct"]} | '
                    f'{r["rmse"]} | {r["p95"]} | {r["first_lock"]} | {r["valid_pct"]} | '
                    f'{r["losses"]} | {r["acq"]} | {r["avg_ms"]} | {r.get("severity", "")} | '
                    f'{",".join(r.get("tags", []))} | {r.get("benchmark", "")} | '
                    f'{r["verdict"]} | {r["reason"]} |\n')
    print(f"Logged run -> {auto_json} + {auto_md}")

    hist = os.path.join("runs", "headless_log.csv")
    new_file = not os.path.exists(hist)
    with open(hist, "a", newline="") as f:
        w = csv.writer(f)
        if new_file:
            w.writerow(["stamp", "case", "seed", "frames", "lock_pct", "rmse",
                        "first_lock", "valid_pct", "losses", "acq", "avg_ms",
                        "verdict", "severity", "tags", "benchmark"])
        for r in results:
            w.writerow([stamp, r["case"], r["seed"], r["frames"], r["lock_pct"],
                        r["rmse"], r["first_lock"], r["valid_pct"], r["losses"],
                        r["acq"], r["avg_ms"], r["verdict"], r.get("severity", ""),
                        ",".join(r.get("tags", [])), r.get("benchmark", "")])
    print(f"History -> {hist}")

    try:
        keep = max(int(args.keep), 1)
        snaps = sorted(glob.glob(os.path.join("runs", "headless_*.json")))
        for old in snaps[:-keep]:
            try:
                os.remove(old)
                md_old = old[:-5] + ".md"
                if os.path.exists(md_old):
                    os.remove(md_old)
            except Exception:
                pass
    except Exception:
        pass

    if args.json and args.json != auto_json:
        with open(args.json, "w") as f:
            json.dump(payload, f, indent=2, allow_nan=False)
        print(f"JSON -> {args.json}")
    if args.md and args.md != auto_md:
        with open(args.md, "w") as f:
            f.write("# Headless PAT results\n\n")
            f.write(f"{final}\n\nPASSED: {', '.join(passed) if passed else '-'}\n\n"
                    f"FAILED: {', '.join(failed) if failed else '-'}\n\n")
            f.write("| case | seed | fr | lock% | rmse | p95 | 1st | valid% | "
                    "loss | acq | avgms | sev | tags | benchmark | verdict | reason |\n")
            f.write("|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|\n")
            for r in results:
                f.write(f'| {r["case"]} | {r["seed"]} | {r["frames"]} | {r["lock_pct"]} | '
                        f'{r["rmse"]} | {r["p95"]} | {r["first_lock"]} | {r["valid_pct"]} | '
                        f'{r["losses"]} | {r["acq"]} | {r["avg_ms"]} | {r.get("severity", "")} | '
                        f'{",".join(r.get("tags", []))} | {r.get("benchmark", "")} | '
                        f'{r["verdict"]} | {r["reason"]} |\n')
        print(f"MD -> {args.md}")
    return 0 if (fl == 0 and er == 0) else 1


if __name__ == "__main__":
    raise SystemExit(main())