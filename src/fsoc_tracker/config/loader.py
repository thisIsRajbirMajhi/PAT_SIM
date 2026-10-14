"""Legacy compatibility: canonical implementation lives in pat_common.config."""
from pat_common.config.loader import deep_merge, load_config, save_config

__all__ = ["deep_merge", "load_config", "save_config"]
