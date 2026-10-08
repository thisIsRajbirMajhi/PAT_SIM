"""Built-in stress presets shared by the CLI runner and the GUI preset panel.

Single source of truth for X1..X10 (previously defined in headless.py).
Each entry: name -> (description, overrides, frames).
Frame count converts to duration via duration_s = frames / fps at apply time.
"""
import copy

SCENARIOS = {
    "X1-baseline": ("Defaults sanity check (must PASS).", {}, 240),
    "X2-sensor-hell": ("Max Gaussian noise + 10% salt&pepper + poisson.", {
        "noise": {"gaussian_enabled": True, "gaussian_std": 20.0,
                  "salt_pepper_enabled": True, "salt_pepper_prob": 0.10,
                  "poisson": True}}, 240),
    "X3-motion-hell": ("Max camera jitter + aggressive random platform.", {
        "camera": {"jitter_px": 20.0},
        "platform": {"type": "random", "speed_px_per_frame": 15.0}}, 240),
    "X4-speed-demon": ("Target at max speed on figure-eight.", {
        "target": {"speed_px_per_frame": 20.0, "trajectory": "figure_eight"}}, 240),
    "X5-tiny-target": ("Minimum-size target + star clutter.", {
        "target": {"size": 5, "speed_px_per_frame": 6.0, "trajectory": "straight"},
        "environment": {"stars_enabled": True, "stars_density": 0.002,
                        "stars_brightness": 185}}, 240),
    "X6-blink-dropout": ("5 Hz blinking beacon + 2 s hidden dropout.", {
        "target": {"blink_rate_hz": 5.0,
                   "visibility_schedule": [[1.0, 3.0, "hidden"]]}}, 240),
    "X7-atmo-soup": ("Full-strength fog.", {
        "atmosphere": {"type": "fog", "strength": 1.0}}, 240),
    "X8-cold-start": ("Far-corner crossing, no cue: scan to track.", {
        "target": {"initial_mode": "user-defined", "initial_pos": [300, 300],
                   "trajectory": "straight", "speed_px_per_frame": 3.0}}, 900),
    "X9-crowded": ("5 targets + stars + vignetting.", {
        "target": {"count": 5},
        "environment": {"stars_enabled": True, "stars_density": 0.002,
                        "stars_brightness": 185, "vignetting_enabled": True,
                        "vignetting_strength": 0.42}}, 240),
    "X10-combined-hell": ("Noise + jitter + fast target + blink + fog + platform.", {
        "noise": {"gaussian_enabled": True, "gaussian_std": 12.0,
                  "salt_pepper_enabled": True, "salt_pepper_prob": 0.05},
        "camera": {"jitter_px": 12.0},
        "target": {"speed_px_per_frame": 12.0, "trajectory": "figure_eight",
                   "blink_rate_hz": 2.0},
        "atmosphere": {"type": "fog", "strength": 0.6},
        "platform": {"type": "linear", "speed_px_per_frame": 8.0}}, 300),
}

FAR_START = {"target": {"initial_mode": "user-defined", "initial_pos": [300, 300],
                        "trajectory": "straight", "speed_px_per_frame": 3.0}}

STRESS_PREFIX = "Stress: "


def stress_names():
    return list(SCENARIOS)


def describe(name):
    desc, _ov, fr = SCENARIOS[name]
    return f"{desc} [{fr} frames]"


def build_config(base_cfg, name, deep_merge):
    """Return a new config with scenario overrides applied + duration set."""
    desc, ov, fr = SCENARIOS[name]
    cfg = deep_merge(base_cfg, copy.deepcopy(ov))
    try:
        fps = max(float(cfg["camera"].get("fps", 30.0)), 1)
    except Exception:
        fps = 30.0
    cfg["experiment"]["duration_s"] = round(fr / fps, 2)
    return cfg


__all__ = ["SCENARIOS", "FAR_START", "STRESS_PREFIX", "stress_names", "describe", "build_config"]
