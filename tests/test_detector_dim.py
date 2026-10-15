"""Dim-beacon detection (Task 1 RED test): E11-class frame must detect."""
import sys, os
_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO = os.path.dirname(_HERE)
sys.path.insert(0, os.path.join(_REPO, "src"))
import numpy as np
import cv2
from pat_pipeline.detection.detector import BeaconDetector
from pat_common.config.defaults import DEFAULT_CONFIG
import copy


def _cfg():
    return copy.deepcopy(DEFAULT_CONFIG)


def _dim_spot():
    # Discriminating dim beacon: uniform disc radius 5 at 100 on bg 11.
    # Old fixed floor 120 -> binary empty -> invalid.
    # New dim-aware floor 70 -> detected. Mirrors E11 (raw ~140,
    # blurred peak below 120) while keeping enough area to survive opening.
    img = np.full((480, 640), 11, dtype=np.uint8)
    yy, xx = np.ogrid[:480, :640]
    mask = (yy - 240) ** 2 + (xx - 320) ** 2 <= 25
    img[mask] = 100
    return img


def test_dim_beacon_detected():
    det = BeaconDetector(_cfg())
    d = det.detect(_dim_spot())
    assert d.valid, "dim beacon (peak_raw 140, peak_blur ~84, bg 11) must be detected"


def test_bright_beacon_still_detected():
    det = BeaconDetector(_cfg())
    img = np.full((480, 640), 21, dtype=np.uint8)
    img[240 - 5:240 + 5, 320 - 5:320 + 5] = 255
    d = det.detect(img)
    assert d.valid, "bright beacon must stay detected"
