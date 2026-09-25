"""
Dataset builders — Plan §9.2 Steps 1-5 / Prompt Phase 3.

Two datasets:
  CandidatePatchDataset   — 64×64 patches + numerical features → {BEACON,DECOY,NOISE,UNKNOWN}
  TrackSequenceDataset    — (T, D) sequences per track → {PRIMARY,DECOY,UNKNOWN}

Both split by scenario seed (no adjacent-frame leakage):
    train seeds 1-70, val 71-85, test 86-100

No ground truth is exposed to the model at inference — labels are
only used here to build supervised targets.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import List, Dict, Tuple, Optional
import json
import numpy as np

from ..types import CandidateClass, IdentityClass

# Canonical class ids (keep stable across exports)
CANDIDATE_CLASS_IDS = {c.value: i for i, c in enumerate(CandidateClass)}
IDENTITY_CLASS_IDS = {c.value: i for i, c in enumerate(IdentityClass)}

TRAIN_SEEDS = range(1, 71)
VAL_SEEDS = range(71, 86)
TEST_SEEDS = range(86, 101)


@dataclass
class PatchSample:
    patch: np.ndarray  # (64,64) float32 0-1
    num_features: np.ndarray  # (9,)
    label: int  # CandidateClass id
    metadata: Dict  # bbox, seed, scenario, etc.


@dataclass
class SequenceSample:
    sequence: np.ndarray  # (T, D) float32
    mask: np.ndarray  # (T,) 0/1 valid
    label: int  # IdentityClass id
    track_id: int
    metadata: Dict


def split_by_seed(seed: int) -> str:
    if seed in TRAIN_SEEDS:
        return "train"
    if seed in VAL_SEEDS:
        return "val"
    if seed in TEST_SEEDS:
        return "test"
    # out-of-range seeds go to train by default
    return "train"


def load_patch_manifest(root: Path) -> List[Dict]:
    """
    Load all patch manifests under data/datasets/candidate_patches/.
    Each manifest is a JSONL with one sample per line.
    """
    manifests = list((root / "candidate_patches").glob("*.jsonl"))
    samples = []
    for m in manifests:
        with open(m) as f:
            for line in f:
                if line.strip():
                    samples.append(json.loads(line))
    return samples


def build_sequence_from_track(track_dict: Dict, seq_len: int = 25) -> Optional[SequenceSample]:
    """
    Convert a serialized TrackState dict (from generated scenarios)
    into a SequenceSample. Pads short tracks on the left.
    """
    # Placeholder — full logic in scripts/generate_training_data.py;
    # this helper is used by train_identity.py at load time.
    return None
