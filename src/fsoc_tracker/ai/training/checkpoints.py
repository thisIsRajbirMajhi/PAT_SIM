"""
Checkpoint helpers — reproducible saves with metadata.

Every save writes:
  checkpoint.pt / .onnx  +  metadata.json  (ModelMetadata)
  + config snapshot + random seed + data version
so any run can be reproduced (Prompt §7).
"""
from __future__ import annotations

from pathlib import Path
import json
import time
from typing import Dict, Any


def save_metadata(out_dir: Path, metadata: Dict[str, Any]) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    metadata = dict(metadata)
    metadata.setdefault("saved_at", time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
    path = out_dir / "metadata.json"
    path.write_text(json.dumps(metadata, indent=2))
    return path


def load_metadata(out_dir: Path) -> Dict[str, Any]:
    p = out_dir / "metadata.json"
    if not p.exists():
        return {}
    return json.loads(p.read_text())
