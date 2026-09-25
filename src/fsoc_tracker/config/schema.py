from typing import Any, Dict

def validate_config(cfg: Dict[str, Any]) -> Dict[str, Any]:
    # -- Camera Parameters --
    w, h = cfg["world"]["width"], cfg["world"]["height"]
    assert 2000 <= w <= 4000 and 2000 <= h <= 4000, "Screen Size must be 2000-4000 (spec min 2000)"
    assert cfg["world"].get("background", 18) in range(0, 80), "background 0-80"
    assert cfg["camera"]["type"] in ("monochrome", "colour", "color"), "Camera Type must be monochrome|colour"
    assert 320 <= cfg["camera"]["resolution"][0] <= 1920 and 240 <= cfg["camera"]["resolution"][1] <= 1080, "Resolution 320-1920 x 240-1080"
    assert 1.0 <= cfg["camera"]["fov_deg"][0] <= 12 and 1.0 <= cfg["camera"]["fov_deg"][1] <= 12, "FOV 1-12°"
    assert 30 <= cfg["camera"]["fps"] <= 60, "Camera update Rate 30-60 Hz (min 30, spec §5)"
    assert cfg["camera"]["initial_position"] in ("centre", "center", "user-defined", "user_defined"), "Initial Camera Position"
    # allow pan/tilt within world
    assert 1 <= cfg["camera"]["max_pan_speed"] <= 15, "Max Pan 1-15 °/s (nominal 5-10)"
    assert 1 <= cfg["camera"]["max_tilt_speed"] <= 15, "Max Tilt 1-15 °/s (nominal 5-10)"
    # Update Interval derived from fps, but allow explicit
    assert 20 <= cfg["camera"].get("update_interval_hz", cfg["camera"]["fps"]) <= 60, "Update Interval ≥20 Hz"

    # -- Target Parameters --
    assert cfg["target"]["type"] in ("beacon_spot", "beacon", "spot", "point", "extended", "custom"), "Target type must be beacon_spot|point|extended|custom"
    assert 1 <= cfg["target"]["count"] <= 5, "Number of Targets 1-5 (1 mandatory)"
    assert cfg["target"]["shape"] in ("square", "circle", "gaussian", "cross", "user-defined", "user_defined"), "Shape square default + user-defined"
    assert 5 <= cfg["target"]["size"] <= 20, "Target Size 5-20 px"
    # initial pos None=Random or [x,y]
    ip = cfg["target"]["initial_pos"]
    if ip is not None:
        assert len(ip) == 2 and 0 <= ip[0] <= w and 0 <= ip[1] <= h, "Initial Target within world"
    assert cfg["target"]["trajectory"] in ("straight","circular","figure_eight","figure-eight","random","spiral","sinusoidal","user-defined","user_defined"), "Motion"
    assert 0 <= cfg["target"]["speed_px_per_frame"] <= 20, "target speed 0-20"
    assert 50 <= cfg["target"]["radius"] <= 800, "radius 50-800"
    assert cfg["target"]["count"] >= 1

    # -- Disturbances --
    assert 0 <= cfg["noise"].get("gaussian_std",0) <= 20, "Max Std Dev 20 px (Gaussian σ)"
    assert 0 <= cfg["noise"].get("salt_pepper_prob",0) <= 0.15, "S&P ~10% (0.10) max 0.15"
    # poisson is boolean
    assert 0 <= cfg["camera"]["jitter_px"] <= 20, "Max Camera Jitter ±20 px/frame"
    assert cfg["atmosphere"]["type"] in ("clear","haze","fog","rain","low_light"), "Atmospheric Clear/Haze/Fog/Rain/Low light"
    assert 0 <= cfg["atmosphere"].get("strength",0) <= 1, "atmo strength 0-1"
    assert cfg["platform"]["type"] in ("none","linear","circular","random","spiral","figure_of_8","figure_8","figure-of-8","spiral"), "Platform Linear def + Circular/Random/Spiral/Figure_8"
    assert 0 <= cfg["platform"].get("speed_px_per_frame",0) <= 20, "Platform ±20 px/frame"

    # --- AI ---
    if "ai" in cfg:
        ai = cfg["ai"]
        assert isinstance(ai.get("enabled", False), bool), "ai.enabled must be bool"
        assert 32 <= int(ai.get("patch_size", 64)) <= 128, "ai patch_size 32-128"
        assert 10 <= int(ai.get("sequence_length", 25)) <= 50, "ai sequence_length 10-50"
        thr = ai.get("thresholds", {})
        if thr:
            assert 0.5 <= float(thr.get("primary_threshold", 0.85)) <= 0.99
            assert 0.5 <= float(thr.get("decoy_threshold", 0.85)) <= 0.99
            assert 1 <= int(thr.get("confirmation_frames", 5)) <= 15
            assert 0.0 <= float(thr.get("unknown_low", 0.45)) < float(thr.get("unknown_high", 0.85)) <= 1.0
        w = ai.get("weights", None)
        if w:
            s = float(w.get("appearance", 0.20)) + float(w.get("motion", 0.20)) + float(w.get("temporal", 0.20)) + float(w.get("signature", 0.25)) + float(w.get("estimator", 0.15))
            assert abs(s - 1.0) < 1e-6, f"ai.weights must sum to 1.0 (got {s})"

    # environment brightness etc already validated elsewhere
    return cfg
