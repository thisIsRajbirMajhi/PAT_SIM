"""Target/Beacon module — single canonical home for ALL target-side code.

Layout:
    target/
        dynamics/     trajectories (straight/circular/figure-8/random/spiral/
                      sinusoidal/user-defined) + TargetManager (multi-target,
                      distractor seeds, position resolution) + visibility schedule
        appearance/   beacon shapes (square/circle/gaussian/cross/user-defined),
                      glow/core drawing + BeaconRenderer (blur + re-brighten)
        ground_truth/ evaluator-only GroundTruthFrame/GroundTruthLog
        config.py     TARGET defaults + get_target()/visibility/appearance helpers
        factory.py    make_trajectory()/make_manager()/make_renderer()

Shared-ownership rule: simulation/world.py owns the static environment base;
all target dynamics + appearance + visibility live here. World delegates to
TargetManager + BeaconRenderer and keeps thin mirrors (traj/trajectories/
target_count/all_world_pos/world_pos/size/shape/intensity/polygon) for compat.
"""
from .appearance import BeaconRenderer, draw_beacon, get_user_polygon
from .config import TARGET_DEFAULTS, get_target, get_visibility_schedule, target_appearance_changed
from .dynamics import (
    CircularTrajectory,
    FigureEightTrajectory,
    RandomTrajectory,
    SinusoidalTrajectory,
    SpiralTrajectory,
    StraightTrajectory,
    TargetManager,
    Trajectory,
    UserDefinedTrajectory,
    is_hidden,
    make_trajectory,
    target_dynamics_changed,
)
from .factory import make_manager, make_renderer
from .ground_truth import GroundTruthFrame, GroundTruthLog

__all__ = [
    # dynamics
    "Trajectory",
    "StraightTrajectory",
    "CircularTrajectory",
    "FigureEightTrajectory",
    "RandomTrajectory",
    "SpiralTrajectory",
    "SinusoidalTrajectory",
    "UserDefinedTrajectory",
    "make_trajectory",
    "TargetManager",
    "target_dynamics_changed",
    "is_hidden",
    "get_visibility_schedule",
    # appearance
    "BeaconRenderer",
    "draw_beacon",
    "get_user_polygon",
    # ground truth
    "GroundTruthFrame",
    "GroundTruthLog",
    # config / factory
    "TARGET_DEFAULTS",
    "get_target",
    "target_appearance_changed",
    "make_manager",
    "make_renderer",
]
