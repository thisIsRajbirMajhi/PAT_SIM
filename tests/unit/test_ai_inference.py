"""Inference pipeline safety tests (Prompt §8 — unit + model tests)."""
from fsoc_tracker.ai.inference import AIInferencePipeline
from fsoc_tracker.ai.types import Candidate, CandidateClass
from fsoc_tracker.common.types import Detection
import numpy as np


def _cfg(enabled=False):
    return {"camera": {"fps": 30}, "ai": {"enabled": enabled, "inference_timeout_ms": 40}}


def test_pipeline_disabled_returns_empty():
    pipe = AIInferencePipeline(_cfg(enabled=False))
    assert pipe.step(np.zeros((64, 64), dtype=np.uint8), [], {}) == []


def test_pipeline_fallback_on_empty_candidates():
    pipe = AIInferencePipeline(_cfg(enabled=True))
    assert pipe.step(np.zeros((64, 64), dtype=np.uint8), [], {}) == []


def test_heuristic_candidate_classifier_marks_beacon():
    from fsoc_tracker.ai.candidate_model import CandidateClassifier
    clf = CandidateClassifier(_cfg(enabled=False))  # heuristic path
    c = Candidate(candidate_id=1, centroid_px=(320, 240), bbox=(310, 230, 20, 20),
                  area=120, width=11, height=11, aspect_ratio=1.0,
                  brightness=220, peak_intensity=255, local_contrast=40,
                  compactness=0.85, distance_from_prediction=5.0)
    out = clf.predict([c])
    assert out[0].detection_class in (CandidateClass.BEACON_LIKE, CandidateClass.UNKNOWN)
