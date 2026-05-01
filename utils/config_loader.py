"""配置加载模块"""
import os
import yaml
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
DEFAULT_CONFIG = PROJECT_ROOT / "config.yaml"


def load_config(config_path: str = None) -> dict:
    """加载YAML配置文件"""
    path = config_path or str(DEFAULT_CONFIG)
    if not os.path.exists(path):
        raise FileNotFoundError(f"配置文件不存在: {path}")
    with open(path, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    # 解析路径为绝对路径
    base = Path(path).parent
    for key in ("signals_dir", "reports_dir", "data_cache"):
        rel = cfg.get("paths", {}).get(key, "")
        if rel and not os.path.isabs(rel):
            cfg["paths"][key] = str(base / rel)
    return cfg


def get_strategy_params(config: dict, name: str) -> dict:
    """获取指定策略的参数"""
    return config.get("strategies", {}).get(name, {})
