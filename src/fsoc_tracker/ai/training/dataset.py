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

from dataclasses import dataclass, field
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

# Feature vector layout per sequence step (Plan §9.1 Stage 2):
#   pos(2) + vel(2) + brightness(1) + shape_stability(1) + blink(1)
#   + innovation(1) + IMM(3) = 11 motion/signal features
# The GRU input concatenates the 128-d CNN embedding first, then these 11.
SEQ_FEATURE_DIM = 11


@dataclass
class PatchSample:
    patch: np.ndarray  # (64,64) float32 0-1
    num_features: np.ndarray  # (9,)
    label: int  # CandidateClass id
    metadata: Dict = field(default_factory=dict)  # bbox, seed, scenario, etc.


@dataclass
class SequenceSample:
    sequence: np.ndarray  # (T, D) float32
    mask: np.ndarray  # (T,) 0/1 valid
    label: int  # IdentityClass id
    track_id: int
    metadata: Dict = field(default_factory=dict)


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


def _candidate_label(record: Dict) -> int:
    """Map a patch manifest label to CandidateClass id (UNKNOWN as fallback)."""
    label = str(record.get("label", "UNKNOWN"))
    if label in ("PRIMARY_TARGET", "BEACON_LIKE"):
        return CANDIDATE_CLASS_IDS[CandidateClass.BEACON_LIKE.value]
    if label in ("DECOY", "DECOY_LIKE"):
        return CANDIDATE_CLASS_IDS[CandidateClass.DECOY_LIKE.value]
    if label == "NOISE":
        return CANDIDATE_CLASS_IDS[CandidateClass.NOISE.value]
    return CANDIDATE_CLASS_IDS[CandidateClass.UNKNOWN.value]


def _numeric_feature_vector(record: Dict) -> np.ndarray:
    """9-dim numerical features matching ai.features.numerical_features."""
    return np.array([
        float(record.get("brightness", 0.0)) / 255.0,
        float(record.get("peak_intensity", 0.0)) / 255.0,
        float(record.get("local_contrast", 0.0)) / 255.0,
        float(record.get("area", 0.0)) / 900.0,
        float(record.get("width", 0)) / 64.0,
        float(record.get("height", 0)) / 64.0,
        min(float(record.get("aspect_ratio", 1.0)) / 3.5, 1.0),
        float(record.get("compactness", 0.0)),
        min(float(record.get("distance_from_prediction", 0.0)) / 400.0, 1.0),
    ], dtype=np.float32)


class CandidatePatchDataset:
    """
    Loads patches from {split}.jsonl manifests + patches/*.npy files.
    Returns (patch, num_features, label) tensors ready for Stage-1 training.
    """

    def __init__(self, root: Path, split: str, augment: bool = False, seed: int = 42):
        self.root = Path(root)
        self.split = split
        self.augment = augment
        self.rng = np.random.default_rng(seed)
        manifest = self.root / "candidate_patches" / f"{split}.jsonl"
        self.records: List[Dict] = []
        if manifest.exists():
            with open(manifest) as f:
                for line in f:
                    if line.strip():
                        self.records.append(json.loads(line))
        # class weights for imbalance (noise/decoys may outnumber primary)
        counts = np.zeros(len(CandidateClass), dtype=np.float64)
        for r in self.records:
            counts[_candidate_label(r)] += 1.0
        total = max(counts.sum(), 1.0)
        # inverse-frequency, normalized to mean 1
        self.class_weights = np.ones(len(CandidateClass), dtype=np.float32)
        nz = counts > 0
        if nz.any():
            self.class_weights[nz] = (total / (len(CandidateClass) * counts[nz])).astype(np.float32)

    def __len__(self) -> int:
        return len(self.records)

    def _load_patch(self, record: Dict) -> np.ndarray:
        from ..features import PATCH_SIZE
        rel = record.get("patch_file", "")
        path = self.root / "candidate_patches" / rel
        if path.exists():
            patch = np.load(str(path)).astype(np.float32)
            if patch.ndim == 3 and patch.shape[0] in (1, 3):
                patch = patch[0] if patch.shape[0] == 1 else patch.mean(axis=0)
            if patch.shape != (PATCH_SIZE, PATCH_SIZE):
                import cv2
                patch = cv2.resize(patch, (PATCH_SIZE, PATCH_SIZE))
            patch = np.clip(patch, 0, 1)
            # per-patch standardization — preserves local contrast (identity
            # evidence, Plan §9.2 Step 3) while normalizing background level
            mu = float(patch.mean())
            sd = float(patch.std())
            if sd > 1e-6:
                patch = np.clip((patch - mu) / (sd * 4.0) * 0.5 + 0.5, 0, 1)
            return patch
        return np.zeros((PATCH_SIZE, PATCH_SIZE), dtype=np.float32)

    def __getitem__(self, idx: int) -> Tuple[np.ndarray, np.ndarray, int]:
        r = self.records[idx]
        patch = self._load_patch(r)
        if self.augment:
            from .augmentations import augment_patch
            patch = augment_patch(patch, self.rng)
        num = _numeric_feature_vector(r)
        label = _candidate_label(r)
        return patch, num, label

    def iter_batches(self, batch_size: int = 64, shuffle: bool = True):
        """Yield (patches (B,1,64,64), features (B,9), labels (B,)) numpy batches."""
        idxs = np.arange(len(self.records))
        if shuffle:
            self.rng.shuffle(idxs)
        for start in range(0, len(idxs), batch_size):
            batch_idx = idxs[start:start + batch_size]
            patches, nums, labels = [], [], []
            for i in batch_idx:
                p, n, l = self.__getitem__(int(i))
                patches.append(p)
                nums.append(n)
                labels.append(l)
            yield (
                np.stack(patches)[:, None, :, :].astype(np.float32),
                np.stack(nums).astype(np.float32),
                np.array(labels, dtype=np.int64),
            )


def build_sequence_from_track(track_dict: Dict, seq_len: int = 25) -> Optional[SequenceSample]:
    """
    Convert a serialized track dict (position/velocity/brightness/blink/
    innovation/imm histories) into a SequenceSample with a padded (T, 11)
    motion/signal matrix. Left-pads short tracks; returns None when the
    track has fewer than 2 usable observations.
    """
    pos = track_dict.get("position_history") or []
    if len(pos) < 2:
        return None
    vel = track_dict.get("velocity_history") or []
    br = track_dict.get("brightness_history") or []
    size = track_dict.get("size_history") or []
    blink = track_dict.get("blink_history") or []
    innov = track_dict.get("innovation_history") or []
    imm = track_dict.get("imm_probs_history") or []

    n = len(pos)
    T = min(n, seq_len)
    pad = seq_len - T
    seq = np.zeros((seq_len, SEQ_FEATURE_DIM), dtype=np.float32)
    mask = np.zeros((seq_len,), dtype=np.float32)

    # shape stability: rolling std of size history (normalized)
    size_arr = np.array(size[:n], dtype=np.float32)
    for i in range(T):
        idx = n - T + i
        px, py = pos[idx]
        vx, vy = vel[idx] if idx < len(vel) else (0.0, 0.0)
        b = br[idx] if idx < len(br) else 0.0
        bl = blink[idx] if idx < len(blink) else 0
        inno = innov[idx] if idx < len(innov) else 0.0
        p = imm[idx] if idx < len(imm) else (0.33, 0.33, 0.34)
        # shape stability: std of sizes seen so far (scaled)
        if len(size_arr[: idx + 1]) > 1:
            shape_stab = float(np.clip(1.0 - np.std(size_arr[: idx + 1]) / 20.0, 0, 1))
        else:
            shape_stab = 1.0
        seq[pad + i] = [
            px / 640.0, py / 480.0,
            np.clip(vx / 20.0, -1, 1), np.clip(vy / 20.0, -1, 1),
            float(b) / 255.0,
            shape_stab,
            float(bl),
            float(inno) / 50.0,
            p[0], p[1], p[2],
        ]
        mask[pad + i] = 1.0

    return SequenceSample(
        sequence=seq,
        mask=mask,
        label=track_dict.get("label_id", IDENTITY_CLASS_IDS[IdentityClass.UNKNOWN.value]),
        track_id=int(track_dict.get("track_id", 0)),
        metadata=track_dict.get("metadata", {}),
    )


class TrackSequenceDataset:
    """
    Loads track sequences from track_sequences/*.npz files selected by
    {split}.jsonl manifests. Returns (sequence (T,11), mask (T,), label).
    """

    def __init__(self, root: Path, split: str):
        self.root = Path(root)
        self.split = split
        manifest = self.root / "track_sequences" / f"{split}.jsonl"
        self.records: List[Dict] = []
        if manifest.exists():
            with open(manifest) as f:
                for line in f:
                    if line.strip():
                        self.records.append(json.loads(line))
        counts = np.zeros(len(IdentityClass), dtype=np.float64)
        for r in self.records:
            counts[IDENTITY_CLASS_IDS.get(r.get("label", "UNKNOWN"), 2)] += 1.0
        total = max(counts.sum(), 1.0)
        self.class_weights = np.ones(len(IdentityClass), dtype=np.float32)
        nz = counts > 0
        if nz.any():
            self.class_weights[nz] = (total / (len(IdentityClass) * counts[nz])).astype(np.float32)

    def __len__(self) -> int:
        return len(self.records)

    def __getitem__(self, idx: int) -> Tuple[np.ndarray, np.ndarray, int]:
        r = self.records[idx]
        path = self.root / "track_sequences" / r["file"]
        if path.exists():
            data = np.load(str(path), allow_pickle=False)
            seq = data["sequence"].astype(np.float32)
            mask = data["mask"].astype(np.float32)
        else:
            from ..features import SEQ_LEN
            seq = np.zeros((SEQ_LEN, SEQ_FEATURE_DIM), dtype=np.float32)
            mask = np.zeros((SEQ_LEN,), dtype=np.float32)
        label = IDENTITY_CLASS_IDS.get(r.get("label", "UNKNOWN"), IDENTITY_CLASS_IDS[IdentityClass.UNKNOWN.value])
        return seq, mask, label

    def iter_batches(self, batch_size: int = 32, shuffle: bool = True, seed: int = 42):
        idxs = np.arange(len(self.records))
        rng = np.random.default_rng(seed)
        if shuffle:
            rng.shuffle(idxs)
        for start in range(0, len(idxs), batch_size):
            batch_idx = idxs[start:start + batch_size]
            seqs, masks, labels = [], [], []
            for i in batch_idx:
                s, m, l = self.__getitem__(int(i))
                seqs.append(s)
                masks.append(m)
                labels.append(l)
            yield (
                np.stack(seqs).astype(np.float32),
                np.stack(masks).astype(np.float32),
                np.array(labels, dtype=np.int64),
            )
