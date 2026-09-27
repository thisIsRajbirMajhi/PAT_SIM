"""Beacon visibility schedule — hide beacon during hidden intervals (forces loss/re-acq)."""


def get_visibility_schedule(cfg):
    return cfg["target"].get("visibility_schedule") or cfg.get("visibility", {}).get("schedule")


def is_hidden(frame_id, cfg):
    """True if frame_id falls inside a hidden/invisible/off schedule segment."""
    vis_sched = get_visibility_schedule(cfg)
    if not vis_sched:
        return False
    try:
        t = frame_id / max(float(cfg["camera"].get("fps", 30)), 1)
        for seg in vis_sched:
            # seg: [start, end, "visible"/"hidden"]
            if len(seg) >= 3:
                s, e, state = seg[0], seg[1], str(seg[2]).lower()
                if s <= t < e and state in ("hidden", "invisible", "off"):
                    return True
        return False
    except Exception:
        return False
