"""回测引擎模块"""
import os
import json
import numpy as np
import pandas as pd
from datetime import datetime
from data.data_loader import get_historical_data
from strategies.engine import STRATEGY_MAP


def run_backtest(symbol: str, config: dict, days: int = 800) -> dict:
    """对单个标的运行完整回测"""
    strategies_cfg = config.get("strategies", {})
    risk_cfg = config.get("risk", {})
    sl_pct = risk_cfg.get("stop_loss", -0.05)
    ts = risk_cfg.get("trailing_stop", True)

    # 获取数据
    df = get_historical_data(symbol, days)

    # 获取各策略信号
    signal_log = []
    weights = {}
    total_weight = 0

    for name, scfg in strategies_cfg.items():
        if not scfg.get("enabled", False):
            continue
        params = {k: scfg[k] for k in ["fast", "slow", "period", "threshold",
                                        "lookback", "low_threshold", "high_threshold",
                                        "entry_threshold", "exit_threshold"] if k in scfg}
        if name == "ma" and "fast" not in params:
            params["fast"] = scfg.get("fast", 3)
            params["slow"] = scfg.get("slow", 10)
        if name in STRATEGY_MAP:
            result = STRATEGY_MAP[name](df, params)
            signal_log.append({"strategy": name, **result})
            w = scfg.get("weight", 1.0)
            weights[name] = w
            total_weight += w

    # 综合信号
    composite = _composite_signal(signal_log, weights, total_weight)
    composite["symbol"] = symbol
    composite["timestamp"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    composite["strategy_details"] = signal_log

    # 模拟回测表现
    backtest = _simulate_backtest(df, config, signal_log, sl_pct, ts)

    return {
        "signal": composite,
        "backtest": backtest,
    }


def _composite_signal(signals: list, weights: dict, total_weight: float) -> dict:
    """综合多策略信号"""
    score = 0
    buy_strength = 0
    sell_strength = 0
    details = []

    for s in signals:
        name = s["strategy"]
        w = weights.get(name, 1.0) / total_weight
        if s["signal"] == "buy":
            score += w
            buy_strength += s.get("strength", 0) * w
        elif s["signal"] == "sell":
            score -= w
            sell_strength += s.get("strength", 0) * w
        details.append(f"{name}:{s['signal']}")

    if score > 0.3:
        signal = "buy"
        strength = buy_strength / max(len([s for s in signals if s["signal"] == "buy"]), 1)
    elif score < -0.3:
        signal = "sell"
        strength = sell_strength / max(len([s for s in signals if s["signal"] == "sell"]), 1)
    else:
        signal = "hold"
        strength = max(buy_strength, sell_strength) * 0.5

    return {
        "signal": signal,
        "strength": min(100, strength),
        "score": score,
        "details": " / ".join(details),
    }


def _simulate_backtest(df: pd.DataFrame, config: dict, signals: list,
                       sl_pct: float, trailing_stop: bool) -> dict:
    """简化回测模拟（基于日线）"""
    # 取最后300个交易日做回测
    test_df = df.tail(300).copy()
    test_df.index = range(len(test_df))

    position = 0
    capital = 100000
    holdings = 0
    peak = capital
    trades = []
    daily_returns = []

    for i in range(20, len(test_df)):
        window = test_df.iloc[:i + 1]

        # 根据当前窗口数据生成信号
        current_signals = []
        for s in signals:
            sig = s.get("signal", "hold")
            current_signals.append({"signal": sig})

        score = sum(1 for s in current_signals if s["signal"] == "buy") - \
                sum(1 for s in current_signals if s["signal"] == "sell")
        n = len(current_signals)

        price = test_df.iloc[i]["close"]

        # 止损检查
        if position > 0:
            entry_price = trades[-1]["price"] if trades else price
            pnl_pct = (price - entry_price) / entry_price
            if pnl_pct < sl_pct:
                # 止损
                holdings = 0
                trades[-1]["exit_price"] = price
                trades[-1]["pnl_pct"] = pnl_pct
                position = 0

            # 移动止损
            if trailing_stop and position > 0:
                peak = max(peak, price)
                drawdown = (price - peak) / peak
                if drawdown < sl_pct:
                    holdings = 0
                    trades[-1]["exit_price"] = price
                    trades[-1]["pnl_pct"] = (price - trades[-1]["price"]) / trades[-1]["price"]
                    position = 0

        # 交易信号
        if score > 0.5 * n and position <= 0:
            shares = int(capital * 0.95 / price / 100) * 100
            if shares > 0:
                cost = shares * price
                holdings = shares
                capital -= cost
                trades.append({"entry_date": test_df.iloc[i]["date"], "price": price, "shares": shares})
                position = 1
        elif score < -0.5 * n and position >= 0 and holdings > 0:
            capital += holdings * price
            trades[-1]["exit_price"] = price
            trades[-1]["pnl_pct"] = (price - trades[-1]["price"]) / trades[-1]["price"]
            holdings = 0
            position = 0

        # 每日净值
        total_value = capital + holdings * price
        daily_returns.append(total_value)

    # 最终平仓
    if holdings > 0:
        final_price = test_df.iloc[-1]["close"]
        capital += holdings * final_price
        holdings = 0

    total_return = (capital - 100000) / 100000
    n_days = len(daily_returns)
    daily_ret_series = pd.Series(daily_returns).pct_change().dropna()

    sharpe = 0
    if len(daily_ret_series) > 0 and daily_ret_series.std() > 0:
        sharpe = daily_ret_series.mean() / daily_ret_series.std() * np.sqrt(252)

    max_dd = 0
    peak_val = daily_returns[0]
    for v in daily_returns:
        peak_val = max(peak_val, v)
        dd = (v - peak_val) / peak_val
        max_dd = min(max_dd, dd)

    wins = sum(1 for t in trades if t.get("pnl_pct", 0) > 0)
    win_rate = wins / len(trades) if trades else 0

    return {
        "total_return_pct": round(total_return * 100, 2),
        "sharpe": round(sharpe, 2),
        "max_drawdown_pct": round(max_dd * 100, 2),
        "win_rate": round(win_rate * 100, 1),
        "total_trades": len(trades),
        "start_date": str(test_df.iloc[20]["date"].date()) if len(test_df) > 20 else "N/A",
        "end_date": str(test_df.iloc[-1]["date"].date()),
    }


def generate_report(results: dict, output_path: str = None):
    """生成回测报告Markdown"""
    signal = results.get("signal", {})
    bt = results.get("backtest", {})
    symbol = signal.get("symbol", "未知")
    details = signal.get("strategy_details", [])

    lines = [f"## {symbol} 回测报告", ""]
    lines.append(f"**综合信号**: {signal.get('signal', 'N/A')} | 强度: {signal.get('strength', 0):.1f}% | 评分: {signal.get('score', 0):+.2f}")
    lines.append(f"**时间**: {signal.get('timestamp', 'N/A')}")
    lines.append("")

    lines.append("### 回测表现")
    lines.append(f"| 指标 | 数值 |")
    lines.append(f"|------|------|")
    lines.append(f"| 总收益 | {bt.get('total_return_pct', 0):+.2f}% |")
    lines.append(f"| 夏普比率 | {bt.get('sharpe', 0):.2f} |")
    lines.append(f"| 最大回撤 | {bt.get('max_drawdown_pct', 0):.2f}% |")
    lines.append(f"| 胜率 | {bt.get('win_rate', 0):.1f}% |")
    lines.append(f"| 交易次数 | {bt.get('total_trades', 0)} |")
    lines.append(f"| 回测区间 | {bt.get('start_date', 'N/A')} ~ {bt.get('end_date', 'N/A')} |")
    lines.append("")

    lines.append("### 策略信号明细")
    for d in details:
        lines.append(f"- **{d.get('strategy', '?')}**: {d.get('signal', '?')} | 强度: {d.get('strength', 0):.1f}% | {d.get('detail', '')}")

    report = "\n".join(lines)

    if output_path:
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(report)

    return report
