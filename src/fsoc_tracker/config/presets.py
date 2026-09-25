"""Discovery helpers for user-facing and benchmark preset files.

The simulator keeps two different kinds of YAML configuration:

* ``configs/presets/`` contains the small, curated presets exposed by the
  Control Deck.
* ``configs/benchmarks/`` contains the detailed P01-P12 regression scenarios
  used by the headless test suite.

Keeping discovery in one place prevents configuration files such as
``ai.yaml`` and ``training.yaml`` from accidentally appearing as presets in
 the GUI.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

import yaml


PROJECT_ROOT = Path(__file__).resolve().parents[3]
GUI_PRESET_DIR = PROJECT_ROOT / "configs" / "presets"
BENCHMARK_DIR = PROJECT_ROOT / "configs" / "benchmarks"


@dataclass(frozen=True)
class PresetInfo:
    """Metadata for one discoverable Control Deck preset."""

    preset_id: str
    display_name: str
    path: Path
    ai_mode: str
    purpose: str
    expected: Dict[str, Any]
    order: int
    system: str = "deterministic"

    @property
    def is_ai_preset(self) -> bool:
        return self.ai_mode.strip().upper() in {"ON", "TRUE", "YES", "ENABLED", "1"}

    @property
    def is_deterministic_preset(self) -> bool:
        return self.system == "deterministic"


def _read_yaml(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    return data if isinstance(data, dict) else {}


def _pretty_name(stem: str) -> str:
    # Numeric curated files use a friendly name from preset_meta. This is
    # only the fallback for user-created files without that optional field.
    return stem.replace("_", " ").strip().title()


def _normalise_mode(value: Any, *, data: Optional[Dict[str, Any]] = None) -> str:
    if isinstance(value, bool):
        return "ON" if value else "OFF"
    if value is not None:
        return str(value).strip().upper()
    if data is not None:
        return "ON" if bool(data.get("ai", {}).get("enabled", False)) else "OFF"
    return "OFF"


def _normalise_system(value: Any, *, ai_mode: str) -> str:
    """Return the Control Deck portion that owns a preset.

    ``system`` is explicit in maintained preset files. The AI mode fallback
    keeps older custom presets discoverable and places them in the expected
    portion without exposing benchmark files.
    """
    text = str(value or "").strip().lower()
    if text in {"ai", "ai_system", "ai-system", "identity"}:
        return "ai"
    if text in {"deterministic", "classical", "classic", "det", "existing"}:
        return "deterministic"
    return "ai" if ai_mode in {"ON", "TRUE", "YES", "ENABLED", "1"} else "deterministic"


def _as_int(value: Any, default: int = 999) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def discover_presets(directory: Optional[Path] = None) -> List[PresetInfo]:
    """Return valid, sorted presets from the curated preset directory.

    A file is a user-facing preset only when it contains a ``preset_meta``
    mapping. Invalid or incomplete files are ignored rather than making the
    Control Deck unusable; normal preset validation is still performed by
    :func:`fsoc_tracker.config.loader.load_config` when a preset is loaded.
    """
    root = Path(directory) if directory is not None else GUI_PRESET_DIR
    if not root.exists():
        return []

    found: List[PresetInfo] = []
    for path in sorted(root.glob("*.yaml")):
        try:
            data = _read_yaml(path)
        except (OSError, yaml.YAMLError):
            continue
        meta = data.get("preset_meta")
        if not isinstance(meta, dict):
            continue
        preset_id = str(meta.get("preset") or path.stem).strip()
        display_name = str(meta.get("display_name") or _pretty_name(path.stem)).strip()
        if not preset_id or not display_name:
            continue
        expected = meta.get("expected", {})
        if not isinstance(expected, dict):
            expected = {"result": expected}
        ai_mode = _normalise_mode(meta.get("ai_mode"), data=data)
        found.append(
            PresetInfo(
                preset_id=preset_id,
                display_name=display_name,
                path=path,
                ai_mode=ai_mode,
                purpose=str(meta.get("purpose") or "").strip(),
                expected=expected,
                order=_as_int(meta.get("order")),
                system=_normalise_system(meta.get("system"), ai_mode=ai_mode),
            )
        )

    # A custom preset may not declare an order; it remains available, after
    # the maintained presets, rather than disappearing from the selector.
    return sorted(found, key=lambda item: (item.order, item.display_name.casefold(), item.preset_id))


def presets_for_system(system: str, directory: Optional[Path] = None) -> List[PresetInfo]:
    """Return curated presets belonging to ``ai`` or ``deterministic``."""
    wanted = "ai" if str(system).strip().lower() in {"ai", "identity"} else "deterministic"
    return [preset for preset in discover_presets(directory) if preset.system == wanted]


def preset_by_id(preset_id: str, directory: Optional[Path] = None) -> Optional[PresetInfo]:
    for preset in discover_presets(directory):
        if preset.preset_id == preset_id:
            return preset
    return None


def benchmark_preset_paths(directory: Optional[Path] = None) -> List[Path]:
    """Return the P01-P12 benchmark scenario files, sorted numerically."""
    root = Path(directory) if directory is not None else BENCHMARK_DIR
    if not root.exists():
        return []
    return sorted(root.glob("P*.yaml"), key=lambda p: p.name.casefold())


__all__ = [
    "BENCHMARK_DIR",
    "GUI_PRESET_DIR",
    "PROJECT_ROOT",
    "PresetInfo",
    "benchmark_preset_paths",
    "discover_presets",
    "presets_for_system",
    "preset_by_id",
]
