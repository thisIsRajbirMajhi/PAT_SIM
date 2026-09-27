"""Target validation (moved verbatim from schema.py)."""


def validate_target(cfg):
    w, h = cfg["world"]["width"], cfg["world"]["height"]
    # -- Target Parameters --
    assert cfg["target"]["type"] in ("beacon_spot", "beacon", "spot"), "Beacon Spot"
    assert 1 <= cfg["target"]["count"] <= 5, "Number of Targets 1-5 (1 mandatory)"
    assert cfg["target"]["shape"] in ("square", "circle", "gaussian", "cross", "user-defined", "user_defined"), "Shape square default + user-defined"
    assert 5 <= cfg["target"]["size"] <= 20, "Target Size 5-20 px"
    # initial pos None=Random or [x,y]
    ip = cfg["target"]["initial_pos"]
    if ip is not None:
        assert len(ip) == 2 and 0 <= ip[0] <= w and 0 <= ip[1] <= h, "Initial Target within world"
    assert cfg["target"]["trajectory"] in ("straight", "circular", "figure_eight", "figure-eight", "random", "spiral", "sinusoidal", "user-defined", "user_defined"), "Motion"
    assert 0 <= cfg["target"]["speed_px_per_frame"] <= 20, "target speed 0-20"
    assert 50 <= cfg["target"]["radius"] <= 800, "radius 50-800"
    assert cfg["target"]["count"] >= 1
    return cfg
