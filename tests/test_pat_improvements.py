import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))


def test_overlap_steps_cover_fov():
    from fsoc_tracker.pipeline.state.search_policy import overlap_search_steps
    a1, r1 = overlap_search_steps((640, 480), (4.0, 3.0), 0.3)
    assert 0.05 <= a1 <= 1.5 and 0.01 <= r1 <= 0.5
    a2, r2 = overlap_search_steps((640, 480), (1.0, 1.0), 0.3)
    assert 0.05 <= a2 <= 1.5 and 0.01 <= r2 <= 0.5


def test_tile_reverses_before_limit():
    from fsoc_tracker.config.loader import load_config
    from fsoc_tracker.camera.control.camera_controller import CameraController
    cfg = load_config()
    c = CameraController(cfg)
    d0 = c.raster_dir
    c.search_frames = c.spiral_phase_frames + c.sweep_frames + 1
    c._raster_rates()
    # entering a new sweep segment reverses the pan direction ...
    assert c.raster_dir == -d0
    c.search_frames += c.sweep_frames
    c._raster_rates()
    # ... and boustrophedon reverses again on the next segment (net zero
    # after two single-segment advances: -d0 then back to d0). NOTE: the
    # brief's verbatim `assert c.raster_dir == -d0` here is arithmetically
    # unsatisfiable with flip-per-segment ((sweep+1)//sweep == 1 then
    # (2*sweep+1)//sweep == 2 for any sweep >= 1, i.e. two flips); the
    # production toggle is kept correct instead of hacked to fit.
    assert c.raster_dir == d0
