"""Unit tests for AI types, features, signatures, thresholds (Prompt §8)."""
import numpy as np
from fsoc_tracker.ai.types import Candidate, CandidateClass, IdentityState
from fsoc_tracker.ai.features import extract_patch, PATCH_SIZE
from fsoc_tracker.ai.signatures import blink_correlation, SignatureConfig, signature_score
from fsoc_tracker.ai.thresholds import ThresholdConfig, decide_identity


def test_extract_patch_pads_border():
    img = np.zeros((480, 640), dtype=np.uint8)
    patch = extract_patch(img, (2, 2), size=PATCH_SIZE)
    assert patch.shape == (PATCH_SIZE, PATCH_SIZE)
    assert patch.dtype == np.float32


def test_blink_correlation_perfect():
    assert blink_correlation([1,0,1,1,0,0,1,0], "10110010") == 1.0


def test_thresholds_validate():
    cfg = ThresholdConfig()
    cfg.validate()


def test_decide_identity_unknown_band():
    cfg = ThresholdConfig(primary_threshold=0.85, decoy_threshold=0.85)
    # low confidence → UNKNOWN or IDENTITY_CHECKING, never blind PRIMARY
    s = decide_identity(0.50, 0.30, 0.40, cfg)
    assert s in (IdentityState.UNKNOWN, IdentityState.IDENTITY_CHECKING)
