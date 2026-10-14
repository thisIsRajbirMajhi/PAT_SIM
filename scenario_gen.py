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
run. All sampled values stay inside config/validation caps (see LIMITS):
gauss_std 0-20, salt&pepper 0-0.15, jitter 0-20, atmo 0-1, platform/target
speed 0-20, size 5-20, count 1-5, blink 0-50 Hz, stars density 0-0.006.

Guarantees (checked by ``python scenario_gen.py --selftest``):
  * same seed -> identical (desc, overrides, frames), run after run;
  * random scenarios always pass validate_overrides() (generator self-checks);
  * custom scenarios are validated (ValueError on out-of-range / typo'd
    disturbance keys) and never alias the caller's dicts/lists;
  * every scenario keeps camera.initial_position == "centre" unless a custom
    camera dict says otherwise (a former bug dropped it whenever disturbances
    were applied).

CLI:
    python scenario_gen.py [N] [SEED] [--json]     # print N random scenarios
    python scenario_gen.py --selftest [N]          # property checks, exit 0/1
"""
import argparse
import copy
import json
import math
import random
import sys
import warnings

# Far-corner starts: camera stays centred, target begins ~990px off boresight.
CORNERS = [[300, 300], [1700, 300], [300, 1700], [1700, 1700]]

TRAJECTORIES = ["straight", "straight", "figure_eight", "circular", "sinusoidal"]
PLATFORM_TYPES = ["none", "none", "linear", "random"]
ATMO_TYPES = ["clear", "haze", "fog"]
TARGET_SHAPES = ["square", "circle", "diamond", "cross", "triangle"]

# (lo, hi) inclusive caps per "section.key" -- mirrors config validation.
LIMITS = {
    "noise.gaussian_std": (0.0, 20.0),
    "noise.salt_pepper_prob": (0.0, 0.15),
    "camera.jitter_px": (0.0, 20.0),
    "atmosphere.strength": (0.0, 1.0),
    "platform.speed_px_per_frame": (0.0, 20.0),
    "target.speed_px_per_frame": (0.0, 20.0),
    "target.size": (5, 20),
    "target.count": (1, 5),
    "target.blink_rate_hz": (0.0, 50.0),
    "environment.stars_density": (0.0, 0.006),
    "environment.stars_brightness": (0, 255),
    "environment.vignetting_strength": (0.0, 1.0),
    "environment.gradient_top": (0, 255),
    "environment.gradient_bottom": (0, 255),
    "environment.texture_strength": (0, 255),
}
INTEGER_KEYS = {"target.size", "target.count"}

# Known category values. Unknown values only WARN (the real config may
# support more names than this generator samples).
KNOWN_NAMES = {
    "atmosphere.type": set(ATMO_TYPES),
    "platform.type": set(PLATFORM_TYPES),
    "target.trajectory": set(TRAJECTORIES),
    "target.shape": set(TARGET_SHAPES),
}

DISTURBANCE_KEYS = {"noise", "atmosphere", "platform", "jitter_px"}


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------
def _is_num(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def _deep_merge(dst, src):
    """In-place recursive merge of src into dst (src values are deep-copied)."""
    for k, v in src.items():
        if isinstance(v, dict) and isinstance(dst.get(k), dict):
            _deep_merge(dst[k], v)
        else:
            dst[k] = copy.deepcopy(v)
    return dst


def _check_frames(frames):
    if isinstance(frames, bool) or not isinstance(frames, int) or frames <= 0:
        raise ValueError(f"frames must be a positive int, got {frames!r}")
    return frames


def validate_overrides(ov):
    """Return a list of problems (empty == OK). Pure; never raises.

    Checks numeric caps (LIMITS), integer-ness of size/count, finite
    start position, and visibility_schedule shape/order. Unknown category
    names (trajectory/shape/atmosphere/platform type) emit a warning only.
    """
    problems = []
    if not isinstance(ov, dict):
        return ["overrides must be a dict"]

    for path, (lo, hi) in LIMITS.items():
        sec, key = path.split(".")
        section = ov.get(sec)
        if section is None:
            continue
        if not isinstance(section, dict):
            problems.append(f"{sec} must be a dict, got {type(section).__name__}")
            continue
        if key not in section:
            continue
        v = section[key]
        if not _is_num(v):
            problems.append(f"{path}={v!r} is not a finite number")
        elif path in INTEGER_KEYS and int(v) != v:
            problems.append(f"{path}={v!r} must be an integer")
        elif not (lo <= v <= hi):
            problems.append(f"{path}={v} outside [{lo}, {hi}]")

    tgt = ov.get("target") if isinstance(ov.get("target"), dict) else {}
    pos = tgt.get("initial_pos")
    if pos is not None and not (isinstance(pos, (list, tuple)) and len(pos) == 2
                                and all(_is_num(c) for c in pos)):
        problems.append(f"target.initial_pos={pos!r} must be [x, y] (finite numbers)")

    sched = tgt.get("visibility_schedule")
    if sched is not None:
        if not isinstance(sched, (list, tuple)):
            problems.append("target.visibility_schedule must be a list")
        else:
            for n, seg in enumerate(sched):
                if not (isinstance(seg, (list, tuple)) and len(seg) == 3
                        and _is_num(seg[0]) and _is_num(seg[1])):
                    problems.append(f"visibility_schedule[{n}]={seg!r} must be [t0, t1, state]")
                elif not (0 <= seg[0] < seg[1]):
                    problems.append(f"visibility_schedule[{n}]={seg!r} needs 0 <= t0 < t1")

    for path, names in KNOWN_NAMES.items():
        sec, key = path.split(".")
        section = ov.get(sec)
        if isinstance(section, dict) and section.get(key) is not None \
                and section[key] not in names:
            warnings.warn(f"{path}={section[key]!r} is not one of the generator's "
                          f"known values {sorted(names)}", stacklevel=3)
    return problems


def _split_disturbances(disturbances):
    """Map the disturbances dict onto config sections (noise/atmosphere/platform/camera).

    Raises ValueError on unknown keys (e.g. a typo'd "jiter_px" used to be
    silently ignored, turning a stress test into a clean run).
    """
    d = disturbances or {}
    if not isinstance(d, dict):
        raise ValueError("disturbances must be a dict")
    unknown = set(d) - DISTURBANCE_KEYS
    if unknown:
        raise ValueError(f"unknown disturbance key(s) {sorted(unknown)}; "
                         f"allowed: {sorted(DISTURBANCE_KEYS)}")
    ov = {}
    for sec in ("noise", "atmosphere", "platform"):
        if d.get(sec):
            if not isinstance(d[sec], dict):
                raise ValueError(f"disturbances[{sec!r}] must be a dict")
            ov[sec] = copy.deepcopy(d[sec])
    if d.get("jitter_px") is not None:
        ov["camera"] = {"jitter_px": d["jitter_px"]}
    return ov


# --------------------------------------------------------------------------
# random sampling (draw ORDER is frozen so old seeds still reproduce)
# --------------------------------------------------------------------------
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


def random_scenario(seed_or_rng, frames=None, corner=None):
    """(desc, overrides, frames). seed_or_rng: int seed or random.Random.

    The frame-count draw is always consumed (even when ``frames`` is given)
    so the RNG stream, and therefore every later scenario in a shared-RNG
    fuzz loop, does not depend on whether frames was overridden.
    """
    if isinstance(seed_or_rng, random.Random):
        rng = seed_or_rng
    else:
        if isinstance(seed_or_rng, bool) or not isinstance(seed_or_rng, int):
            raise TypeError(f"seed must be int or random.Random, got {seed_or_rng!r}")
        rng = random.Random(seed_or_rng)
    tgt = random_target(rng, corner=corner)
    env = random_environment(rng)
    dist = random_disturbances(rng)
    drawn_frames = rng.choice([600, 900])
    frames = drawn_frames if frames is None else _check_frames(frames)

    ov = {"target": tgt, "camera": {"initial_position": "centre"}}
    _deep_merge(ov, _split_disturbances(dist))   # merge: must NOT replace camera
    if env:
        ov["environment"] = env

    problems = validate_overrides(ov)
    if problems:  # generator bug, never a user error
        raise RuntimeError("random_scenario produced invalid overrides: "
                           + "; ".join(problems))
    return describe(ov), ov, frames


def custom_scenario(target=None, environment=None, disturbances=None,
                    camera=None, corner=(300, 300), frames=600, desc=None,
                    validate=True):
    """(desc, overrides, frames) from explicit parts.

    target: partial target dict (merged over a sane far-start base).
    environment: partial environment dict (merged over {} -- base config
        supplies defaults).
    disturbances: {"noise": {...}, "atmosphere": {...}, "platform": {...},
        "jitter_px": float} (jitter wins over camera["jitter_px"] if both).
        Unknown keys raise ValueError.
    camera: partial camera dict (merged over {"initial_position": "centre"}).
    corner: far-start corner used when target omits initial_pos (or sets it
        to None).
    validate: raise ValueError listing every out-of-range value (default).
    Inputs are deep-copied; the returned overrides never alias the caller's.
    """
    _check_frames(frames)
    if not (isinstance(corner, (list, tuple)) and len(corner) == 2):
        raise ValueError(f"corner must be [x, y], got {corner!r}")

    tgt = {"initial_mode": "user-defined", "initial_pos": list(corner),
           "trajectory": "straight", "speed_px_per_frame": 3.0,
           "size": 10, "count": 1, "blink_rate_hz": 0.0}
    tgt.update(copy.deepcopy(target or {}))
    if tgt.get("initial_pos") is None:
        tgt["initial_pos"] = list(corner)
    else:
        tgt["initial_pos"] = list(tgt["initial_pos"])

    cam = {"initial_position": "centre"}
    cam.update(copy.deepcopy(camera or {}))
    ov = {"target": tgt, "camera": cam}
    _deep_merge(ov, _split_disturbances(disturbances))  # disturbance jitter wins
    if environment:
        ov["environment"] = copy.deepcopy(dict(environment))

    if validate:
        problems = validate_overrides(ov)
        if problems:
            raise ValueError("invalid custom scenario: " + "; ".join(problems))
    return (desc or describe(ov)), ov, frames


def describe(ov):
    """One-line human summary of a scenario's overrides (never raises)."""
    try:
        t = ov.get("target") or {}
        c = ov.get("camera") or {}
        n = ov.get("noise") or {}
        p = ov.get("platform") or {}
        a = ov.get("atmosphere") or {}
        e = ov.get("environment") or {}
        bits = [f"{t.get('initial_pos')} {t.get('trajectory')}@{t.get('speed_px_per_frame')}px/f",
                f"{t.get('shape', 'default')} size={t.get('size')}x{t.get('count')} "
                f"blink={t.get('blink_rate_hz')}"]
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
        if a.get("type", "clear") != "clear":
            bits.append(f"{a.get('type')}@{a.get('strength')}")
        if p.get("type", "none") != "none":
            bits.append(f"plat-{p.get('type')}@{p.get('speed_px_per_frame')}")
        if e.get("stars_enabled"):
            bits.append(f"stars@{e.get('stars_density')}")
        if e.get("vignetting_enabled"):
            bits.append("vignette")
        if e.get("gradient_enabled"):
            bits.append("gradient")
        if e.get("texture_strength"):
            bits.append(f"texture={e.get('texture_strength')}")
        return " ".join(bits)
    except Exception:
        return "custom scenario"


# --------------------------------------------------------------------------
# self-test
# --------------------------------------------------------------------------
def selftest(n=200):
    """Property checks over seeds 0..n-1 plus custom_scenario edge cases."""
    fails = []

    def check(cond, msg):
        if not cond:
            fails.append(msg)

    with warnings.catch_warnings():
        warnings.simplefilter("error")  # any unexpected warning is a failure
        for seed in range(n):
            a = random_scenario(seed)
            b = random_scenario(seed)
            check(a == b, f"seed {seed}: not deterministic")
            desc, ov, frames = a
            check(validate_overrides(ov) == [], f"seed {seed}: invalid {validate_overrides(ov)}")
            check(ov["camera"].get("initial_position") == "centre",
                  f"seed {seed}: camera.initial_position lost")
            check("jitter_px" in ov["camera"], f"seed {seed}: jitter missing")
            check(frames in (600, 900), f"seed {seed}: frames {frames}")
            try:
                check(json.loads(json.dumps(ov)) == ov, f"seed {seed}: not JSON round-trippable")
            except TypeError as e:
                fails.append(f"seed {seed}: not JSON serialisable ({e})")
            # shared-rng streams must not depend on a frames override
            r1, r2 = random.Random(seed), random.Random(seed)
            random_scenario(r1)
            random_scenario(r2, frames=123)
            check(random_scenario(r1)[1] == random_scenario(r2)[1],
                  f"seed {seed}: frames override perturbs RNG stream")
        # corner pass-through
        _, ov, _ = random_scenario(1, corner=[10, 20])
        check(ov["target"]["initial_pos"] == [10, 20], "corner override ignored")

        # ---- custom_scenario -------------------------------------------------
        tin = {"initial_pos": None, "visibility_schedule": [[1.0, 3.0, "hidden"]]}
        _, ov, fr = custom_scenario(target=tin, corner=[1700, 300],
                                    camera={"initial_position": "centre", "jitter_px": 2.0},
                                    disturbances={"jitter_px": 6.0,
                                                  "noise": {"gaussian_enabled": True,
                                                            "gaussian_std": 5.0}})
        check(ov["target"]["initial_pos"] == [1700, 300], "explicit None initial_pos not replaced")
        check(ov["camera"]["jitter_px"] == 6.0, "disturbance jitter must win")
        check(ov["camera"]["initial_position"] == "centre", "custom dropped camera keys")
        ov["target"]["visibility_schedule"][0][0] = 99
        check(tin["visibility_schedule"][0][0] == 1.0, "custom aliases caller's lists")
        for bad, why in [({"target": {"speed_px_per_frame": 25.0}}, "speed over cap"),
                         ({"target": {"count": 2.5}}, "non-integer count"),
                         ({"target": {"size": float("nan")}}, "NaN size"),
                         ({"disturbances": {"jiter_px": 3.0}}, "typo'd disturbance key"),
                         ({"disturbances": {"noise": {"gaussian_std": 21.0}}}, "gauss over cap"),
                         ({"frames": 0}, "zero frames"),
                         ({"target": {"visibility_schedule": [[5.0, 2.0, "hidden"]]}}, "reversed window")]:
            try:
                custom_scenario(**bad)
                fails.append(f"custom_scenario accepted invalid input: {why}")
            except ValueError:
                pass
        # validate=False bypasses range checks but not typo detection
        custom_scenario(target={"speed_px_per_frame": 25.0}, validate=False)
    return fails


def main(argv=None):
    ap = argparse.ArgumentParser(description="Print seeded random scenarios or self-test the generator.")
    ap.add_argument("n", nargs="?", type=int, default=3, help="scenarios to print (default 3)")
    ap.add_argument("seed", nargs="?", type=int, default=7, help="RNG seed (default 7)")
    ap.add_argument("--json", action="store_true", help="print full overrides as JSON lines")
    ap.add_argument("--selftest", nargs="?", type=int, const=200, default=None, metavar="N",
                    help="run property checks over N seeds (default 200) and exit 0/1")
    args = ap.parse_args(argv)

    if args.selftest is not None:
        fails = selftest(args.selftest)
        for f in fails[:50]:
            print("FAIL:", f)
        print(f"selftest: {'FAILED (%d)' % len(fails) if fails else 'OK'}")
        return 1 if fails else 0

    rng = random.Random(args.seed)
    for k in range(args.n):
        desc, ov, fr = random_scenario(rng)
        print(f"[{k + 1}] [{fr} frames] {desc}")
        if args.json:
            print(json.dumps(ov, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())