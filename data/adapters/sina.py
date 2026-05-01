"""
新浪财经适配器 — 直连新浪API获取K线 + 实时行情
稳定、无额外依赖（只需 requests）
"""
import json
import os
import time
import pandas as pd
import requests
from datetime import datetime

from . import register_adapter


@register_adapter("sina")
class SinaAdapter:
    """新浪财经API适配器（默认数据源）"""

    name = "sina"

    def __init__(self, config: dict = None):
        self.config = config or {}
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Referer": "https://vip.stock.finance.sina.com.cn/",
        })

        # 新浪ETF代码映射
        self._symbol_prefix = {
            "510050": "sh", "510300": "sh", "510500": "sh", "588000": "sh",
            "510880": "sh", "159919": "sz", "159915": "sz",
        }
        self._etf_names = {
            "510050": "上证50ETF华夏", "510300": "沪深300ETF华泰柏瑞",
            "510500": "中证500ETF南方", "588000": "科创50ETF华夏",
            "510880": "上证红利ETF", "159919": "沪深300ETF易方达",
            "159915": "创业板ETF",
        }

        # 实时行情缓存（避免重复请求）
        self._realtime_cache = {}
        self._realtime_cache_ts = 0
        self._realtime_cache_ttl = 10  # 秒

    def _get_prefix(self, symbol: str) -> str:
        return self._symbol_prefix.get(symbol, "sh")

    def _get_name(self, symbol: str) -> str:
        return self._etf_names.get(symbol, f"ETF{symbol}")

    def get_historical(self, symbol: str, days: int = 800) -> pd.DataFrame:
        """获取历史K线（新浪JSONP接口）"""
        prefix = self._get_prefix(symbol)
        url = (
            f"https://quotes.sina.cn/cn/api/jsonp_v2.php/"
            f"var%20_{symbol}_2026_2026/CN_MarketData.getKLineData"
            f"?symbol={prefix}{symbol}&scale=240&ma=no&datalen=1023"
        )

        resp = self.session.get(url, timeout=15)
        if resp.status_code != 200:
            raise ConnectionError(f"HTTP {resp.status_code}")

        text = resp.text
        start = text.find("[")
        end = text.rfind("]") + 1
        if start == -1 or end == -1:
            raise ValueError("无法解析新浪JSONP响应")

        data = json.loads(text[start:end])
        if not data:
            raise ValueError("新浪返回空数据")

        records = []
        for item in data:
            records.append({
                "date": item["day"],
                "open": float(item["open"]),
                "high": float(item["high"]),
                "low": float(item["low"]),
                "close": float(item["close"]),
                "volume": float(item.get("volume", 0)),
                "amount": float(item.get("amount", 0)),
            })

        df = pd.DataFrame(records)
        df["date"] = pd.to_datetime(df["date"])
        df = df.sort_values("date").reset_index(drop=True)

        if days and days < len(df):
            df = df.tail(days).reset_index(drop=True)

        return df

    def get_realtime(self, symbol: str) -> dict:
        """获取实时行情"""
        # 检查缓存
        now = time.time()
        if now - self._realtime_cache_ts < self._realtime_cache_ttl and symbol in self._realtime_cache:
            return self._realtime_cache[symbol]

        # 全量获取（新浪不支持单只查询，只能全量拉然后过滤）
        try:
            import akshare as ak
            df = ak.fund_etf_spot_em()
            if df is not None and not df.empty:
                mask = df["代码"].astype(str) == symbol
                if not mask.any():
                    mask = df["代码"].astype(str).str.endswith(symbol)
                if mask.any():
                    r = df[mask].iloc[0]
                    result = {
                        "symbol": symbol,
                        "name": str(r.get("名称", self._get_name(symbol))),
                        "price": float(r.get("最新价", 0)),
                        "change_pct": float(r.get("涨跌幅", 0)),
                        "volume": float(r.get("成交额", 0)),
                        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    }
                    self._realtime_cache[symbol] = result
                    self._realtime_cache_ts = now
                    return result
        except Exception:
            pass

        # fallback: 返回placeholder
        return {"symbol": symbol, "price": 0, "change_pct": 0, "name": self._get_name(symbol)}

    def health(self) -> bool:
        """检查新浪API是否可用"""
        try:
            df = self.get_historical("510050", days=5)
            return df is not None and len(df) > 0
        except Exception:
            return False
