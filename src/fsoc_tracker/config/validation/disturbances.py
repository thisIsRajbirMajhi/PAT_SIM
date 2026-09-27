"""Disturbance validation: noise + jitter + atmosphere + platform."""

from ...disturbances.platform.platform_motion import normalize_platform_type

_PLATFORM_TYPES = ("none", "linear", "circular", "random", "spiral", "figure_of_8")


def validate_disturbances(cfg):
    # -- Disturbances --
    assert 0 <= float(cfg["noise"].get("gaussian_std", 0)) <= 20, "Max Std Dev 20 px (Gaussian sigma)"
    assert 0 <= float(cfg["noise"].get("salt_pepper_prob", 0)) <= 0.15, "S&P ~10% (0.10) max 0.15"
    # poisson is boolean
    assert 0 <= float(cfg["camera"]["jitter_px"]) <= 20, "Max Camera Jitter +-20 px/frame"
    assert cfg["atmosphere"]["type"] in ("clear", "haze", "fog", "rain", "low_light"), \
        "Atmospheric Clear/Haze/Fog/Rain/Low light"
    assert 0 <= float(cfg["atmosphere"].get("strength", 0)) <= 1, "atmo strength 0-1"
    ptype = normalize_platform_type(cfg["platform"].get("type", "none"))
    assert ptype in _PLATFORM_TYPES, \
        "Platform Linear def + Circular/Random/Spiral/Figure_8 (aliases like figure_8 accepted)"
    assert 0 <= float(cfg["platform"].get("speed_px_per_frame", 0)) <= 20, "Platform +-20 px/frame"
    assert 0 <= float(cfg["platform"].get("amplitude", 0)) <= 1000, "Platform amplitude 0-1000"

    # environment brightness etc are validated in validate_environment (see validation/environment.py)
    return cfg
