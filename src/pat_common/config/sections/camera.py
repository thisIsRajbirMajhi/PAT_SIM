CAMERA_DEFAULTS = {
    "type": "monochrome",  # Camera Type: Monochrome, Focal Plane Array (default) | optional Colour
    "resolution": [640, 480],  # Camera Resolution: 640x480 (default) | optional 320-1920
    "fov_deg": [4.0, 3.0],  # Field of View: user-defined, default 4°×3°, range 1-12°
    "fps": 30.0,  # Frame Rate: 30 Hz min, range 20-60 Hz
    "initial_position": "centre",  # Initial Camera Position: Centre (default) | user-defined
    "initial_pan": 0.0,  # deg, used when initial_position == "user-defined"
    "initial_tilt": 0.0,
    "max_pan_speed": 5.0,  # Maximum Pan Speed: 5-10 °/s, default 5 °/s
    "max_tilt_speed": 5.0,  # Maximum Tilt Speed: 5-10 °/s, default 5 °/s
    "update_interval_hz": 30.0,  # Update Rate: ≥20 Hz, default 30 Hz
    "jitter_px": 0.0,  # ±20 px/frame max
}
