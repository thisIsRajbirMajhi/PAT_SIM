"""Scene validation: world + camera (moved verbatim from schema.py)."""


def validate_scene(cfg):
    # -- Camera Parameters --
    w, h = cfg["world"]["width"], cfg["world"]["height"]
    assert 2000 <= w <= 4000 and 2000 <= h <= 4000, "Screen Size must be 2000-4000 (spec min 2000)"
    assert 0 <= cfg["world"].get("background", 18) <= 80, "background 0-80"
    assert cfg["camera"]["type"] in ("monochrome", "colour", "color"), "Camera Type must be monochrome|colour"
    assert 320 <= cfg["camera"]["resolution"][0] <= 1920 and 240 <= cfg["camera"]["resolution"][1] <= 1080, "Resolution 320-1920 x 240-1080"
    assert 1.0 <= cfg["camera"]["fov_deg"][0] <= 12 and 1.0 <= cfg["camera"]["fov_deg"][1] <= 12, "FOV 1-12°"
    assert 30 <= cfg["camera"]["fps"] <= 60, "Camera update Rate 30-60 Hz (min 30, spec §5)"
    assert cfg["camera"]["initial_position"] in ("centre", "center", "user-defined", "user_defined"), "Initial Camera Position"
    # allow pan/tilt within world
    assert 5 <= cfg["camera"]["max_pan_speed"] <= 15 or 1 <= cfg["camera"]["max_pan_speed"] <= 15, "Max Pan 5-10 °/s (UI 1-15 for tuning)"
    assert 5 <= cfg["camera"]["max_tilt_speed"] <= 15 or 1 <= cfg["camera"]["max_tilt_speed"] <= 15, "Max Tilt"
    # Update Interval derived from fps, but allow explicit
    assert 20 <= cfg["camera"].get("update_interval_hz", cfg["camera"]["fps"]) <= 60, "Update Interval ≥20 Hz"
    return cfg
