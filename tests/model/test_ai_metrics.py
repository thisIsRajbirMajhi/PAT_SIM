"""Model-level metric tests — Prompt §8."""
import numpy as np
from fsoc_tracker.ai.evaluation.metrics import false_lock_rate, decoy_rejection_rate
from fsoc_tracker.ai.calibration import expected_calibration_error


def test_false_lock_rate_zero_when_no_primary_predicted():
    assert false_lock_rate(np.array([0,0,1]), np.array([0,0,0])) == 0.0


def test_ece_perfect_calibration_near_zero():
    # perfect: 3 samples, each predicted correctly with 0.95 confidence
    probs = np.array([[0.95, 0.05],[0.05, 0.95],[0.95, 0.05]])
    labels = np.array([0,1,0])
    ece = expected_calibration_error(probs, labels, n_bins=5)
    assert ece < 0.10
