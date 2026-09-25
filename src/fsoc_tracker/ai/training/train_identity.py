"""
Training logic for Stage-2 GRU identity classifier — Prompt Phase 5.

Real training loop:
 - 1-layer GRU (hidden 64/128) over (T, 11) motion/signal sequences
   (built by ai.identity_model._build_torch_gru)
 - Weighted cross-entropy over {PRIMARY, DECOY, UNKNOWN}
 - Sequence-level metrics: primary precision/recall, decoy rejection,
   false-lock rate, identity-switch count, calibration.
 - Saves checkpoint + ModelMetadata (Plan §9.2 Step 7).

Typical flow:
  1) Freeze CNN, train GRU only.
  2) Optionally fine-tune CNN+GRU with lower LR.

Requires torch.
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
    from .dataset import TrackSequenceDataset
    return (
        TrackSequenceDataset(data_root, "train"),
        TrackSequenceDataset(data_root, "val"),
    )


def _evaluate(model, val_ds, class_ids: Dict[str, int]) -> Dict[str, Any]:
    """Sequence-level metrics (Plan §9.2 Step 7)."""
    import torch
    model.eval()
    confusion = np.zeros((len(class_ids), len(class_ids)), dtype=np.int64)
    t_lat = []
    with torch.no_grad():
        for seqs, masks, labels in val_ds.iter_batches(batch_size=64, shuffle=False):
            t0 = time.perf_counter()
            logits, conf = model(torch.from_numpy(seqs), torch.from_numpy(masks))
            t_lat.append((time.perf_counter() - t0) * 1000.0 / max(len(seqs), 1))
            preds = logits.argmax(dim=1).cpu().numpy()
            for p, y in zip(preds, labels):
                confusion[y, p] += 1
    primary_id = class_ids["PRIMARY"]
    decoy_id = class_ids["DECOY"]
    unknown_id = class_ids["UNKNOWN"]

    tp = int(confusion[primary_id, primary_id])
    fp = int(confusion[:, primary_id].sum() - tp)
    fn = int(confusion[primary_id, :].sum() - tp)
    prec = tp / max(tp + fp, 1)
    rec = tp / max(tp + fn, 1)
    f1 = 2 * prec * rec / max(prec + rec, 1e-9)

    decoy_total = int(confusion[decoy_id, :].sum())
    decoy_rej = 1.0 - confusion[decoy_id, primary_id] / max(decoy_total, 1)
    total_preds = int(confusion.sum())
    metrics: Dict[str, Any] = {
        "primary_precision": prec,
        "primary_recall": rec,
        "primary_f1": f1,
        "decoy_rejection_rate": float(decoy_rej),
        # false lock: non-primary tracks promoted to PRIMARY
        "false_lock_rate": float(fp / max(total_preds, 1)),
        "unknown_decision_rate": float(confusion[:, unknown_id].sum() / max(total_preds, 1)),
        "unknown_precision": float(confusion[unknown_id, unknown_id] / max(confusion[unknown_id, :].sum(), 1)),
        "accuracy": float(np.trace(confusion) / max(total_preds, 1)),
        "latency_ms_per_sequence": float(np.mean(t_lat)) if t_lat else 0.0,
        "confusion_matrix": confusion.tolist(),
    }
    return metrics


def train(cfg: Dict[str, Any]) -> Dict[str, Any]:
    try:
        import torch
    except Exception as e:
        raise ImportError(
            "PyTorch is required to train the GRU identity model. "
            "Install with: pip install torch --index-url https://download.pytorch.org/whl/cpu"
        ) from e
    import torch.nn as nn

    from ..identity_model import _build_torch_gru
    from .dataset import IDENTITY_CLASS_IDS, SEQ_FEATURE_DIM

    tr = cfg.get("training", {}) if isinstance(cfg, dict) else {}
    ident = tr.get("identity", {})
    seed = int(tr.get("seed", 42))
    torch.manual_seed(seed)
    np.random.seed(seed)
    torch.use_deterministic_algorithms(True, warn_only=True)

    out_dir = Path(tr.get("identity_out", "models/identity_classifier"))
    out_dir.mkdir(parents=True, exist_ok=True)
    data_root = Path(tr.get("data_root", "data/datasets"))

    train_ds, val_ds = _load_datasets(cfg)
    if len(train_ds) == 0:
        raise RuntimeError(
            f"No training sequences found at {data_root}/track_sequences/train.jsonl — "
            "run scripts/generate_training_data.py first."
        )
    if len(val_ds) == 0:
        raise RuntimeError(
            f"No validation sequences found at {data_root}/track_sequences/val.jsonl — "
            "run scripts/generate_training_data.py with >=71 seeds."
        )

    class_ids = dict(IDENTITY_CLASS_IDS)  # name→id
    hidden = int(ident.get("hidden", 64))
    seq_len = int(ident.get("seq_len", 25))
    model = _build_torch_gru((torch, nn), input_dim=SEQ_FEATURE_DIM, hidden=hidden)
    epochs = int(ident.get("epochs", 40))
    batch_size = int(ident.get("batch_size", 32))
    lr = float(ident.get("lr", 1e-3))
    use_weighted = str(ident.get("loss", "weighted_ce")).lower() == "weighted_ce"
    patience = 8
    # class weights from the TRAIN distribution, capped; absent classes neutral
    raw_w = train_ds.class_weights.copy()
    from .dataset import IDENTITY_CLASS_IDS as _iid
    present = np.zeros(len(raw_w), dtype=bool)
    for r in train_ds.records:
        present[_iid.get(r.get("label", "UNKNOWN"), 2)] = True
    raw_w[~present] = 1.0
    raw_w = np.clip(raw_w, 0.25, 8.0)
    weights = torch.tensor(raw_w)
    opt = torch.optim.AdamW(model.parameters(), lr=lr, weight_decay=1e-4)
    sched = torch.optim.lr_scheduler.CosineAnnealingLR(opt, T_max=epochs)

    best_score = -1.0
    best_epoch = -1
    patience_left = patience + 2
    history: List[Dict[str, Any]] = []

    # small dataset (< 100 sequences): full-batch training with label
    # smoothing + weight decay — prevents the over-confidence and rare-class
    # collapse that minibatch weighted-CE causes at this scale
    tiny = len(train_ds) < 100
    crit = None
    if tiny:
        import torch as _t
        crit = _t.nn.CrossEntropyLoss(label_smoothing=0.1)
        opt = _t.optim.Adam(model.parameters(), lr=1e-2, weight_decay=1e-3)
        sched = None
        print(f"[train_identity] tiny dataset ({len(train_ds)} seqs) — full-batch, label smoothing 0.1, lr=1e-2")

    for epoch in range(epochs):
        model.train()
        epoch_loss, n_seen = 0.0, 0
        if tiny:
            # full-batch pass over all sequences
            X = torch.from_numpy(np.stack([train_ds[i][0] for i in range(len(train_ds))]))
            Mo = torch.from_numpy(np.stack([train_ds[i][1] for i in range(len(train_ds))]))
            targets = torch.from_numpy(np.array([train_ds[i][2] for i in range(len(train_ds))], dtype=np.int64))
            opt.zero_grad()
            logits, _conf = model(X, Mo)
            loss = crit(logits, targets)
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 5.0)
            opt.step()
            epoch_loss = float(loss.detach()) * len(targets)
            n_seen = len(targets)
        else:
            for seqs, masks, labels in train_ds.iter_batches(batch_size=batch_size, shuffle=True, seed=seed + epoch):
                opt.zero_grad()
                logits, _conf = model(torch.from_numpy(seqs), torch.from_numpy(masks))
                targets = torch.from_numpy(labels)
                if use_weighted:
                    loss = torch.nn.functional.cross_entropy(logits, targets, weight=weights)
                else:
                    loss = torch.nn.functional.cross_entropy(logits, targets)
                loss.backward()
                torch.nn.utils.clip_grad_norm_(model.parameters(), 5.0)
                opt.step()
                epoch_loss += float(loss.detach()) * len(labels)
                n_seen += len(labels)
            sched.step()
        train_loss = epoch_loss / max(n_seen, 1)

        val = _evaluate(model, val_ds, class_ids)
        # safety-aware selection: primary F1 minus false-lock penalty (Plan §7)
        score = val["primary_f1"] - 2.0 * val["false_lock_rate"]

        history.append({
            "epoch": epoch, "train_loss": train_loss,
            "primary_f1": val["primary_f1"],
            "false_lock_rate": val["false_lock_rate"],
            "decoy_rejection_rate": val["decoy_rejection_rate"],
        })
        print(f"[train_identity] epoch {epoch+1}/{epochs} loss={train_loss:.4f} "
              f"primary_f1={val['primary_f1']:.3f} false_lock={val['false_lock_rate']:.3f}")

        if score > best_score:
            best_score = score
            best_epoch = epoch
            best_val = val
            torch.save({"state_dict": model.state_dict(), "epoch": epoch,
                        "class_ids": class_ids,
                        "val_metrics": {k: v for k, v in val.items() if k != "confusion_matrix"}},
                       out_dir / "identity_model.pt")
            patience_left = patience
        else:
            patience_left -= 1
            if patience_left <= 0:
                print(f"[train_identity] early stop at epoch {epoch+1} (best epoch {best_epoch+1})")
                break

    ckpt = torch.load(out_dir / "identity_model.pt", map_location="cpu")
    model.load_state_dict(ckpt["state_dict"])
    final_val = _evaluate(model, val_ds, class_ids)

    summary: Dict[str, Any] = {
        "model": f"GRU-1-layer hidden={hidden} seq_len={seq_len}",
        "status": "trained",
        "checkpoint": str(out_dir / "identity_model.pt"),
        "best_epoch": best_epoch,
        "epochs_run": len(history),
        "val_metrics": {k: v for k, v in final_val.items() if k != "confusion_matrix"},
        "confusion_matrix": final_val["confusion_matrix"],
        "train_samples": len(train_ds),
        "val_samples": len(val_ds),
        "seed": seed,
    }
    (out_dir / "train_summary.json").write_text(json.dumps(summary, indent=2))

    from .checkpoints import save_metadata
    save_metadata(out_dir, {
        "model_name": "GRUIdentity",
        "version": f"epoch{best_epoch}",
        "random_seed": seed,
        "data_version": "1.0.0",
        "train_metrics": {"final_train_loss": history[-1]["train_loss"] if history else None},
        "val_metrics": {k: v for k, v in final_val.items() if k != "confusion_matrix"},
        "config_snapshot": {"identity": ident},
        "export_format": "pt",
    })
    return summary
