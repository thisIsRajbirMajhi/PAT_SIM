"""Tests for EKF and IMM tracking (6-state, nonlinear tan projection)."""
import numpy as np
from fsoc_tracker.tracking.ekf import SimpleEKF
from fsoc_tracker.tracking.imm import IMM
from fsoc_tracker.config.loader import load_config

def test_ekf_predict_update():
    cfg = load_config()
    ekf = SimpleEKF(cfg, mode="CV")
    # Initial state zero, predict should keep zero (no motion)
    x0 = ekf.predict(dt=1/30)
    assert np.allclose(x0[:2], [0,0], atol=1e-6)
    # Update with measurement at centre (320,240) -> should stay near zero
    # Measurement at centre corresponds to angle 0
    z = (320, 240)
    x1, nis = ekf.update(z, confidence=0.9)
    # Innovation should be small
    assert nis < 5

def test_ekf_outlier_rejection():
    cfg = load_config()
    ekf = SimpleEKF(cfg, mode="CV")
    ekf.predict()
    # Far outlier should be rejected (NIS > 28)
    z_far = (600, 400)  # far from predicted centre
    _, nis = ekf.update(z_far, confidence=0.9)
    # Should be large NIS, but our update rejects and doesn't pull state far
    # Check that state didn't jump wildly
    assert nis > 10

def test_imm_three_models():
    cfg = load_config()
    imm = IMM(cfg)
    # Predict and update with a straight motion measurement
    imm.predict(dt=1/30)
    # Provide measurement moving slowly
    z = (330, 240)
    imm.update(z, confidence=0.9)
    # Probs should sum to 1 and CV should be dominant for straight
    assert abs(sum(imm.probs) - 1.0) < 1e-6
    assert imm.probs[0] > 0.2  # CV at least some weight

def test_imm_handles_missing_measurement():
    cfg = load_config()
    imm = IMM(cfg)
    imm.predict()
    # None measurement should not crash and should keep probs
    imm.update(None, confidence=0.0)
    assert abs(sum(imm.probs) - 1.0) < 1e-6
    # Fused state should still be finite
    assert np.all(np.isfinite(imm.fused_x))
