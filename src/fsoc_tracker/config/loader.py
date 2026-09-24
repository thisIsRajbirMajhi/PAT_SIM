import copy, yaml, json, os
from .defaults import DEFAULT_CONFIG
from .schema import validate_config

def deep_merge(a, b):
    out = copy.deepcopy(a)
    for k, v in b.items():
        if k in out and isinstance(out[k], dict) and isinstance(v, dict):
            out[k] = deep_merge(out[k], v)
        else:
            out[k] = v
    return out

def load_config(path: str = None, overrides: dict = None):
    cfg = copy.deepcopy(DEFAULT_CONFIG)
    if path and os.path.exists(path):
        with open(path) as f:
            if path.endswith(".json"):
                data = json.load(f)
            else:
                data = yaml.safe_load(f) or {}
        cfg = deep_merge(cfg, data)
    if overrides:
        cfg = deep_merge(cfg, overrides)
    return validate_config(cfg)

def save_config(cfg, path: str):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w") as f:
        yaml.safe_dump(cfg, f, sort_keys=False)
