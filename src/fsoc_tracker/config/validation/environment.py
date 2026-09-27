"""Environment validation: background gradient + texture + stars + vignetting + brightness."""


def validate_environment(cfg):
    env = cfg.get("environment", {})
    # Gradient
    assert env.get("gradient_type", "linear") in ("linear", "radial", "diagonal"), \
        "gradient_type must be linear|radial|diagonal"
    assert 0 <= int(env.get("gradient_top", 22)) <= 80, "gradient_top 0-80"
    assert 0 <= int(env.get("gradient_bottom", 38)) <= 80, "gradient_bottom 0-80"
    assert 0 <= float(env.get("gradient_angle", 90)) <= 360, "gradient_angle 0-360"
    # Texture
    assert 0 <= int(env.get("texture_strength", 5)) <= 20, "texture_strength 0-20"
    # Stars
    assert 0 <= float(env.get("stars_density", 0.0)) <= 0.006, "stars_density 0-0.006"
    assert 0 <= int(env.get("stars_brightness", 185)) <= 255, "stars_brightness 0-255"
    assert 0 <= int(env.get("stars_min_mag", 90)) <= 255, "stars_min_mag 0-255"
    assert 0 <= int(env.get("stars_max_mag", 90)) <= 255, "stars_max_mag 0-255"
    assert int(env.get("stars_min_mag", 90)) <= int(env.get("stars_max_mag", 255)), \
        "stars_min_mag must be <= stars_max_mag"
    assert 0 <= int(env.get("stars_twinkle_amount", 6)) <= 30, "stars_twinkle_amount 0-30"
    assert 0 <= int(env.get("stars_seed", 1337)) <= 999999, "stars_seed 0-999999"
    assert 0 <= int(env.get("stars_max_count", 12000)) <= 50000, "stars_max_count 0-50000"
    # Vignetting
    assert 0 <= float(env.get("vignetting_strength", 0.0)) <= 0.95, "vignetting_strength 0-0.95"
    assert 0.05 <= float(env.get("vignetting_radius", 0.72)) <= 1.0, "vignetting_radius 0.05-1.0"
    assert 0.3 <= float(env.get("vignetting_falloff", 2.0)) <= 6.0, "vignetting_falloff 0.3-6.0"
    assert 0 <= float(env.get("vignetting_center_x", 0.5)) <= 1, "vignetting_center_x 0-1"
    assert 0 <= float(env.get("vignetting_center_y", 0.5)) <= 1, "vignetting_center_y 0-1"
    # Brightness
    assert 0.5 <= float(env.get("brightness_gain", 1.0)) <= 1.8, "brightness_gain 0.5-1.8"
    assert -40 <= float(env.get("brightness_offset", 0)) <= 40, "brightness_offset -40..40"
    return cfg
