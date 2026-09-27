from enum import Enum


class NoiseType(str, Enum):
    GAUSSIAN = "gaussian"
    SALT_PEPPER = "salt_pepper"
    POISSON = "poisson"


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
