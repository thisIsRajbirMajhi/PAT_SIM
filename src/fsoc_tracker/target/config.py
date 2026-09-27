"""Canonical defaults for the Target module.

Single source of truth remains config/defaults.py:DEFAULT_CONFIG;
re-exported here for discoverability and standalone use.
"""
from ..config.defaults import DEFAULT_CONFIG

TARGET_DEFAULTS = DEFAULT_CONFIG["target"]


def get_target(cfg):
    return cfg.get("target", {})


def get_visibility_schedule(cfg):
    return cfg["target"].get("visibility_schedule") or cfg.get("visibility", {}).get("schedule")


def target_appearance_changed(old_cfg, new_cfg):
    o, n = old_cfg.get("target", {}), new_cfg.get("target", {})
    return (
        o.get("shape") != n.get("shape")
        or o.get("size") != n.get("size")
        or o.get("intensity") != n.get("intensity")
        or o.get("custom_polygon") != n.get("custom_polygon")
    )


__all__ = ["TARGET_DEFAULTS", "get_target", "get_visibility_schedule", "target_appearance_changed"]
