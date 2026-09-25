"""
Confusion-matrix helpers for candidate + identity models.
"""
from __future__ import annotations

import numpy as np
from typing import List


def confusion_matrix(y_true: np.ndarray, y_pred: np.ndarray, num_classes: int) -> np.ndarray:
    cm = np.zeros((num_classes, num_classes), dtype=int)
    for t, p in zip(y_true, y_pred):
        if 0 <= t < num_classes and 0 <= p < num_classes:
            cm[int(t), int(p)] += 1
    return cm


def format_confusion(cm: np.ndarray, labels: List[str]) -> str:
    header = "true\\pred | " + "  ".join(f"{l:>8}" for l in labels)
    lines = [header, "-" * len(header)]
    for i, l in enumerate(labels):
        row = f"{l:>9} | " + "  ".join(f"{cm[i, j]:8d}" for j in range(len(labels)))
        lines.append(row)
    return "\n".join(lines)
