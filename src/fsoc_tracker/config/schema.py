from typing import Any, Dict

def validate_config(cfg: Dict[str, Any]) -> Dict[str, Any]:
    # minimal validation - ensure required keys
    assert cfg["camera"]["resolution"][0] > 0 and cfg["camera"]["resolution"][1] > 0, "resolution must be >0"
    assert cfg["camera"]["fov_deg"][0] > 0 and cfg["camera"]["fov_deg"][1] > 0, "FOV must be >0"
    assert cfg["camera"]["max_pan_speed"] > 0, "max pan speed >0"
    assert cfg["target"]["size"] >= 3, "target size too small"
    assert cfg["target"]["speed_px_per_frame"] >= 0, "speed >=0"
    return cfg
