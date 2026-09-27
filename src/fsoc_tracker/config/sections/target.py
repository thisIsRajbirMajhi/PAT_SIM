TARGET_DEFAULTS = {
    "type": "beacon_spot",  # Target Type: Beacon Spot
    "count": 1,  # Target Count: 1 mandatory, 1-5 optional
    "shape": "square",  # Target Shape: square (default) | circle
    "size": 10,  # Target Size: 5-20 px, default 10×10
    "initial_pos": None,  # Initial Target Location: user-defined or Random (default)
    "initial_mode": "random",  # helper: random | centre | user-defined
    "trajectory": "circular",  # Motion: straight, circular, figure-eight, random + spiral, sinusoidal, user-defined
    "speed_px_per_frame": 2.8,  # px/frame
    "blink_rate_hz": 0.0,  # beacon modulation: 0 = steady on, else square-wave blink rate
    "visibility_schedule": None,  # optional [[start_s, end_s, state], ...]
}
