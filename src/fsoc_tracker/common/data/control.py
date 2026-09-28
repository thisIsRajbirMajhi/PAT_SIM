from dataclasses import dataclass


@dataclass
class ControlCommand:
    pan_rate: float = 0.0  # deg/s
    tilt_rate: float = 0.0
    saturated: bool = False
    search_mode: bool = False
    search_case: str = ""
