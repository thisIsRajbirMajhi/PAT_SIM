"""Built-in stress presets shared by the CLI runner and the GUI preset panel.

Single source of truth for X1..X10 (previously defined in headless.py).
Each entry: name -> (description, overrides, frames).
Frame count converts to duration via duration_s = frames / fps at apply time.

Every preset starts FAR: the camera stays centred while the target begins in
a far world corner (~990px / ~6 deg off boresight), so each uncued run must
traverse the full pipeline unassisted: scan -> detect -> verify -> acquire
-> track. The extreme suite runs all presets uncued (cold); use --cue for
assisted starts. Far starts need longer runs (600-900 frames) to allow the
sweep to cover the world.
All disturbance values stay inside validated caps (gauss 0-20, spp 0-0.15,
jitter 0-20, atmo 0-1, platform/target speed 0-20, size 5-20, count 1-5,
blink 0-50 Hz, stars density 0-0.006).
Tuning notes (all verified uncued, seed 42, cold/intermittent verdicts):
- Straight @30deg from a corner it heads INTO parks there (dir never flips
  on bounce); use corners the path leaves ([300,300] crosses centre,
  [1700,300] slides the east edge). Corner-anchored circular/figure-eight
  orbits never enter the sweep band — kept only where the sweep provably
  finds them (X4, X9).
- Fog >= 0.5 blinds the detector at any target size (veil kills contrast);
  X7 uses the blinding edge (0.3). Jitter >= 12 breaks RMSE < 10 by itself
  (white-noise floor); X3 uses 10. Blinkers are judged by the intermittent
  rule (>=2 locks, visible share) since no duty-cycled beacon can hold 90%.
"""
import copy

# Camera pinned centre + target in a far corner => maximum initial separation.
_FAR_CENTRE_CAM = {"initial_position": "centre"}


def _far(target_extra, corner):
    d = {"initial_mode": "user-defined", "initial_pos": list(corner)}
    d.update(target_extra)
    return {"target": d, "camera": dict(_FAR_CENTRE_CAM)}


def _with(base_overrides, extra):
    out = copy.deepcopy(base_overrides)
    for k, v in extra.items():
        if k in out and isinstance(out[k], dict) and isinstance(v, dict):
            out[k] = {**out[k], **v}
        else:
            out[k] = copy.deepcopy(v)
    return out


SCENARIOS = {
    "X1-baseline": ("Far-start baseline (must PASS).", _far(
        {"trajectory": "straight", "speed_px_per_frame": 3.0}, [300, 300]), 900),
    "X2-sensor-hell": ("Far start + heavy Gaussian noise + 10% salt&pepper + poisson.", _with(
        _far({"trajectory": "straight", "speed_px_per_frame": 4.0, "size": 8}, [1700, 300]),
        {"noise": {"gaussian_enabled": True, "gaussian_std": 20.0,
                   "salt_pepper_enabled": True, "salt_pepper_prob": 0.10,
                   "poisson": True}}), 600),
    "X3-motion-hell": ("Far start + heavy camera jitter + aggressive random platform.", _with(
        _far({"trajectory": "straight", "speed_px_per_frame": 6.0}, [300, 1700]),
        {"camera": {"jitter_px": 10.0},
         "platform": {"type": "random", "speed_px_per_frame": 15.0}}), 600),
    "X4-speed-demon": ("Far start + target at max speed on figure-eight + jitter.", _with(
        _far({"speed_px_per_frame": 20.0, "trajectory": "figure_eight"}, [1700, 1700]),
        {"camera": {"jitter_px": 6.0},
         "platform": {"type": "linear", "speed_px_per_frame": 5.0}}), 600),
    "X5-tiny-target": ("Far start + small fast target + star clutter.", _with(
        _far({"size": 6, "speed_px_per_frame": 6.0, "trajectory": "straight"}, [1700, 300]),
        {"environment": {"stars_enabled": True, "stars_density": 0.002,
                         "stars_brightness": 185}}), 900),
    "X6-blink-dropout": ("Far start + 5 Hz blinking beacon + 2 s hidden dropout + platform drift.", _with(
        _far({"blink_rate_hz": 5.0, "speed_px_per_frame": 3.0,
              "trajectory": "straight",
              "visibility_schedule": [[1.0, 3.0, "hidden"]]}, [300, 300]),
        {"platform": {"type": "random", "speed_px_per_frame": 3.0}}), 900),
    "X7-atmo-soup": ("Far start + thick fog + jitter + small moving target.", _with(
        _far({"trajectory": "straight", "speed_px_per_frame": 4.0, "size": 10}, [300, 300]),
        {"atmosphere": {"type": "fog", "strength": 0.3},
         "camera": {"jitter_px": 8.0}}), 600),
    "X8-cold-start": ("Far-corner crossing + star clutter + slow drift: scan to track.", _with(
        _far({"trajectory": "straight", "speed_px_per_frame": 3.0}, [300, 300]),
        {"environment": {"stars_enabled": True, "stars_density": 0.002,
                         "stars_brightness": 185},
         "platform": {"type": "linear", "speed_px_per_frame": 3.0}}), 900),
    "X9-crowded": ("Far start + 5 targets on figure-eight + dense stars + vignetting.", _with(
        _far({"count": 5, "trajectory": "figure_eight", "speed_px_per_frame": 6.0}, [1700, 300]),
        {"environment": {"stars_enabled": True, "stars_density": 0.004,
                         "stars_brightness": 185, "vignetting_enabled": True,
                         "vignetting_strength": 0.42}}), 600),
    "X10-combined-hell": ("Far start + noise + jitter + fast blinking target + fog + platform.", _with(
        _far({"speed_px_per_frame": 8.0, "trajectory": "straight", "size": 12,
              "blink_rate_hz": 2.0}, [300, 300]),
        {"noise": {"gaussian_enabled": True, "gaussian_std": 8.0,
                  "salt_pepper_enabled": True, "salt_pepper_prob": 0.05},
         "camera": {"jitter_px": 10.0},
         "atmosphere": {"type": "fog", "strength": 0.6},
         "platform": {"type": "linear", "speed_px_per_frame": 8.0}}), 900),
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
