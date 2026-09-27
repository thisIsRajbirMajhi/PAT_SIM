"""Canonical defaults for the Target module.

Single source of truth remains config/defaults.py:DEFAULT_CONFIG;
a deep copy is re-exported here so mutating it never affects globals.
Accessors return copies (mutating the result never mutates the cfg).
"""
import copy

from ..config.accessors import get_target as _get_target
from ..config.defaults import DEFAULT_CONFIG

TARGET_DEFAULTS = copy.deepcopy(DEFAULT_CONFIG["target"])


def get_target(cfg):
    tgt = _get_target(cfg)
    return dict(tgt) if isinstance(tgt, dict) else {}


def get_visibility_schedule(cfg):
    if not isinstance(cfg, dict):
        return None
    tgt = cfg.get("target", {}) or {}
    return tgt.get("visibility_schedule") or (cfg.get("visibility", {}) or {}).get("schedule")


def target_appearance_changed(old_cfg, new_cfg):
    o = old_cfg.get("target", {}) if isinstance(old_cfg, dict) else {}
    n = new_cfg.get("target", {}) if isinstance(new_cfg, dict) else {}
    return (
        o.get("shape") != n.get("shape")
        or o.get("size") != n.get("size")
        or o.get("blink_rate_hz") != n.get("blink_rate_hz")
    )


__all__ = ["TARGET_DEFAULTS", "get_target", "get_visibility_schedule", "target_appearance_changed"]
