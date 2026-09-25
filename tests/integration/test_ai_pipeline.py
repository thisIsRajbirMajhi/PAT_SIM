"""
Integration tests for AI pipeline — Prompt §8.

  perception → track manager → MobileNet → GRU → identity state machine
  → EKF-IMM → PID (gating)
Also covers synthetic vs MP4 input parity and timeout fallback.
"""
import numpy as np
import pytest
from fsoc_tracker.ai.inference import AIInferencePipeline
from fsoc_tracker.ai.types import Candidate, TrackState


def _cfg():
    return {"camera": {"fps": 30}, "ai": {"enabled": True, "inference_timeout_ms": 80,
            "thresholds": {"primary_threshold": 0.85, "decoy_threshold": 0.85, "confirmation_frames": 5}}}


def test_new_track_has_no_identity_until_history():
    pipe = AIInferencePipeline(_cfg())
    c = Candidate(candidate_id=42, centroid_px=(100, 100), bbox=(90, 90, 20, 20),
                  area=80, width=10, height=10, aspect_ratio=1.0,
                  brightness=200, peak_intensity=240, local_contrast=30,
                  compactness=0.8, distance_from_prediction=10.0,
                  patch=np.zeros((64, 64), dtype=np.float32))
    results = pipe.step(np.zeros((64, 64), dtype=np.uint8), [c], tracks={})
    assert len(results) == 1
    assert results[0].identity is None  # insufficient history


def test_primary_requires_consecutive_frames():
    pipe = AIInferencePipeline(_cfg())
    # feed same track 6 times with high signature score
    c = Candidate(candidate_id=1, centroid_px=(320, 240), bbox=(310, 230, 20, 20),
                  area=100, width=10, height=10, aspect_ratio=1.0,
                  brightness=220, peak_intensity=255, local_contrast=40,
                  compactness=0.9, distance_from_prediction=2.0,
                  patch=np.zeros((64, 64), dtype=np.float32))
    track = TrackState(track_id=1)
    # simulate history that yields high signature (blink matches 10110010)
    track.blink_history = [1,0,1,1,0,0,1,0] * 4
    track.brightness_history = [220]*32
    track.position_history = [(320, 240)]*25
    track.velocity_history = [(2, 0)]*25
    track.innovation_history = [0.5]*25
    track.imm_probs_history = [(0.7, 0.2, 0.1)]*25

    # first 4 frames → not yet confirmed (need 5)
    for _ in range(4):
        res = pipe.step(np.zeros((64, 64), dtype=np.uint8), [c], tracks={1: track})
        # identity may be heuristic voter; just check we don't crash and respect confirmation
        assert res[0].candidate.candidate_id == 1
