"""
Training logic for Stage-1 candidate classifier — Prompt Phase 4.

Real training loop:
 - MobileNetV3-Small backbone (1-channel 64×64) + numerical-feature MLP
   (built by ai.candidate_model._build_torch_candidate)
 - Focal loss or weighted cross-entropy (configs/training.yaml)
 - Per-class precision/recall, false-primary rate, decoy rejection,
   UNKNOWN precision, confusion matrix, inference latency.
 - Saves checkpoint + ModelMetadata + training curves (Plan §9.2 Step 6).

Requires torch + torchvision. If unavailable, raises ImportError
with a helpful message (do not silently skip training).
"""
from __future__ import annotations

from pathlib import Path
from typing import Dict, Any, List
import json
import time

import numpy as np


def _load_datasets(cfg: Dict[str, Any]):
    from pathlib import Path as _P
    tr = cfg.get("training", {}) if isinstance(cfg, dict) else {}
    data_root = _P(tr.get("data_root", "data/datasets"))
    from .dataset import CandidatePatchDataset
    return (
        CandidatePatchDataset(data_root, "train", augment=True, seed=int(tr.get("seed", 42))),
        CandidatePatchDataset(data_root, "val", augment=False),
    )


def _focal_loss(logits, targets, gamma: float = 2.0, weights=None):
    """
    Multi-class focal loss with optional per-class weights.
    Mixed 50/50 with plain cross-entropy: pure focal can collapse to the
    majority class early in training because easy examples get almost
    zero gradient. The CE term keeps gradients alive for the dominant
    classes while focal emphasises hard examples.
    """
    import torch
    import torch.nn.functional as F
    ce = F.cross_entropy(logits, targets, weight=weights, reduction="none")
    pt = torch.exp(-ce)
    focal = ((1 - pt) ** gamma * ce).mean()
    return 0.5 * focal + 0.5 * ce.mean()


def _evaluate(model, val_ds, class_ids: Dict[str, int]) -> Dict[str, float]:
    """Validation metrics: per-class precision/recall, confusion, latency."""
    import torch
    model.eval()
    confusion = np.zeros((len(class_ids), len(class_ids)), dtype=np.int64)
    t_lat = []
    with torch.no_grad():
        for patches, nums, labels in val_ds.iter_batches(batch_size=128, shuffle=False):
            t0 = time.perf_counter()
            logits, qual, emb = model(torch.from_numpy(patches), torch.from_numpy(nums))
            t_lat.append((time.perf_counter() - t0) * 1000.0 / max(len(patches), 1))
            preds = logits.argmax(dim=1).cpu().numpy()
            for p, y in zip(preds, labels):
                confusion[y, p] += 1
    metrics: Dict[str, float] = {}
    per_class_prec, per_class_rec = {}, {}
    n_cls = len(class_ids)
    for cid, cname in enumerate(class_ids.keys()):
        tp = confusion[cid, cid]
        fp = confusion[:, cid].sum() - tp
        fn = confusion[cid, :].sum() - tp
        prec = tp / max(tp + fp, 1)
        rec = tp / max(tp + fn, 1)
        per_class_prec[cname] = float(prec)
        per_class_rec[cname] = float(rec)
    metrics["per_class_precision"] = per_class_prec
    metrics["per_class_recall"] = per_class_rec
    # safety metrics: false-primary = non-BEACON predicted as BEACON
    beacon_id = class_ids["BEACON_LIKE"]
    decoy_id = class_ids["DECOY_LIKE"]
    fp_primary = confusion[decoy_id, beacon_id] + confusion[0 if beacon_id != 0 else 1, beacon_id]
    fp_primary = int(confusion[:, beacon_id].sum() - confusion[beacon_id, beacon_id])
    metrics["false_primary_rate"] = float(fp_primary / max(confusion.sum(), 1))
    # decoy rejection: decoys NOT predicted as beacon
    decoy_total = confusion[decoy_id, :].sum()
    metrics["decoy_rejection_rate"] = float(1.0 - confusion[decoy_id, beacon_id] / max(decoy_total, 1))
    unknown_id = class_ids["UNKNOWN"]
    unk_total = confusion[unknown_id, :].sum()
    metrics["unknown_precision"] = float(confusion[unknown_id, unknown_id] / max(unk_total, 1))
    total = confusion.sum()
    correct = np.trace(confusion)
    metrics["accuracy"] = float(correct / max(total, 1))
    metrics["latency_ms_per_patch"] = float(np.mean(t_lat)) if t_lat else 0.0
    metrics["confusion_matrix"] = confusion.tolist()
    return metrics


def train(cfg: Dict[str, Any]) -> Dict[str, Any]:
    """
    Train MobileNetV3-Small on candidate patches.
    Returns summary dict with val metrics and checkpoint path.
    """
    try:
        import torch
    except Exception as e:
        raise ImportError(
            "PyTorch is required to train the candidate classifier. "
            "Install with: pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu"
        ) from e
    import torch.nn as nn  # noqa: F401  (ensures nn submodule loaded)

    from ..candidate_model import _build_torch_candidate
    from .dataset import CANDIDATE_CLASS_IDS

    tr = cfg.get("training", {}) if isinstance(cfg, dict) else {}
    cand = tr.get("candidate", {})
    seed = int(tr.get("seed", 42))
    torch.manual_seed(seed)
    np.random.seed(seed)
    torch.use_deterministic_algorithms(True, warn_only=True)

    out_dir = Path(tr.get("candidate_out", "models/candidate_classifier"))
    out_dir.mkdir(parents=True, exist_ok=True)
    data_root = Path(tr.get("data_root", "data/datasets"))

    train_ds, val_ds = _load_datasets(cfg)
    if len(train_ds) == 0:
        raise RuntimeError(
            f"No training patches found at {data_root}/candidate_patches/train.jsonl — "
            "run scripts/generate_training_data.py first."
        )
    if len(val_ds) == 0:
        raise RuntimeError(
            f"No validation patches found at {data_root}/candidate_patches/val.jsonl — "
            "run scripts/generate_training_data.py with >=71 seeds."
        )

    class_ids = {k: v for k, v in CANDIDATE_CLASS_IDS.items()}  # name→id
    model = _build_torch_candidate((torch, nn))
    epochs = int(cand.get("epochs", 30))
    batch_size = int(cand.get("batch_size", 64))
    lr = float(cand.get("lr", 1e-3))
    wd = float(cand.get("weight_decay", 1e-4))
    gamma = float(cand.get("focal_gamma", 2.0))
    use_focal = str(cand.get("loss", "focal")).lower() == "focal"
    patience = int(cand.get("early_stop_patience", 6))
    val_metric_target = str(cand.get("val_metric", "f1_beacon"))

    # class weights from the TRAIN distribution, capped so rare absent
    # classes cannot dominate (Plan §9.2 Step 6: weighted/focal for imbalance)
    raw_w = train_ds.class_weights.copy()
    present = np.zeros(len(raw_w), dtype=bool)
    from .dataset import CANDIDATE_CLASS_IDS as _cid
    for r in train_ds.records:
        from .dataset import _candidate_label
        present[_candidate_label(r)] = True
    raw_w[~present] = 1.0  # classes absent from train get neutral weight
    raw_w = np.clip(raw_w, 0.5, 4.0)  # floor: never strongly downweight majority
    weights = torch.tensor(raw_w)
    opt = torch.optim.AdamW(model.parameters(), lr=lr, weight_decay=wd)
    sched = torch.optim.lr_scheduler.CosineAnnealingLR(opt, T_max=epochs)

    best_score = -1.0
    best_epoch = -1
    best_val: Dict[str, Any] = {}
    patience_left = patience + 2
    history: List[Dict[str, Any]] = []

    for epoch in range(epochs):
        model.train()
        epoch_loss, n_seen = 0.0, 0
        for patches, nums, labels in train_ds.iter_batches(batch_size=batch_size, shuffle=True):
            opt.zero_grad()
            logits, _qual, _emb = model(torch.from_numpy(patches), torch.from_numpy(nums))
            targets = torch.from_numpy(labels)
            if use_focal:
                loss = _focal_loss(logits, targets, gamma=gamma, weights=weights)
            else:
                loss = torch.nn.functional.cross_entropy(logits, targets, weight=weights)
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 5.0)
            opt.step()
            epoch_loss += float(loss.detach()) * len(labels)
            n_seen += len(labels)
        sched.step()
        train_loss = epoch_loss / max(n_seen, 1)

        val_metrics = _evaluate(model, val_ds, class_ids)
        prec_b = val_metrics["per_class_precision"].get("BEACON_LIKE", 0.0)
        rec_b = val_metrics["per_class_recall"].get("BEACON_LIKE", 0.0)
        f1_beacon = 2 * prec_b * rec_b / max(prec_b + rec_b, 1e-9)
        # model selection on safety-aware metric, not accuracy alone (Plan §9.2 Step 6)
        score = f1_beacon - 2.0 * val_metrics["false_primary_rate"]

        history.append({
            "epoch": epoch, "train_loss": train_loss,
            "val_f1_beacon": f1_beacon,
            "val_false_primary_rate": val_metrics["false_primary_rate"],
            "val_accuracy": val_metrics["accuracy"],
        })
        print(f"[train_candidate] epoch {epoch+1}/{epochs} loss={train_loss:.4f} "
              f"val_f1_beacon={f1_beacon:.3f} false_primary={val_metrics['false_primary_rate']:.3f}")

        if score > best_score:
            best_score = score
            best_epoch = epoch
            best_val = val_metrics
            torch.save({"state_dict": model.state_dict(), "epoch": epoch,
                        "class_ids": class_ids, "val_metrics": {k: v for k, v in val_metrics.items() if k != "confusion_matrix"}},
                       out_dir / "candidate_model.pt")
            patience_left = patience
        else:
            patience_left -= 1
            if patience_left <= 0:
                print(f"[train_candidate] early stop at epoch {epoch+1} (best epoch {best_epoch+1})")
                break

    # reload best weights for final summary
    ckpt = torch.load(out_dir / "candidate_model.pt", map_location="cpu")
    model.load_state_dict(ckpt["state_dict"])
    final_val = _evaluate(model, val_ds, class_ids)

    summary: Dict[str, Any] = {
        "model": "MobileNetV3-Small",
        "status": "trained",
        "checkpoint": str(out_dir / "candidate_model.pt"),
        "best_epoch": best_epoch,
        "epochs_run": len(history),
        "val_metrics": {k: v for k, v in final_val.items() if k != "confusion_matrix"},
        "confusion_matrix": final_val["confusion_matrix"],
        "train_samples": len(train_ds),
        "val_samples": len(val_ds),
        "seed": seed,
        "val_metric": val_metric_target,
    }
    (out_dir / "train_summary.json").write_text(json.dumps(summary, indent=2))

    from .checkpoints import save_metadata
    save_metadata(out_dir, {
        "model_name": "MobileNetV3-Small",
        "version": f"epoch{best_epoch}",
        "random_seed": seed,
        "data_version": "1.0.0",
        "train_metrics": {"final_train_loss": history[-1]["train_loss"] if history else None},
        "val_metrics": {k: v for k, v in final_val.items() if k != "confusion_matrix"},
        "config_snapshot": {"candidate": cand},
        "export_format": "pt",
    })
    return summary
