"""Legacy compatibility: canonical implementation lives in pat_common.visibility."""
from pat_common.visibility import (
    BLINK_DUTY,
    get_blink_rate,
    get_visibility_schedule,
    is_blink_off,
    is_hidden,
    validate_visibility_schedule,
)

__all__ = [
    "BLINK_DUTY",
    "get_blink_rate",
    "get_visibility_schedule",
    "is_blink_off",
    "is_hidden",
    "validate_visibility_schedule",
]
