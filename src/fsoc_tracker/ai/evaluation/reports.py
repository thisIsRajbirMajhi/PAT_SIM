"""
Report generation for AI runs — extends evaluation/report.py output.

Writes to outputs/runs/<timestamp>_<traj>_seedN/:
  ai_metrics.json, confusion_candidate.png, confusion_identity.png,
  reliability_diagram.png, ai_report.html (appended section).
"""
from __future__ import annotations

from pathlib import Path
import json
from typing import Dict, Any


def write_ai_report(out_dir: Path, metrics: Dict[str, Any]) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "ai_metrics.json"
    path.write_text(json.dumps(metrics, indent=2))
    return path
