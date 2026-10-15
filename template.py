"""Template: build your own headless presets (copy me to my_run.py and edit).

Covers the full tunable surface with validated limits (from
src/pat_common/config/validation/*.py + sections/*.py). Anything outside
these limits raises AssertionError under load_config(); headless.py merges
with deep_merge() directly so it can also probe slightly outside (e.g. fps 20).

QUICK START:
  1. Copy:  cp my_headless_template.py my_run.py
  2. Edit MY_CASES below (overrides are deep-merged over DEFAULT_CONFIG).
  3. Run:   .\\.venv\\Scripts\\python.exe my_run.py            # all MY_CASES
             .\\.venv\\Scripts\\python.exe my_run.py --list     # show benches
             .\\.venv\\Scripts\\python.exe my_run.py --case MY1 --frames 200

RULES (same as headless.py):
  - Far-start is enforced: camera centre + target far corner. If you set a
    near/centre start it gets rewritten to the corner in "corner".
  - Stars are mandatory: every case gets stars_density/brightness (0-0.006).
  - Benchmarks: each case needs a bench it must beat (lock/rmse/first/losses
    or acq+valid for blink/hidden/crowded). Verdicts: STRICT-PASS /
    INTERMITTENT-PASS / FAIL / ERROR.
"""

import copy
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "src"))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "tests"))

from pat_common.config.defaults import DEFAULT_CONFIG
from pat_common.config.loader import deep_merge

from headless import (  # reuse the proven runner, don't copy it
    FAR_CORNERS,
    apply_stars,
    bench_str,
    enforce_far_start,
    print_table,
    run_tracking_case,
)

# ---------------------------------------------------------------------------
# PARAMETER REFERENCE (validated limits). Overrides below must stay inside
# these unless you deliberately probe outside (headless deep_merge allows it,
# load_config/validate would reject).
#
# world:        width/height 2000-4000 | background 0-80
# camera:       type mono|colour|color | resolution [320-1920, 240-1080]
#               fov_deg [1-12, 1-12] | fps 30-60 (E8 probes 20) | update_interval_hz 20-60
#               initial_position centre|user-defined (+initial_pan/tilt deg)
#               max_pan/tilt_speed 1-15 (spec 5-10) | jitter_px 0-20
# target:       type beacon_spot|beacon|spot | count 1-5 | size 5-20 | intensity 0-255
#               shape square|circle|diamond|cross|triangle|custom (+custom_polygon 3-16 pts, +-20px)
#               initial_mode random|centre|user-defined | initial_pos [x,y] in world
#               trajectory straight|circular|figure_eight|random|spiral|sinusoidal|user-defined
#               trajectories [len==count] | distractor_trajectory | speeds [len==count, 0-20 each]
#               speed_px_per_frame 0-20 | blink_rate_hz 0-50 (0=steady)
#               visibility_schedule [[start_s, end_s, "hidden"], ...]
# platform:     type none|linear|circular|random|spiral|figure_of_8 | speed 0-20 | amplitude 0-1000
# noise:        gaussian_std 0-20 (+enabled) | salt_pepper_prob 0-0.15 (+enabled) | poisson bool
# atmosphere:   type clear|haze|fog|rain|low_light | strength 0-1
# environment:  gradient linear|radial|diagonal, top/bottom 0-80, angle 0-360
#               texture_strength 0-20 | stars_density 0-0.006 | stars_brightness 0-255
#               stars_min/max_mag 0-255 (min<=max) | twinkle amount 0-30 | seed 0-999999 | max_count 0-50000
#               vignetting strength 0-0.95, radius 0.05-1.0, falloff 0.3-6.0, center 0-1
#               brightness_gain 0.5-1.8 | brightness_offset -40..40
# detector:     threshold_k ~3.0 | min_area 8 | max_area 900 | blur_ksize | adaptive_block/C
# tracker:      process_noise 0.1-5 | meas_noise 0.5-10 | gate_sigma ~5 | lost_timeout 15 | reacq 30
# controller:   kp_pan/tilt 0.1-5 | ki 0-1 | kd 0-2 | deadzone 0-20 | feedforward 0-5
#               search_angle_step 0.05-1.5 | radius_step 0.01-0.5 | radius_max 1-8
#               rate_scale 0.1-1.5 | spiral_phase_s 1-10 | raster_pan/tilt 0.1-1.0
#               stare 0.05-1 | intercept_gain 0.5-5 | lead 0-1s | unc_scale 0-2
#               unc_max_boost 1-4 | fast_vel 0.2-5 | give_up 60-3600
# experiment:   seed int | duration_s (= frames/fps, auto) | cue_to_target bool
# headless-only: frames 400-1200 typical | seed | corner 0-3 | star (density, brightness)
# ---------------------------------------------------------------------------

# Your cases. Fields: key, name, desc, corner 0-3, frames, seed,
#   overrides (deep-merged), star (density, brightness), intermittent bool,
#   bench dict (lock/rmse/first/losses [+ acq/valid for intermittent]).
MY_CASES = [
    {
        "key": "MY1", "name": "MY1-tiny-blink-duel",
        "desc": "Example: size-6 + 5Hz blink + star clutter. Copy and edit me.",
        "corner": 0, "frames": 600, "seed": 42,
        "overrides": {
            "target": {"trajectory": "straight", "speed_px_per_frame": 5.0,
                       "size": 6, "blink_rate_hz": 5.0},
            "camera": {"jitter_px": 4.0},
        },
        "star": (0.002, 180), "intermittent": True,
        "bench": {"lock": 10.0, "rmse": 12.0, "first": 600, "losses": 8,
                  "acq": 2, "valid": 15.0},
        # To also probe control tuning, add e.g.:
        # "controller": {"kp_pan": 1.6, "kp_tilt": 1.6, "deadzone_px": 1.5},
        # "tracker": {"process_noise": 1.0, "meas_noise": 5.0},
        # "detector": {"threshold_k": 3.5, "min_area": 6},
    },
    {
        "key": "MY2", "name": "MY2-fog-wall",
        "desc": "Example: EXPECTED-HARD fog. Must complete, low bar.",
        "corner": 1, "frames": 600, "seed": 42,
        "overrides": {
            "target": {"trajectory": "straight", "speed_px_per_frame": 3.0},
            "atmosphere": {"type": "fog", "strength": 0.7},
        },
        "star": (0.001, 170), "intermittent": False,
        "bench": {"lock": 5.0, "rmse": 15.0, "first": 800, "losses": 10},
    },
]


def build_my_config(case, seed=None):
    """Merge DEFAULT_CONFIG + case overrides + stars + far-start (same as headless)."""
    cfg = deep_merge(copy.deepcopy(DEFAULT_CONFIG), copy.deepcopy(case["overrides"]))
    dens, bri = case["star"]
    e = cfg.setdefault("environment", {})
    e["stars_enabled"] = True
    e["stars_density"] = float(min(max(dens, 0.0), 0.006))
    e["stars_brightness"] = int(bri)
    cfg = enforce_far_start(cfg, case.get("corner", 0))
    fps = max(float(cfg["camera"].get("fps", 30.0)), 1)
    cfg["experiment"]["duration_s"] = round(case["frames"] / fps, 2)
    cfg["experiment"]["seed"] = int(seed if seed is not None else case.get("seed", 42))
    return cfg


def run_my_case(case, frames=None, seed=None, timeout_s=300.0):
    """Run one MY case through the canonical pipeline; returns result dict."""
    import headless as H

    cfg = build_my_config(case, seed)
    fr = frames or case["frames"]
    sd = int(seed if seed is not None else case.get("seed", 42))
    bench_key = case["key"]
    if bench_key not in H.BENCHMARKS:  # register custom bench so verdict uses it
        H.BENCHMARKS[bench_key] = dict(case.get("bench", {}), note=case.get("desc", "")[:60])
    else:
        H.BENCHMARKS[bench_key] = dict(case.get("bench", {}), note=case.get("desc", "")[:60])
    return run_tracking_case(f'{case["key"]}-s{sd}', f'{case["name"]}@s{sd}',
                             case["desc"], cfg, fr, sd,
                             case.get("intermittent", False),
                             bkey=bench_key, timeout_s=timeout_s)


def main(argv=None):
    import argparse

    ap = argparse.ArgumentParser(description="My headless presets (template)")
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--case", default=None, help="run one key/name (default: all)")
    ap.add_argument("--frames", type=int, default=None)
    ap.add_argument("--seed", type=int, default=None)
    args = ap.parse_args(argv)

    cases = MY_CASES
    if args.case:
        cases = [c for c in MY_CASES if c["key"] == args.case or c["name"] == args.case]
        if not cases:
            raise SystemExit(f"unknown case {args.case}")

    if args.list:
        for c in MY_CASES:
            print(f'  {c["key"]:<4} {c["name"]:<24} {c["frames"]}f corner={FAR_CORNERS[c.get("corner", 0)]} star={c["star"]}')
            print(f'      BENCH: {c.get("bench", {})} :: {c["desc"]}')
        return 0

    results = []
    for c in cases:
        r = run_my_case(c, frames=args.frames, seed=args.seed)
        results.append(r)
        print(f'[{r["case"]}] {r["verdict"]} lock={r["lock_pct"]}% rmse={r["rmse"]} 1st={r["first_lock"]} :: {r["reason"]}')
    print()
    print_table(results)
    fails = [r["case"] for r in results if r["verdict"] in ("FAIL", "ERROR")]
    print(f'FINAL: {"PASS" if not fails else "FAIL - " + ", ".join(fails)}')
    return 0 if not fails else 1


if __name__ == "__main__":
    raise SystemExit(main())
