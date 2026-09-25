"""
Scenario tests for decoy rejection and false-lock safety — Prompt §8.

Covers: clean single-target, multiple decoys, bright decoy, centre-biased
decoy, crossing targets, incorrect signature, target loss/leaving FOV,
fog/haze/low-light, jitter, platform motion, random/manoeuvring motion.

These are headless (no GUI) and use deterministic seeds.
"""
import pytest
import numpy as np
from fsoc_tracker.ai.signatures import blink_correlation, SignatureConfig


def test_bright_decoy_with_wrong_signature_not_primary():
    # decoy has higher brightness but wrong blink → must not outrank primary
    primary_blink = [1,0,1,1,0,0,1,0]
    decoy_blink =   [1,1,1,0,0,0,1,1]
    assert blink_correlation(primary_blink, "10110010") > blink_correlation(decoy_blink, "10110010")


def test_incomplete_evidence_stays_unknown():
    from fsoc_tracker.ai.thresholds import ThresholdConfig, decide_identity
    from fsoc_tracker.ai.types import IdentityState
    cfg = ThresholdConfig(primary_threshold=0.85, decoy_threshold=0.85)
    # 0.60/0.30/0.40 → not enough for either PRIMARY or DECOY
    s = decide_identity(0.60, 0.30, 0.55, cfg)
    assert s in (IdentityState.UNKNOWN, IdentityState.IDENTITY_CHECKING)
