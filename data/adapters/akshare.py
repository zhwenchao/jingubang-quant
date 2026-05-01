"""
akshare 适配器 — 使用东方财富接口
作为新浪的备选/替代数据源
"""
import pandas as pd
from datetime import datetime

from . import register_adapter

try:
    import akshare as ak
except ImportError:
    ak = None


@register_adapter("akshare")
class AkshareAdapter:
    """akshare 数据源适配器（东方财富接口）"""

    name = "akshare"

    def __init__(self, config: dict = None):
        self.config = config or {}

    def get_historical(self, symbol: str, days: int = 800) -> pd.DataFrame:
        if ak is None:
            raise RuntimeError("akshare 未安装")

        df = ak.fund_etf_hist_em(
            symbol=symbol,
            period="daily",
            start_date="20000101",
            end_date=datetime.now().strftime("%Y%m%d"),
            adjust="",
        )
        if df is None or df.empty:
            raise RuntimeError(f"akshare 返回空数据: {symbol}")

        # 标准化列名
        rename = {
            "日期": "date", "开盘": "open", "收盘": "close",
            "最高": "high", "最低": "low", "成交量": "volume", "成交额": "amount",
        }
        df.rename(columns={k: v for k, v in rename.items() if k in df.columns}, inplace=True)
        df["date"] = pd.to_datetime(df["date"])
        df = df.sort_values("date").reset_index(drop=True)
        df["open"] = df["open"].astype(float)
        df["high"] = df["high"].astype(float)
        df["low"] = df["low"].astype(float)
        df["close"] = df["close"].astype(float)
        df["volume"] = df["volume"].astype(float)
        if "amount" in df.columns:
            df["amount"] = df["amount"].astype(float)

        if days and days < len(df):
            df = df.tail(days).reset_index(drop=True)

        return df

    def get_realtime(self, symbol: str) -> dict:
        if ak is None:
            return {"symbol": symbol, "error": "akshare 未安装"}

        df = ak.fund_etf_spot_em()
        mask = df["代码"].astype(str) == symbol
        if not mask.any():
            mask = df["代码"].astype(str).str.endswith(symbol)
        if not mask.any():
            return {"symbol": symbol, "error": "未找到ETF数据"}

        r = df[mask].iloc[0]
        return {
            "symbol": symbol,
            "name": str(r.get("名称", "")),
            "price": float(r.get("最新价", 0)),
            "change_pct": float(r.get("涨跌幅", 0)),
            "volume": float(r.get("成交额", 0)),
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }

    def health(self) -> bool:
        if ak is None:
            return False
        try:
            df = ak.fund_etf_spot_em()
            return df is not None and not df.empty
        except Exception:
            return False
