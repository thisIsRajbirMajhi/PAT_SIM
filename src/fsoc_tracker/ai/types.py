"""
AI type contracts — Phase 1 (Prompt §5 / Plan §6-7).

These are the canonical data contracts for the AI subsystem.
They are intentionally separate from common.types to keep AI
dependencies isolated; conversion helpers go in features.py.

Ground-truth fields are NEVER present here — evaluator only.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Tuple, List, Dict, Any
import numpy as np


class CandidateClass(str, Enum):
    """Per-patch detection class (Plan §5)."""
    BEACON_LIKE = "BEACON_LIKE"
    DECOY_LIKE = "DECOY_LIKE"
    NOISE = "NOISE"
    UNKNOWN = "UNKNOWN"


class IdentityClass(str, Enum):
    """Track-level identity (Plan §6)."""
    PRIMARY = "PRIMARY"
    DECOY = "DECOY"
    UNKNOWN = "UNKNOWN"


class IdentityState(str, Enum):
    """
    Identity state machine (Plan §7).
    Separate from TrackingState (common.enums) — this governs
    whether camera control is allowed.
    """
    SEARCHING = "SEARCHING"
    CANDIDATE_FOUND = "CANDIDATE_FOUND"
    IDENTITY_CHECKING = "IDENTITY_CHECKING"
    PRIMARY_CONFIRMED = "PRIMARY_CONFIRMED"
    DECOY_CONFIRMED = "DECOY_CONFIRMED"
    UNKNOWN = "UNKNOWN"
    TARGET_LOST = "TARGET_LOST"


@dataclass
class Candidate:
    """
    One blob candidate from classical pipeline (Plan §5).
    Mirrors Detection but carries full feature set for AI.
    """
    candidate_id: int
    centroid_px: Tuple[float, float]
    bbox: Tuple[int, int, int, int]  # x,y,w,h
    area: float
    width: int
    height: int
    aspect_ratio: float
    brightness: float       # mean intensity 0-255
    peak_intensity: float
    local_contrast: float
    compactness: float      # area / bbox_area
    distance_from_prediction: float
    patch: Optional[np.ndarray] = None  # 64x64 grayscale, normalized 0-1
    # filled by Stage-1 classifier:
    beacon_probability: float = 0.0
    detection_class: CandidateClass = CandidateClass.UNKNOWN
    measurement_quality: float = 0.0
    appearance_embedding: Optional[np.ndarray] = None  # 128-d


@dataclass
class IdentityEvidence:
    """Evidence breakdown for explainability (Plan §15-16)."""
    appearance_score: float = 0.0
    motion_score: float = 0.0
    temporal_score: float = 0.0
    optical_signature_score: float = 0.0
    estimator_consistency_score: float = 0.0
    # signature sub-scores
    blink_correlation: float = 0.0
    freq_error_hz: float = 0.0
    shape_stability: float = 0.0
    innovation_sigma: float = 0.0
    reasons: List[str] = field(default_factory=list)  # e.g. "✓ Correct blink pattern"


@dataclass
class IdentityResult:
    """
    Per-track identity decision (Plan §6 / Prompt §5).
    Consumed by the state machine, not the controller directly.
    """
    track_id: int
    primary_probability: float
    decoy_probability: float
    unknown_probability: float
    identity_state: IdentityState
    measurement_quality: float
    evidence: IdentityEvidence = field(default_factory=IdentityEvidence)
    model_version: str = "none"
    # backward-compat alias used by training pipeline:
    @property
    def signature_score(self) -> float:
        return self.evidence.optical_signature_score

    @property
    def motion_score(self) -> float:
        return self.evidence.motion_score

    @property
    def appearance_score(self) -> float:
        return self.evidence.appearance_score


@dataclass
class ModelMetadata:
    """Saved alongside every training run (Plan §9.2)."""
    model_name: str
    version: str
    config_snapshot: Dict[str, Any] = field(default_factory=dict)
    random_seed: int = 42
    data_version: str = "v0"
    train_metrics: Dict[str, float] = field(default_factory=dict)
    val_metrics: Dict[str, float] = field(default_factory=dict)
    thresholds: Dict[str, float] = field(default_factory=dict)
    export_format: str = "onnx"  # or "tflite" / "pt"
    fps_profile: Dict[str, float] = field(default_factory=dict)


@dataclass
class AIInferenceResult:
    """
    Combined stage-1 + stage-2 result for a single frame.
    The pipeline emits one of these per candidate.
    """
    candidate: Candidate
    identity: Optional[IdentityResult] = None
    latency_ms: float = 0.0
    fallback_triggered: bool = False
    error: Optional[str] = None


@dataclass
class TrackState:
    """
    Minimal per-track history kept by the multi-target manager
    (Plan §6). Stored outside EKF/IMM — one entry per candidate_id.
    """
    track_id: int
    age: int = 0  # frames since creation
    missed_frames: int = 0
    last_seen_frame: int = -1
    position_history: List[Tuple[float, float]] = field(default_factory=list)
    velocity_history: List[Tuple[float, float]] = field(default_factory=list)
    brightness_history: List[float] = field(default_factory=list)
    size_history: List[float] = field(default_factory=list)  # area or width*height
    confidence_history: List[float] = field(default_factory=list)
    # EKF/IMM derived
    innovation_history: List[float] = field(default_factory=list)
    imm_probs_history: List[Tuple[float, float, float]] = field(default_factory=list)
    # signature
    blink_history: List[int] = field(default_factory=list)  # 0/1 per frame
    # identity
    identity_history: List[IdentityResult] = field(default_factory=list)
    current_identity: IdentityState = IdentityState.CANDIDATE_FOUND
    confirmed_frames: int = 0  # consecutive PRIMARY/CONFIRMED frames
    is_rejected_decoy: bool = False
