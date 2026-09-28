"""Controller + smart-search validation: PID gains and search routing params."""


def _num(cfg, key, default=0.0):
    try:
        return float(cfg["controller"].get(key, default))
    except (TypeError, ValueError, KeyError, AttributeError):
        raise AssertionError(f"controller.{key} must be numeric")


def validate_controller(cfg):
    c = cfg.get("controller", {}) or {}
    assert 0.1 <= _num(cfg, "kp_pan", 1.2) <= 5.0, "kp_pan 0.1-5.0"
    assert 0.1 <= _num(cfg, "kp_tilt", 1.2) <= 5.0, "kp_tilt 0.1-5.0"
    assert 0.0 <= _num(cfg, "ki", 0.05) <= 1.0, "ki 0-1.0"
    assert 0.0 <= _num(cfg, "kd", 0.15) <= 2.0, "kd 0-2.0"
    assert 0.0 <= _num(cfg, "deadzone_px", 2.0) <= 20.0, "deadzone 0-20 px"
    assert 0.0 <= _num(cfg, "feedforward_gain", 0.0) <= 5.0, "feedforward 0-5"
    # smart-search routing params (single source of truth: search_policy.SEARCH_DEFAULTS)
    assert 0.05 <= _num(cfg, "search_angle_step", 0.45) <= 1.5, "search_angle_step 0.05-1.5 rad/tick"
    assert 0.01 <= _num(cfg, "search_radius_step", 0.09) <= 0.5, "search_radius_step 0.01-0.5"
    assert 1.0 <= _num(cfg, "search_radius_max", 4.5) <= 8.0, "search_radius_max 1-8 deg/s"
    assert 0.1 <= _num(cfg, "search_rate_scale", 0.85) <= 1.5, "search_rate_scale 0.1-1.5"
    assert 1.0 <= _num(cfg, "spiral_phase_s", 3.0) <= 10.0, "spiral_phase_s 1-10 s"
    assert 0.1 <= _num(cfg, "raster_pan_scale", 0.9) <= 1.0, "raster_pan_scale 0.1-1.0"
    assert 0.1 <= _num(cfg, "raster_tilt_scale", 0.35) <= 1.0, "raster_tilt_scale 0.1-1.0"
    assert 0.05 <= _num(cfg, "stare_rate_scale", 0.3) <= 1.0, "stare_rate_scale 0.05-1.0"
    assert 0.5 <= _num(cfg, "intercept_gain", 2.0) <= 5.0, "intercept_gain 0.5-5.0"
    assert 0.0 <= _num(cfg, "intercept_lead_s", 0.3) <= 1.0, "intercept_lead_s 0-1 s"
    assert 0.0 <= _num(cfg, "unc_scale", 0.6) <= 2.0, "unc_scale 0-2"
    assert 1.0 <= _num(cfg, "unc_max_boost", 2.5) <= 4.0, "unc_max_boost 1-4"
    assert 0.2 <= _num(cfg, "fast_vel_deg_s", 1.0) <= 5.0, "fast_vel_deg_s 0.2-5"
    assert 60 <= _num(cfg, "give_up_frames", 600) <= 3600, "give_up_frames 60-3600"
    assert c is not None
    return cfg
