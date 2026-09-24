"""Tests for target trajectory generation (Sr.12)."""
import numpy as np
from fsoc_tracker.simulation.trajectories import StraightTrajectory, CircularTrajectory, FigureEightTrajectory, RandomTrajectory, make_trajectory
from fsoc_tracker.config.loader import load_config

def test_straight_trajectory():
    traj = StraightTrajectory(start=(500,500), angle_deg=0, speed_px_per_frame=3.0, world_size=(2000,2000))
    x0, y0 = traj.step(0)
    x1, y1 = traj.step(1)
    # Should move 3px in x direction (angle 0)
    assert abs((x1 - x0) - 3.0) < 1e-6
    assert abs(y1 - y0) < 1e-6

def test_circular_trajectory():
    traj = CircularTrajectory(center=(1000,1000), radius=100, speed_px_per_frame=3.0)
    # At t=0, should be at (1100,1000)
    x0, y0 = traj.step(0)
    assert abs(x0 - 1100) < 1e-6
    assert abs(y0 - 1000) < 1e-6
    # After some steps, should stay on circle radius 100
    for t in [10, 20, 30]:
        x, y = traj.step(t)
        r = np.hypot(x-1000, y-1000)
        assert abs(r - 100) < 1e-3

def test_figure_eight():
    traj = FigureEightTrajectory(center=(1000,1000), radius=100, speed_px_per_frame=3.0)
    x0, y0 = traj.step(0)
    # At t=0, should be at centre (sin0=0)
    assert abs(x0 - 1000) < 1e-6

def test_make_trajectory_factory():
    cfg = load_config()
    for name in ["straight", "circular", "figure_eight", "random", "spiral", "sinusoidal"]:
        cfg["target"]["trajectory"] = name
        traj = make_trajectory(cfg, seed=42)
        x, y = traj.step(0)
        assert 0 <= x <= cfg["world"]["width"]
        assert 0 <= y <= cfg["world"]["height"]
