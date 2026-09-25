"""
Training logic for Stage-1 candidate classifier — Prompt Phase 4.

Extracted as a library module so scripts/train_candidate_classifier.py
can call train(cfg) and remain a thin CLI wrapper.

Loss: weighted cross-entropy or focal loss (for class imbalance).
Metrics tracked: per-class precision/recall, false-primary rate,
decoy rejection, UNKNOWN precision, confusion matrix, inference time.

Requires torch + torchvision. If unavailable, raises ImportError
with a helpful message (do not silently skip training).
"""
from __future__ import annotations

from pathlib import Path
from typing import Dict, Any
import json


def train(cfg: Dict[str, Any]) -> Dict[str, Any]:
    """
    Train MobileNetV3-Small on candidate patches.
    Returns summary dict with val metrics and checkpoint path.
    """
    try:
        import torch  # type: ignore
    except Exception as e:
        raise ImportError(
            "PyTorch is required to train the candidate classifier. "
            "Install with: pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu"
        ) from e

    # Resolve paths from configs/training.yaml
    tr = cfg.get("training", {}) if isinstance(cfg, dict) else {}
    data_root = Path(tr.get("data_root", "data/datasets"))
    out_dir = Path(tr.get("candidate_out", "models/candidate_classifier"))
    out_dir.mkdir(parents=True, exist_ok=True)

    # Placeholder: full epoch loop, dataloader, focal loss, etc.
    # The CLI script wires this up with CandidatePatchDataset.
    summary: Dict[str, Any] = {
        "model": "MobileNetV3-Small",
        "status": "not_implemented_stub",
        "hint": "Run scripts/generate_training_data.py first, then fill this loop. See docs/training_pipeline.md.",
        "out_dir": str(out_dir),
    }
    # write stub metadata so evaluation can run without crashing
    (out_dir / "train_summary.json").write_text(json.dumps(summary, indent=2))
    return summary
