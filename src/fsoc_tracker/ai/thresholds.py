"""
Threshold management — Plan §9.2 Steps 8-9 / Prompt Phase 5-6.

Three operating regions:
    primary_prob >= 0.85  → eligible for PRIMARY_CONFIRMED (after N frames)
    decoy_prob   >= 0.85  → REJECT track
    otherwise             → UNKNOWN / continue observing

Thresholds are tunable via configs/model_thresholds.yaml and
calibrated on the validation set (calibration.py).
"""
from __future__ import annotations

from dataclasses import dataclass
from .types import IdentityState


@dataclass
class ThresholdConfig:
    """Mirrors model_thresholds.yaml (with defaults from Plan §6)."""
    primary_threshold: float = 0.85
    decoy_threshold: float = 0.85
    confirmation_frames: int = 5
    unknown_low: float = 0.45
    unknown_high: float = 0.85
    # optional per-stage weights (Plan §6 IdentityScore)
    w_appearance: float = 0.20
    w_motion: float = 0.20
    w_temporal: float = 0.20
    w_signature: float = 0.25
    w_estimator: float = 0.15

    def validate(self) -> None:
        assert 0.5 <= self.primary_threshold <= 0.99
        assert 0.5 <= self.decoy_threshold <= 0.99
        assert 1 <= self.confirmation_frames <= 15
        assert 0.0 <= self.unknown_low < self.unknown_high <= 1.0
        w_sum = self.w_appearance + self.w_motion + self.w_temporal + self.w_signature + self.w_estimator
        assert abs(w_sum - 1.0) < 1e-6, f"identity weights must sum to 1.0 (got {w_sum})"


def decide_identity(primary_p: float, decoy_p: float, unknown_p: float, cfg: ThresholdConfig) -> IdentityState:
    """Single-frame region decision (before temporal confirmation)."""
    if primary_p >= cfg.primary_threshold:
        return IdentityState.CANDIDATE_FOUND  # caller promotes to PRIMARY_CONFIRMED after N frames
    if decoy_p >= cfg.decoy_threshold:
        return IdentityState.CANDIDATE_FOUND  # caller promotes to DECOY_CONFIRMED after N frames
    if max(primary_p, decoy_p, unknown_p) < 0.55:
        return IdentityState.UNKNOWN
    return IdentityState.IDENTITY_CHECKING


def is_valid_threshold_dict(d: dict) -> bool:
    try:
        ThresholdConfig(**{k: d[k] for k in ThresholdConfig.__dataclass_fields__ if k in d}).validate()
        return True
    except Exception:
        return False
