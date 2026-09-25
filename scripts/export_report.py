"""Export a run report from the latest outputs/runs entry (Prompt §10).

Usage:
    python scripts/export_report.py --run-dir outputs/runs/<timestamp>_<traj>_seedN
    python scripts/export_report.py --latest
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))


def main() -> int:
    ap = argparse.ArgumentParser(description="Export/inspect a run report directory.")
    ap.add_argument("--run-dir", default=None, help="Existing run directory to validate.")
    ap.add_argument("--latest", action="store_true", help="Use latest outputs/runs/* entry.")
    args = ap.parse_args()

    root = Path("outputs") / "runs"
    target = Path(args.run_dir) if args.run_dir else None
    if args.latest or target is None:
        if not root.exists():
            print("No outputs/runs directory yet — run the app or scripts/run_simulation.py first.")
            return 1
        entries = sorted([p for p in root.iterdir() if p.is_dir()])
        if not entries:
            print("No run directories found.")
            return 1
        target = entries[-1]
    expected = ["config_used.yaml", "summary_report.json", "frame_metrics.csv", "events.json", "run_metadata.json"]
    missing = [f for f in expected if not (target / f).exists()]
    print(f"Run dir: {target}")
    if missing:
        print(f"MISSING: {missing}")
        return 2
    print("OK — all expected report artifacts present: " + ", ".join(expected))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
