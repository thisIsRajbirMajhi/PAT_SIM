"""Tests for centroid calculation and detector scoring."""
import numpy as np
import cv2
from fsoc_tracker.perception.detector import BeaconDetector
from fsoc_tracker.config.loader import load_config

def test_centroid_on_synthetic_shape():
    # Create a simple beacon blob
    img = np.full((480,640), 20, dtype=np.uint8)
    # Draw 10x10 square at (100,100)
    cv2.rectangle(img, (95,95), (105,105), 255, -1)
    cfg = load_config()
    det = BeaconDetector(cfg)
    d = det.detect(img)
    assert d.valid
    # Centroid should be near (100,100)
    assert abs(d.centroid_px[0] - 100) < 1.5
    assert abs(d.centroid_px[1] - 100) < 1.5
    assert d.confidence > 0.5

def test_detector_rejects_small_noise():
    img = np.full((480,640), 20, dtype=np.uint8)
    # Single pixel noise
    img[100,100] = 255
    cfg = load_config()
    cfg["detector"]["min_area"] = 8
    det = BeaconDetector(cfg)
    d = det.detect(img)
    # Should be invalid due to area < min
    assert not d.valid

def test_detector_handles_colour_input():
    img_gray = np.full((480,640), 20, dtype=np.uint8)
    cv2.rectangle(img_gray, (200,200), (210,210), 255, -1)
    img_bgr = cv2.cvtColor(img_gray, cv2.COLOR_GRAY2BGR)
    cfg = load_config()
    det = BeaconDetector(cfg)
    d_gray = det.detect(img_gray)
    d_bgr = det.detect(img_bgr)
    assert d_gray.valid and d_bgr.valid
    # Centroids should be close
    assert abs(d_gray.centroid_px[0] - d_bgr.centroid_px[0]) < 1e-3
