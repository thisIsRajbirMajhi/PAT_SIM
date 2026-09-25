"""
fsoc_tracker.ai — AI-enhanced primary target identification package.

Architecture (Plan §9.1):
    Classical candidate generation
        ↓
    MobileNetV3-Small candidate classifier  (Stage 1 — per-patch)
        ↓
    GRU temporal identity classifier         (Stage 2 — per-track, 20-30 frames)
        ↓
    Identity state machine (PRIMARY / DECOY / UNKNOWN)
        ↓
    EKF-IMM (confidence-aware covariance + gating) → PID

All inference goes through inference.AIInferencePipeline which is
disabled by default. The existing perception/tracking/control pipeline
remains runnable with AI disabled (Prompt §4).

Public surface is re-exported here for convenience.
"""
from .types import (
    Candidate,
    CandidateClass,
    IdentityClass,
    IdentityState,
    IdentityEvidence,
    IdentityResult,
    ModelMetadata,
    AIInferenceResult,
    TrackState,
)

__all__ = [
    "Candidate",
    "CandidateClass",
    "IdentityClass",
    "IdentityState",
    "IdentityEvidence",
    "IdentityResult",
    "ModelMetadata",
    "AIInferenceResult",
    "TrackState",
]
