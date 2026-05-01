"""
数据获取模块 — 通过适配器层统一管理多数据源
重构版：从 data_loader.py 迁移到适配器模式

外部统一接口 get_historical_data / get_etf_realtime / save_signal / load_previous_signal
保持向后兼容，内部使用适配器层
"""
import json
import os
import logging

from .adapters import get_adapter

logger = logging.getLogger(__name__)

# 全局默认适配器实例（懒加载）
_adapter = None


def _get_adapter():
    """获取全局适配器实例（按需创建）"""
    global _adapter
    if _adapter is None:
        # 先尝试从 config.yaml 读取配置
        config = {}
        try:
            config_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "config.yaml")
            if os.path.exists(config_path):
                import yaml
                with open(config_path) as f:
                    cfg = yaml.safe_load(f)
                config = cfg or {}
        except Exception:
            pass
        _adapter = get_adapter(config=config)
    return _adapter


def set_adapter(name: str = None):
    """手动切换数据源适配器"""
    global _adapter
    _adapter = get_adapter(name)


def get_historical_data(symbol: str, days: int = 800, max_retries: int = 2) -> "pd.DataFrame":
    """获取历史K线数据（支持重试）"""
    import time
    import pandas as pd

    last_error = None
    for attempt in range(max_retries + 1):
        try:
            df = _get_adapter().get_historical(symbol, days)
            if isinstance(df, pd.DataFrame) and not df.empty:
                return df
        except Exception as e:
            last_error = e
            if attempt < max_retries:
                time.sleep(2)

    # 全部失败，尝试 fallback 适配器
    try:
        logger.warning("[data] %s 失败，尝试 fallback 数据源", _get_adapter().name)
        from .adapters import list_adapters
        for name in list_adapters():
            if name == _get_adapter().name:
                continue
            try:
                fallback = get_adapter(name)
                df = fallback.get_historical(symbol, days)
                if isinstance(df, pd.DataFrame) and not df.empty:
                    logger.info("[data] fallback 到 %s 成功", name)
                    return df
            except Exception:
                continue
    except Exception:
        pass

    raise RuntimeError(f"所有数据源获取{symbol}历史数据均失败: {last_error}")


def get_etf_realtime(symbol: str) -> dict:
    """获取ETF实时行情"""
    return _get_adapter().get_realtime(symbol)


def save_signal(symbol: str, signal: dict, signals_dir: str = "signals"):
    """保存信号到文件"""
    os.makedirs(signals_dir, exist_ok=True)
    path = os.path.join(signals_dir, f"{symbol}_signal.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(signal, f, ensure_ascii=False, indent=2)
    return path


def load_previous_signal(symbol: str, signals_dir: str = "signals") -> dict:
    """加载上一次信号"""
    path = os.path.join(signals_dir, f"{symbol}_signal.json")
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}
