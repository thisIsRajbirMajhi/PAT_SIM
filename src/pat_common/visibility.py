"""Beacon visibility schedule — hide beacon during hidden intervals (forces loss/re-acq).

Schedule format: list of [start_s, end_s, state] with state in
"visible" | "hidden" | "invisible" | "off". Times are seconds (frame_id / fps).
"""
_HIDDEN_STATES = frozenset({"hidden", "invisible", "off"})

#: blink square-wave duty cycle (fraction of each period the beacon is on)
BLINK_DUTY = 0.5


def get_blink_rate(cfg):
    try:
        return float((cfg.get("target", {}) or {}).get("blink_rate_hz", 0.0) or 0.0)
    except (TypeError, ValueError, AttributeError):
        return 0.0


def is_blink_off(frame_id, cfg):
    """True when beacon modulation (blink) is in its off half-cycle.

    rate <= 0 means steady on. Phase derives from frame time (frame_id / fps)
    so blinking stays in sync with the stream clock.
    """
    rate = get_blink_rate(cfg)
    if rate <= 0:
        return False
    try:
        fps = float((cfg.get("camera", {}) or {}).get("fps", 30))
        phase = (frame_id / max(fps, 1) * rate) % 1.0
        return phase >= BLINK_DUTY
    except (TypeError, ValueError, KeyError, ZeroDivisionError):
        return False


def get_visibility_schedule(cfg):
    if not isinstance(cfg, dict):
        return None
    tgt = cfg.get("target", {}) or {}
    return tgt.get("visibility_schedule") or (cfg.get("visibility", {}) or {}).get("schedule")


def validate_visibility_schedule(schedule):
    """Raise ValueError if a visibility schedule is malformed."""
    if schedule is None:
        return None
    if not isinstance(schedule, (list, tuple)):
        raise ValueError("visibility schedule must be a list of [start_s, end_s, state]")
    for seg in schedule:
        if not isinstance(seg, (list, tuple)) or len(seg) < 3:
            raise ValueError(f"bad visibility segment {seg!r}: expected [start_s, end_s, state]")
        s, e, state = seg[0], seg[1], str(seg[2]).lower()
        if not (isinstance(s, (int, float)) and isinstance(e, (int, float)) and s >= 0 and e > s):
            raise ValueError(f"bad visibility segment {seg!r}: need 0 <= start < end")
        if state not in ("visible", *_HIDDEN_STATES):
            raise ValueError(f"bad visibility state {seg[2]!r}: expected visible|hidden|invisible|off")
    return schedule


def is_hidden(frame_id, cfg):
    """True if frame_id falls inside a hidden/invisible/off schedule segment."""
    vis_sched = get_visibility_schedule(cfg)
    if not vis_sched:
        return False
    try:
        fps = float((cfg.get("camera", {}) or {}).get("fps", 30))
        t = frame_id / max(fps, 1)
        for seg in vis_sched:
            if not isinstance(seg, (list, tuple)) or len(seg) < 3:
                continue
            s, e, state = seg[0], seg[1], str(seg[2]).lower()
            if s <= t < e and state in _HIDDEN_STATES:
                return True
        return False
    except (TypeError, ValueError, KeyError, IndexError, ZeroDivisionError):
        return False
