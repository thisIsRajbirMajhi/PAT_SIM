from enum import Enum


class TrajectoryType(str, Enum):
    STRAIGHT = "straight"
    CIRCULAR = "circular"
    FIGURE_EIGHT = "figure_eight"
    RANDOM = "random"
    SPIRAL = "spiral"
    SINUSOIDAL = "sinusoidal"
