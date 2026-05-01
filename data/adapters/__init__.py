"""
金箍棒数据源适配器 — 配置驱动的多数据源透明切换
借鉴 TradingAgents 的 dataflows/interface.py 供应商路由模式

使用方式：
    from data.adapters import get_data_adapter
    adapter = get_data_adapter()
    df = adapter.get_historical("510050", days=800)
    price = adapter.get_realtime("510300")
"""
import importlib
import logging
from typing import Protocol, Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 抽象接口
# ---------------------------------------------------------------------------

class DataAdapter(Protocol):
    """所有数据源适配器必须实现的接口"""

    name: str

    def get_historical(self, symbol: str, days: int = 800) -> "pd.DataFrame":
        """获取历史K线数据，返回含 date/open/high/low/close/volume/amount 的 DataFrame"""
        ...

    def get_realtime(self, symbol: str) -> dict:
        """获取实时行情，返回 {symbol, name, price, change_pct, volume, timestamp}"""
        ...

    def health(self) -> bool:
        """检查数据源是否可用"""
        ...

# ---------------------------------------------------------------------------
# 适配器注册表
# ---------------------------------------------------------------------------

_ADAPTERS: dict[str, type[DataAdapter]] = {}

def register_adapter(name: str):
    """装饰器：注册数据源适配器"""
    def _wrap(cls):
        _ADAPTERS[name] = cls
        cls.name = name
        return cls
    return _wrap

def list_adapters() -> list[str]:
    """列出所有已注册的适配器"""
    return list(_ADAPTERS.keys())

# ---------------------------------------------------------------------------
# 适配器工厂
# ---------------------------------------------------------------------------

def get_adapter(name: str = None, config: dict = None) -> DataAdapter:
    """
    获取数据源适配器实例。

    参数：
        name: 适配器名称，如 "sina", "akshare", "yfinance"
        config: 配置字典，可选

    如果 name 为 None，从 config 读取 "data_adapter" 配置，默认 "sina"。
    """
    if name is None:
        name = (config or {}).get("data_adapter", "sina")

    if name not in _ADAPTERS:
        available = ", ".join(_ADAPTERS.keys())
        raise ValueError(f"未知数据源 '{name}'，可用: {available}")

    cls = _ADAPTERS[name]
    return cls(config)

# ---------------------------------------------------------------------------
# 自动注册各适配器（延迟加载）
# ---------------------------------------------------------------------------

def _auto_register():
    """扫描 adapters/ 目录下的所有适配器模块，自动注册"""
    import os
    import pkgutil
    import importlib

    pkg_dir = os.path.dirname(__file__)
    for importer, modname, ispkg in pkgutil.iter_modules([pkg_dir]):
        if modname.startswith("_") or modname == "base":
            continue
        try:
            importlib.import_module(f".{modname}", __package__)
        except Exception as e:
            logger.warning("[data] 加载适配器 %s 失败: %s", modname, e)

_auto_register()
