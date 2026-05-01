"""策略模块 - 多种量化策略"""
import numpy as np
import pandas as pd


def ma_strategy(df: pd.DataFrame, params: dict) -> dict:
    """移动均线策略"""
    fast = params.get("fast", 3)
    slow = params.get("slow", 10)
    if len(df) < slow + 1:
        return {"signal": "hold", "strength": 0, "detail": "数据不足"}

    df = df.copy()
    df["ma_fast"] = df["close"].rolling(fast).mean()
    df["ma_slow"] = df["close"].rolling(slow).mean()

    price = df["close"].iloc[-1]
    ma_f = df["ma_fast"].iloc[-1]
    ma_s = df["ma_slow"].iloc[-1]
    prev_f = df["ma_fast"].iloc[-2]
    prev_s = df["ma_slow"].iloc[-2]

    diff_pct = (ma_f - ma_s) / ma_s * 100 if ma_s != 0 else 0
    strength = min(100, max(0, abs(diff_pct) * 20))

    # 金叉/死叉判断
    if prev_f <= prev_s and ma_f > ma_s:
        return {"signal": "buy", "strength": strength, "detail": f"金叉(快{fast}慢{slow}):价格{price:.3f}>快线{ma_f:.3f}>慢线{ma_s:.3f}"}
    elif prev_f >= prev_s and ma_f < ma_s:
        return {"signal": "sell", "strength": min(strength, 80), "detail": f"死叉(快{fast}慢{slow}):价格{price:.3f}<快线{ma_f:.3f}<慢线{ma_s:.3f}"}
    elif price > ma_f and price > ma_s:
        return {"signal": "buy", "strength": strength * 0.5, "detail": f"上行(快{fast}慢{slow}):价格{price:.3f}>快线{ma_f:.3f}>慢线{ma_s:.3f}"}
    elif price < ma_f and price < ma_s:
        return {"signal": "sell", "strength": strength * 0.5, "detail": f"下行(快{fast}慢{slow}):价格{price:.3f}<快线{ma_f:.3f}<慢线{ma_s:.3f}"}
    return {"signal": "hold", "strength": strength, "detail": f"价格{price:.3f},快线{ma_f:.3f},慢线{ma_s:.3f}"}


def momentum_strategy(df: pd.DataFrame, params: dict) -> dict:
    """动量策略"""
    period = params.get("period", 5)
    threshold = params.get("threshold", 0.005)
    if len(df) < period + 1:
        return {"signal": "hold", "strength": 0, "detail": "数据不足"}

    df = df.copy()
    df["ret"] = df["close"].pct_change(period)
    mom = df["ret"].iloc[-1]
    strength = min(100, max(0, abs(mom) * 100))

    if mom > threshold:
        return {"signal": "buy", "strength": strength, "detail": f"{period}日动量{mom:+.2%}>阈值{threshold:+.1%}"}
    elif mom < -threshold:
        return {"signal": "sell", "strength": strength, "detail": f"{period}日动量{mom:+.2%}<阈值{-threshold:+.1%}"}
    return {"signal": "hold", "strength": strength * 0.3, "detail": f"{period}日动量{mom:+.2%},无显著方向"}


def volatility_strategy(df: pd.DataFrame, params: dict) -> dict:
    """波动率策略 - 低波做多，高波做空"""
    lookback = params.get("lookback", 20)
    low_th = params.get("low_threshold", 0.15)
    high_th = params.get("high_threshold", 0.35)
    if len(df) < lookback + 1:
        return {"signal": "hold", "strength": 0, "detail": "数据不足"}

    df = df.copy()
    df["ret"] = df["close"].pct_change()
    df["vol"] = df["ret"].rolling(lookback).std() * np.sqrt(252)
    vol = df["vol"].iloc[-1] if not pd.isna(df["vol"].iloc[-1]) else 0.2

    if vol < low_th:
        return {"signal": "buy", "strength": (1 - vol / low_th) * 100, "detail": f"年化波动率{vol:.1%}<低波阈值{low_th:.0%}"}
    elif vol > high_th:
        return {"signal": "sell", "strength": min(100, (vol - high_th) * 200), "detail": f"年化波动率{vol:.1%}>高波阈值{high_th:.0%}"}
    return {"signal": "hold", "strength": 30, "detail": f"年化波动率{vol:.1%},介于阈值之间"}


def rsrs_strategy(df: pd.DataFrame, params: dict) -> dict:
    """RSRS(阻力支撑相对强度)策略"""
    lookback = params.get("lookback", 18)
    entry = params.get("entry_threshold", 0.5)
    exit_th = params.get("exit_threshold", -0.3)
    if len(df) < lookback + 1:
        return {"signal": "hold", "strength": 0, "detail": "数据不足"}

    df = df.copy()
    highs = df["high"].values
    lows = df["low"].values

    slope_list = []
    for i in range(lookback, len(highs)):
        x = lows[i - lookback:i]
        y = highs[i - lookback:i]
        if np.std(x) == 0 or np.std(y) == 0:
            continue
        corr = np.corrcoef(x, y)[0, 1]
        std_x = np.std(x)
        std_y = np.std(y)
        beta = corr * std_y / std_x
        slope_list.append(beta)

    if len(slope_list) < 2:
        return {"signal": "hold", "strength": 0, "detail": "RSRS数据不足"}

    beta_series = pd.Series(slope_list)
    z_score = (beta_series.iloc[-1] - beta_series.mean()) / beta_series.std() if beta_series.std() > 0 else 0
    strength = min(100, max(0, abs(z_score) * 30))

    if z_score > entry:
        return {"signal": "buy", "strength": strength, "detail": f"RSRS beta={beta_series.iloc[-1]:.2f}, Z={z_score:.2f}>入场{entry}"}
    elif z_score < exit_th:
        return {"signal": "sell", "strength": strength, "detail": f"RSRS beta={beta_series.iloc[-1]:.2f}, Z={z_score:.2f}<退出{exit_th}"}
    return {"signal": "hold", "strength": max(strength, 10), "detail": f"RSRS beta={beta_series.iloc[-1]:.2f}, Z={z_score:.2f}"}


STRATEGY_MAP = {
    "ma": ma_strategy,
    "momentum": momentum_strategy,
    "volatility": volatility_strategy,
    "rsrs": rsrs_strategy,
}
