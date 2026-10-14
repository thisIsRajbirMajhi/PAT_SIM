CONTROLLER_DEFAULTS = {
    "kp_pan": 1.2,
    "kp_tilt": 1.2,
    "ki": 0.05,
    "kd": 0.15,
    "deadzone_px": 2.0,
    "integral_limit": 8.0,
    "feedforward_gain": 0.0,
    # Smart-search params (single source of truth lives in
    # pipeline/state/search_policy.py::SEARCH_DEFAULTS; mirrored here so
    # Control Deck / YAML overrides validate without extra plumbing).
    "search_angle_step": 0.45,
    "search_radius_step": 0.09,
    "search_radius_max": 4.5,
    "search_rate_scale": 0.85,
    "spiral_phase_s": 3.0,
    "raster_pan_scale": 0.9,
    "raster_tilt_scale": 0.35,
    "stare_rate_scale": 0.3,
    "intercept_gain": 2.0,
    "intercept_lead_s": 0.3,
    "unc_scale": 0.6,
    "unc_max_boost": 2.5,
    "fast_vel_deg_s": 1.0,
    "give_up_frames": 600,
}
