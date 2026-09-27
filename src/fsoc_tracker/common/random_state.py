"""Backward-compat shim: canonical implementation lives in common/random/.

Use `from .random import seed_all, make_rng` in new code.
"""
from .random import make_rng, seed_all

__all__ = ["seed_all", "make_rng"]
