"""Target/Beacon module — single canonical home for ALL target-side code.

Layout:
    target/
        dynamics/     trajectories (straight/circular/figure-8/random/spiral/
                      sinusoidal/user-defined) + TargetManager (multi-target,
                      distractor seeds, position resolution) + visibility schedule
        appearance/   beacon shapes (square/circle), glow/core drawing +
                      BeaconRenderer (halo blur + sharp core)
        ground_truth/ evaluator-only GroundTruthFrame/GroundTruthLog
        config.py     TARGET defaults + get_target()/visibility/appearance helpers
        factory.py    make_trajectory()/make_manager()/make_renderer()

Shared-ownership rule: simulation/world.py owns the static environment base;
all target dynamics + appearance + visibility live here. World delegates to
TargetManager + BeaconRenderer and keeps thin mirrors (traj/trajectories/
target_count/all_world_pos/world_pos/size/shape/intensity) for compat.
"""
from .appearance import (
    PEAK_INTENSITY,
    BeaconRenderer,
    atmosphere_intensity_scale,
    draw_beacon,
)
from .config import TARGET_DEFAULTS, get_target, get_visibility_schedule, target_appearance_changed
from .dynamics import (
    BLINK_DUTY,
    TRAJECTORY_TYPES,
    CircularTrajectory,
    FigureEightTrajectory,
    RandomTrajectory,
    SinusoidalTrajectory,
    SpiralTrajectory,
    StraightTrajectory,
    TargetManager,
    Trajectory,
    UserDefinedTrajectory,
    get_blink_rate,
    is_blink_off,
    is_hidden,
    make_trajectory,
    normalize_trajectory_type,
    target_dynamics_changed,
    validate_visibility_schedule,
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
    "TRAJECTORY_TYPES",
    "normalize_trajectory_type",
    "make_trajectory",
    "TargetManager",
    "target_dynamics_changed",
    "is_hidden",
    "is_blink_off",
    "get_blink_rate",
    "BLINK_DUTY",
    "get_visibility_schedule",
    "validate_visibility_schedule",
    # appearance
    "BeaconRenderer",
    "atmosphere_intensity_scale",
    "PEAK_INTENSITY",
    "draw_beacon",
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
