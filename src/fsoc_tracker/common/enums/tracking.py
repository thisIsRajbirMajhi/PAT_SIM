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
