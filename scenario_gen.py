#!/usr/bin/env python3
"""Custom/random scenario generator for headless pipeline testing.

Lives next to headless.py. Builds config *overrides* (not full configs) for
three axes -- target, environment, disturbances -- either randomly (seeded,
exactly reproducible) or custom (explicit dicts). stdlib-only: no
fsoc_tracker/pat_pipeline import, so any harness can use it.

    from scenario_gen import random_scenario, custom_scenario

    desc, ov, frames = random_scenario(7)          # seeded fuzz
    desc, ov, frames = custom_scenario(            # explicit case
        target={"trajectory": "figure_eight", "speed_px_per_frame": 20.0},
        disturbances={"jitter_px": 6.0},
        corner=[1700, 1700], frames=600)

Apply with headless.deep_merge(base_cfg, ov) (or any recursive merge), then
run. All sampled values stay inside config/validation caps:
gauss_std 0-20, salt&pepper 0-0.15, jitter 0-20, atmo 0-1, platform/target
speed 0-20, size 5-20, count 1-5, blink 0-50 Hz, stars density 0-0.006.
"""
import random

# Far-corner starts: camera stays centred, target begins ~990px off boresight.
CORNERS = [[300, 300], [1700, 300], [300, 1700], [1700, 1700]]

TRAJECTORIES = ["straight", "straight", "figure_eight", "circular", "sinusoidal"]
PLATFORM_TYPES = ["none", "none", "linear", "random"]
ATMO_TYPES = ["clear", "haze", "fog"]
TARGET_SHAPES = ["square", "circle", "diamond", "cross", "triangle"]


def random_target(rng, corner=None):
    """Random target dict (far-corner start unless corner is given)."""
    corner = list(corner if corner is not None else rng.choice(CORNERS))
    tgt = {
        "initial_mode": "user-defined",
        "initial_pos": corner,
        "trajectory": rng.choice(TRAJECTORIES),
        "speed_px_per_frame": round(rng.uniform(1.0, 12.0), 1),
        "size": rng.randint(6, 14),
        "shape": rng.choice(TARGET_SHAPES),
        "count": rng.choice([1, 1, 1, 2, 3, 5]),
        "blink_rate_hz": 0.0 if rng.random() < 0.5 else round(rng.uniform(1.0, 10.0), 1),
    }
    if rng.random() < 0.5:
        t0 = round(rng.uniform(1.0, 8.0), 1)
        tgt["visibility_schedule"] = [[t0, round(t0 + 2.0, 1), "hidden"]]
    return tgt


def random_environment(rng):
    """Random environment dict (stars / vignetting / gradient / texture)."""
    env = {}
    if rng.random() < 0.5:
        env["stars_enabled"] = True
        env["stars_density"] = round(rng.uniform(0.001, 0.004), 4)
        env["stars_brightness"] = 185
        if rng.random() < 0.3:
            env["stars_twinkle"] = True
    if rng.random() < 0.25:
        env["vignetting_enabled"] = True
        env["vignetting_strength"] = round(rng.uniform(0.2, 0.42), 2)
    if rng.random() < 0.25:
        env["gradient_enabled"] = True
        env["gradient_top"] = rng.randint(10, 30)
        env["gradient_bottom"] = rng.randint(30, 60)
    if rng.random() < 0.25:
        env["texture_strength"] = rng.randint(5, 15)
    return env


def random_disturbances(rng):
    """Random disturbances dict with noise/atmosphere/platform/jitter keys."""
    dist = {"noise": {}, "atmosphere": {"type": "clear", "strength": 0.0},
            "platform": {"type": "none", "speed_px_per_frame": 0.0},
            "jitter_px": 0.0}
    if rng.random() < 0.5:
        dist["noise"]["gaussian_enabled"] = True
        dist["noise"]["gaussian_std"] = round(rng.uniform(2.0, 20.0), 1)
    if rng.random() < 0.4:
        dist["noise"]["salt_pepper_enabled"] = True
        dist["noise"]["salt_pepper_prob"] = round(rng.uniform(0.01, 0.12), 3)
    if rng.random() < 0.3:
        dist["noise"]["poisson"] = True
    dist["jitter_px"] = round(rng.uniform(0.0, 10.0), 1)
    if rng.random() < 0.4:
        dist["atmosphere"] = {"type": rng.choice(ATMO_TYPES),
                              "strength": round(rng.uniform(0.1, 0.45), 2)}
    ptype = rng.choice(PLATFORM_TYPES)
    if ptype != "none":
        dist["platform"] = {"type": ptype,
                            "speed_px_per_frame": round(rng.uniform(1.0, 12.0), 1)}
    return dist


def _split_disturbances(disturbances):
    """Map the disturbances dict onto config sections (noise/atmosphere/platform/camera)."""
    disturbances = disturbances or {}
    ov = {}
    if disturbances.get("noise"):
        ov["noise"] = dict(disturbances["noise"])
    if disturbances.get("atmosphere"):
        ov["atmosphere"] = dict(disturbances["atmosphere"])
    if disturbances.get("platform"):
        ov["platform"] = dict(disturbances["platform"])
    if disturbances.get("jitter_px") is not None:
        ov.setdefault("camera", {})["jitter_px"] = disturbances["jitter_px"]
    return ov


def random_scenario(seed_or_rng, frames=None, corner=None):
    """(desc, overrides, frames). seed_or_rng: int seed or random.Random."""
    rng = seed_or_rng if isinstance(seed_or_rng, random.Random) else random.Random(seed_or_rng)
    tgt = random_target(rng, corner=corner)
    env = random_environment(rng)
    dist = random_disturbances(rng)
    ov = {"target": tgt, "camera": {"initial_position": "centre"}}
    ov.update(_split_disturbances(dist))
    if env:
        ov["environment"] = env
    frames = frames or rng.choice([600, 900])
    desc = describe(ov)
    return desc, ov, frames


def custom_scenario(target=None, environment=None, disturbances=None,
                    camera=None, corner=(300, 300), frames=600, desc=None):
    """(desc, overrides, frames) from explicit parts.

    target: partial target dict (merged over a sane far-start base).
    environment: partial environment dict (merged over {} -- base config
        supplies defaults).
    disturbances: {"noise": {...}, "atmosphere": {...}, "platform": {...},
        "jitter_px": float} (jitter wins over camera["jitter_px"] if both).
    camera: partial camera dict (merged over {"initial_position": "centre"}).
    corner: far-start corner used when target omits initial_pos.
    """
    tgt = {"initial_mode": "user-defined", "initial_pos": list(corner),
           "trajectory": "straight", "speed_px_per_frame": 3.0,
           "size": 10, "count": 1, "blink_rate_hz": 0.0}
    tgt.update(target or {})
    if (target or {}).get("initial_pos") is None and "initial_pos" not in (target or {}):
        tgt["initial_pos"] = list(corner)
    cam = {"initial_position": "centre"}
    cam.update(camera or {})
    ov = {"target": tgt, "camera": cam}
    ov.update(_split_disturbances(disturbances))
    if ov.get("camera", {}).get("jitter_px") is None and (camera or {}).get("jitter_px") is not None:
        ov["camera"]["jitter_px"] = (camera or {})["jitter_px"]
    if environment:
        ov["environment"] = dict(environment)
    return (desc or describe(ov)), ov, frames


def describe(ov):
    """One-line human summary of a scenario's overrides."""
    try:
        t = ov.get("target", {})
        c = ov.get("camera", {})
        n = ov.get("noise", {})
        p = ov.get("platform", {})
        a = ov.get("atmosphere", {})
        bits = [f"{t.get('initial_pos')} {t.get('trajectory')}@{t.get('speed_px_per_frame')}px/f",
                f"size={t.get('size')}x{t.get('count')} blink={t.get('blink_rate_hz')}"]
        if t.get("visibility_schedule"):
            bits.append(f"hidden={t['visibility_schedule']}")
        if n.get("gaussian_enabled"):
            bits.append(f"gauss={n.get('gaussian_std')}")
        if n.get("salt_pepper_enabled"):
            bits.append(f"spp={n.get('salt_pepper_prob')}")
        if n.get("poisson"):
            bits.append("poisson")
        if c.get("jitter_px"):
            bits.append(f"jitter={c.get('jitter_px')}")
        if (a.get("type", "clear") != "clear"):
            bits.append(f"{a.get('type')}@{a.get('strength')}")
        if (p.get("type", "none") != "none"):
            bits.append(f"plat-{p.get('type')}@{p.get('speed_px_per_frame')}")
        e = ov.get("environment", {})
        if e.get("stars_enabled"):
            bits.append(f"stars@{e.get('stars_density')}")
        if e.get("vignetting_enabled"):
            bits.append("vignette")
        if e.get("gradient_enabled"):
            bits.append("gradient")
        return " ".join(bits)
    except Exception:
        return "custom scenario"


if __name__ == "__main__":
    import sys

    n = int(sys.argv[1]) if len(sys.argv) > 1 else 3
    seed = int(sys.argv[2]) if len(sys.argv) > 2 else 7
    rng = random.Random(seed)
    for k in range(n):
        desc, ov, fr = random_scenario(rng)
        print(f"[{k + 1}] [{fr} frames] {desc}")
