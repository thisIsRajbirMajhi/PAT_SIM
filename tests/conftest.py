"""Pytest bootstrap: put repo root, src/, and tests/ on sys.path.

Located at tests/conftest.py. Makes `pytest`, `python -m pytest`, and
`python tests/headless.py` all work from any CWD.
"""
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))   # tests/
_ROOT = os.path.dirname(_HERE)                       # repo root

for _p in (os.path.join(_ROOT, "src"), _HERE, _ROOT):
    if _p not in sys.path:
        sys.path.insert(0, _p)