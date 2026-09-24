# Functional Parameters and Specifications — limits & defaults per problem statement
# All ranges are enforced in Control Deck spin boxes and validated in schema.py

DEFAULT_CONFIG = {
    # --- Camera Parameters ---
    "world": {
        "width": 2000,        # Screen Size 2000x2000, optional 1000-4000
        "height": 2000,
        "background": 18,     # 0-60
    },
    "camera": {
        "type": "monochrome", # Camera Type: Monochrome, Focal Plane Array (default) | optional Colour
        "resolution": [640, 480], # Camera Resolution: 640x480 (default) | optional 320-1920
        "fov_deg": [4.0, 3.0], # Field of View: user-defined, default 4°×3°, range 1-12°
        "fps": 30.0,          # Frame Rate: 30 Hz min, range 20-60 Hz
        "initial_position": "centre", # Initial Camera Position: Centre (default) | user-defined
        "initial_pan": 0.0,   # deg, used when initial_position == "user-defined"
        "initial_tilt": 0.0,
        "max_pan_speed": 5.0, # Maximum Pan Speed: 5-10 °/s, default 5 °/s
        "max_tilt_speed": 5.0,# Maximum Tilt Speed: 5-10 °/s, default 5 °/s
        "update_interval_hz": 30.0, # Update Rate: ≥20 Hz, default 30 Hz
        "jitter_px": 0.0,     # ±20 px/frame max
    },
    # --- Target Parameters ---
    "target": {
        "type": "beacon_spot", # Target Type: Beacon Spot
        "count": 1,          # Target Count: 1 mandatory, 1-5 optional
        "shape": "square",   # Target Shape: Square (default) | circle, gaussian, cross
        "size": 10,          # Target Size: 5-20 px, default 10×10
        "initial_pos": None, # Initial Target Location: user-defined or Random (default)
        "initial_mode": "random", # helper: random | centre | user-defined
        "trajectory": "circular", # Motion: straight, circular, figure-eight, random + spiral, sinusoidal, user-defined
        "speed_px_per_frame": 2.8, # px/frame
        "angle_deg": 30.0,   # for straight
        "radius": 180.0,     # for circular/figure_8
        "intensity": 255,
    },
    "platform": {"type": "linear", "speed_px_per_frame": 0.0, "amplitude": 0.0},
    "noise": {
        "gaussian_std": 0.0,
        "salt_pepper_prob": 0.0,
        "poisson": False,
        "gaussian_enabled": False,
        "salt_pepper_enabled": False,
    },
    "atmosphere": {"type": "clear", "strength": 0.0},
    "environment": {
        "gradient_enabled": False,
        "gradient_type": "linear",
        "gradient_top": 22,
        "gradient_bottom": 38,
        "gradient_angle": 90,
        "stars_enabled": False,
        "stars_density": 0.0007,
        "stars_brightness": 185,
        "stars_min_mag": 90,
        "stars_max_mag": 255,
        "stars_twinkle": False,
        "stars_seed": 1337,
        "vignetting_enabled": False,
        "vignetting_strength": 0.42,
        "vignetting_radius": 0.72,
        "vignetting_falloff": 2.0,
        "vignetting_center_x": 0.5,
        "vignetting_center_y": 0.5,
        "brightness_gain": 1.0,
        "brightness_offset": 0,
    },
    "detector": {
        "threshold_k": 3.0,
        "min_area": 8,
        "max_area": 900,
        "blur_ksize": 3,
        "adaptive_block": 51,
        "adaptive_C": -5,
    },
    "tracker": {
        "process_noise": 0.8,
        "meas_noise": 4.0,
        "gate_sigma": 5.0,
        "lost_timeout_frames": 15,
        "reacq_timeout_frames": 30,
    },
    "controller": {
        "kp_pan": 1.2,
        "kp_tilt": 1.2,
        "ki": 0.05,
        "kd": 0.15,
        "deadzone_px": 2.0,
        "integral_limit": 8.0,
        "feedforward_gain": 0.0,
    },
    "experiment": {"duration_s": 30.0, "seed": 42, "input_mode": "SYNTHETIC", "video_path": ""},
}
# Limits reference (enforced in Control Deck & schema):
# World 1000-4000 (spec min 2000), default 2000
# Resolution W 320-1920 H 240-1080 default 640x480
# FOV 1-12° default 4x3
# FPS 20-60 default 30
# Size 5-20 default 10
# /14 Max Pan/Tilt 5-10 °/s default 5 (UI allows 1-15 for tuning but schema warns outside 5-10)
# Update Interval ≥20 Hz default 30
