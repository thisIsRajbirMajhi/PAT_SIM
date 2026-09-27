"""Backward-compat shim: canonical implementation lives in common/time/.

Use `from .time import Clock` in new code.
"""
from .time import Clock

__all__ = ["Clock"]
