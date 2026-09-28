"""Target validation."""
from ...target.dynamics.trajectories import TRAJECTORY_TYPES, normalize_trajectory_type
from ...target.dynamics.visibility import validate_visibility_schedule


def validate_target(cfg):
    w, h = cfg["world"]["width"], cfg["world"]["height"]
    tgt = cfg.get("target", {})
    # -- Target Parameters --
    assert tgt.get("type", "beacon_spot") in ("beacon_spot", "beacon", "spot"), "Beacon Spot"
    assert 1 <= int(tgt.get("count", 1)) <= 5, "Number of Targets 1-5 (1 mandatory)"
    assert tgt.get("shape", "square") in ("square", "circle", "diamond", "cross", "triangle", "custom"), \
        "Shape square|circle|diamond|cross|triangle|custom"
    # custom polygon: list of [dx,dy] offsets (3..16 points, within +-20px)
    if tgt.get("shape") == "custom" or tgt.get("custom_polygon"):
        poly = tgt.get("custom_polygon")
        if poly is not None:
            assert isinstance(poly, (list, tuple)) and 3 <= len(poly) <= 16, "custom_polygon needs 3-16 points"
            for pt in poly:
                assert isinstance(pt, (list, tuple)) and len(pt) == 2, "custom_polygon points are [dx,dy]"
                assert -20 <= float(pt[0]) <= 20 and -20 <= float(pt[1]) <= 20, "custom_polygon within +-20px"
    assert 5 <= int(tgt.get("size", 10)) <= 20, "Target Size 5-20 px"
    assert 0 <= int(tgt.get("intensity", 255)) <= 255, "Target intensity 0-255"
    # initial pos None=Random or [x,y]
    ip = tgt.get("initial_pos")
    if ip is not None:
        assert len(ip) == 2 and 0 <= ip[0] <= w and 0 <= ip[1] <= h, "Initial Target within world"
    assert tgt.get("initial_mode", "random") in ("random", "centre", "center",
                                                 "user-defined", "user_defined"), \
        "Initial mode random|centre|user-defined"
    traj = normalize_trajectory_type(tgt.get("trajectory", "circular"))
    assert traj in TRAJECTORY_TYPES, f"Motion must be one of {TRAJECTORY_TYPES}"
    # per-target trajectories / distractor motion (Sr.8 multi-target independence)
    if tgt.get("trajectories") is not None:
        assert isinstance(tgt["trajectories"], (list, tuple)), "trajectories must be a list"
        assert len(tgt["trajectories"]) == int(tgt.get("count", 1)), "trajectories length must equal count"
        for t in tgt["trajectories"]:
            if t is None:
                continue
            assert normalize_trajectory_type(t) in TRAJECTORY_TYPES, f"trajectories entry {t!r} invalid"
    if tgt.get("distractor_trajectory"):
        assert normalize_trajectory_type(tgt["distractor_trajectory"]) in TRAJECTORY_TYPES, \
            f"distractor_trajectory invalid"
    if tgt.get("speeds") is not None:
        assert isinstance(tgt["speeds"], (list, tuple)), "speeds must be a list"
        assert len(tgt["speeds"]) == int(tgt.get("count", 1)), "speeds length must equal count"
        for s in tgt["speeds"]:
            if s is None:
                continue
            assert 0 <= float(s) <= 20, "per-target speed 0-20"
    assert 0 <= float(tgt.get("speed_px_per_frame", 0)) <= 20, "target speed 0-20"
    assert 0 <= float(tgt.get("blink_rate_hz", 0)) <= 50, "blink rate 0-50 Hz (0 = steady on)"
    csv_path = tgt.get("custom_trajectory_file") or tgt.get("custom_trajectory_path")
    if traj == "user-defined" and csv_path:
        import os
        assert os.path.exists(csv_path), f"custom trajectory file not found: {csv_path}"
    validate_visibility_schedule(tgt.get("visibility_schedule")
                                 or (cfg.get("visibility", {}) or {}).get("schedule"))
    assert int(tgt.get("count", 1)) >= 1
    return cfg
