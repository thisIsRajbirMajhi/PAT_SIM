"""Circular orbits must stay inside the world (Task 2 RED test)."""
import sys, os
_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO = os.path.dirname(_HERE)
sys.path.insert(0, os.path.join(_REPO, "src"))
from fsoc_tracker.target.dynamics.trajectories import CircularTrajectory


def test_circular_corner_orbit_stays_in_world():
    ws = (2000, 2000)
    for corner in [(300, 300), (1700, 300), (300, 1700), (1700, 1700)]:
        traj = CircularTrajectory(center=corner, radius=400,
                                  speed_px_per_frame=3.0, world_size=ws)
        for t in range(0, 1200, 5):
            x, y = traj.step(t)
            assert 0 <= x <= ws[0], f"corner {corner} t={t}: x={x} outside world"
            assert 0 <= y <= ws[1], f"corner {corner} t={t}: y={y} outside world"
