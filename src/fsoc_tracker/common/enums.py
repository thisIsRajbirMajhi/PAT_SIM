from enum import Enum

class TrackingState(str, Enum):
    IDLE = "IDLE"
    SEARCHING = "SEARCHING"
    CANDIDATE = "CANDIDATE"
    ACQUIRING = "ACQUIRING"
    LOCKED = "LOCKED"
    TEMP_LOST = "TEMP_LOST"
    REACQUIRING = "REACQUIRING"
    FAILED = "FAILED"

class InputMode(str, Enum):
    SYNTHETIC = "SYNTHETIC"
    VIDEO = "VIDEO"

class NoiseType(str, Enum):
    GAUSSIAN = "gaussian"
    SALT_PEPPER = "salt_pepper"
    POISSON = "poisson"

class TrajectoryType(str, Enum):
    STRAIGHT = "straight"
    CIRCULAR = "circular"
    FIGURE_EIGHT = "figure_eight"
    RANDOM = "random"
    SPIRAL = "spiral"
    SINUSOIDAL = "sinusoidal"

class PlatformMotionType(str, Enum):
    NONE = "none"
    LINEAR = "linear"
    CIRCULAR = "circular"
    RANDOM = "random"

class AtmosphereType(str, Enum):
    CLEAR = "clear"
    HAZE = "haze"
    FOG = "fog"
    RAIN = "rain"
    LOW_LIGHT = "low_light"
