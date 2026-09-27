"""Disturbance validation: noise + jitter + atmosphere + platform (moved verbatim from schema.py)."""


def validate_disturbances(cfg):
    # -- Disturbances --
    assert 0 <= cfg["noise"].get("gaussian_std", 0) <= 20, "Max Std Dev 20 px (Gaussian σ)"
    assert 0 <= cfg["noise"].get("salt_pepper_prob", 0) <= 0.15, "S&P ~10% (0.10) max 0.15"
    # poisson is boolean
    assert 0 <= cfg["camera"]["jitter_px"] <= 20, "Max Camera Jitter ±20 px/frame"
    assert cfg["atmosphere"]["type"] in ("clear", "haze", "fog", "rain", "low_light"), "Atmospheric Clear/Haze/Fog/Rain/Low light"
    assert 0 <= cfg["atmosphere"].get("strength", 0) <= 1, "atmo strength 0-1"
    assert cfg["platform"]["type"] in ("none", "linear", "circular", "random", "spiral", "figure_of_8", "figure_8", "figure-of-8", "spiral"), "Platform Linear def + Circular/Random/Spiral/Figure_8"
    assert 0 <= cfg["platform"].get("speed_px_per_frame", 0) <= 20, "Platform ±20 px/frame"

    # environment brightness etc are validated in validate_environment (see validation/environment.py)
    return cfg
