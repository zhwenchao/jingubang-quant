"""金箍棒量化交易系统 - 主入口"""
import os
import sys
import argparse
import json
from datetime import datetime

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from utils.config_loader import load_config
from data.data_loader import (
    get_historical_data,
    get_etf_realtime,
    save_signal,
    load_previous_signal,
)
from strategies.engine import STRATEGY_MAP
from risk.checker import check_risk


def live_signal(symbol: str, config: dict, hist_data: dict = None) -> dict:
    """生成单个标的最新信号（支持预加载数据）"""
    strategies_cfg = config.get("strategies", {})
    signals_dir = config.get("paths", {}).get("signals_dir", "signals")

    # 实时行情
    realtime = get_etf_realtime(symbol)
    price = realtime.get("price", 0)

    # 使用预加载数据或重新获取
    if hist_data and symbol in hist_data:
        df = hist_data[symbol]
    else:
        days_needed = max(
            scfg.get("lookback", 20) for scfg in strategies_cfg.values()
            if scfg.get("enabled", False)
        ) + 50
        try:
            df = get_historical_data(symbol, days_needed)
        except Exception as e:
            return {"symbol": symbol, "signal": "error", "error": str(e), "price": price}

    # 各策略打分
    signal_log = []
    weights = {}
    total_weight = 0

    for name, scfg in strategies_cfg.items():
        if not scfg.get("enabled", False):
            continue
        if name in STRATEGY_MAP:
            params = {k: scfg[k] for k in scfg if k not in ("enabled", "weight")}
            result = STRATEGY_MAP[name](df, params)
            signal_log.append({"strategy": name, **result})
            w = scfg.get("weight", 1.0)
            weights[name] = w
            total_weight += w

    # 综合信号
    composite = _composite_signal(signal_log, weights, total_weight)

    # 风控检查
    previous = load_previous_signal(symbol, signals_dir)
    risk = check_risk({"signal": composite.get("signal"), "strength": composite.get("strength"),
                        "price": price}, previous, config)

    result = {
        "symbol": symbol,
        "name": realtime.get("name", ""),
        "signal": composite.get("signal", "hold"),
        "strength": round(composite.get("strength", 0), 2),
        "price": price,
        "change_pct": realtime.get("change_pct", 0),
        "risk_level": risk.get("risk_level", "low"),
        "risk_issues": risk.get("issues", []),
        "reason": composite.get("details", ""),
        "strategy_details": signal_log,
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }

    save_signal(symbol, result, signals_dir)
    return result


def load_all_hist_data(symbols: list, config: dict) -> dict:
    """一次性加载所有标的的历史数据（减少API调用）"""
    strategies_cfg = config.get("strategies", {})
    days_needed = max(
        scfg.get("lookback", 20) for scfg in strategies_cfg.values()
        if scfg.get("enabled", False)
    ) + 50
    result = {}
    for sym in symbols:
        try:
            result[sym] = get_historical_data(sym, days_needed)
            print(f"  ✓ {sym}: {len(result[sym])}条K线")
        except Exception as e:
            print(f"  ✗ {sym}: {e}")
    return result


def _composite_signal(signals: list, weights: dict, total_weight: float) -> dict:
    """综合多策略信号"""
    score = 0
    buy_s = 0
    sell_s = 0
    details = []

    for s in signals:
        name = s["strategy"]
        w = weights.get(name, 1.0) / total_weight if total_weight > 0 else 0
        if s["signal"] == "buy":
            score += w
            buy_s += s.get("strength", 0) * w
        elif s["signal"] == "sell":
            score -= w
            sell_s += s.get("strength", 0) * w
        details.append(f"{name}:{s['signal']}({s.get('strength',0):.0f}%)")

    if score > 0.2:
        signal = "buy"
        strength = buy_s / max(sum(1 for s in signals if s["signal"] == "buy"), 1)
    elif score < -0.2:
        signal = "sell"
        strength = sell_s / max(sum(1 for s in signals if s["signal"] == "sell"), 1)
    else:
        signal = "hold"
        strength = max(buy_s, sell_s) * 0.5

    return {"signal": signal, "strength": min(100, strength), "details": " | ".join(details)}


def main():
    """主入口"""
    parser = argparse.ArgumentParser(description="金箍棒量化交易系统")
    parser.add_argument("--mode", choices=["live", "backtest"], default="live")
    parser.add_argument("--symbols", nargs="+", default=["510050", "510300", "510500", "588000"])
    parser.add_argument("--days", type=int, default=800)
    parser.add_argument("--config", default="")
    args = parser.parse_args()

    config = load_config(args.config)
    reports_dir = config.get("paths", {}).get("reports_dir", "reports")
    os.makedirs(reports_dir, exist_ok=True)

    if args.mode == "live":
        print("📡 [金箍棒] 加载历史数据...")
        hist_data = load_all_hist_data(args.symbols, config)

        print(f"\n📊 生成信号...")
        signals = []
        for symbol in args.symbols:
            try:
                result = live_signal(symbol, config, hist_data)
                signals.append(result)
            except Exception as e:
                print(f"[{symbol}] 异常: {e}")
                signals.append({"symbol": symbol, "signal": "error", "error": str(e)})

        # 输出汇总报告
        now = datetime.now().strftime("%Y%m%d_%H%M%S")
        summary_path = os.path.join(reports_dir, f"live_{now}.json")
        with open(summary_path, "w", encoding="utf-8") as f:
            json.dump(signals, f, ensure_ascii=False, indent=2, default=str)

        print("\\n## 实盘信号汇总")
        print(f"| 标的 | 信号 | 价格 | 强度 | 涨跌幅 |")
        print(f"|------|------|------|------|--------|")
        for s in signals:
            icon = {"buy": "🟢", "sell": "🔴", "hold": "⚪", "error": "❌"}
            sig = s.get("signal", "?")
            print(f"| {s.get('symbol','?')} {icon.get(sig,'')} | {sig} | {s.get('price','?')} | {s.get('strength',0):.0f}% | {s.get('change_pct',0):+.2f}% |")

        # 信号裁决器：多空共识分析
        try:
            from strategies.consensus import analyze_consensus
            print(f"\n## 多空辩论")
            for s in signals:
                if s.get("signal") in ("error",):
                    continue
                details = s.get("strategy_details", [])
                consensus = analyze_consensus(details, s.get("strength", 0), s.get("signal", "hold"))
                icon = {"strong": "🟢", "moderate": "🟡", "weak": "⚪", "conflicted": "🔴", "unknown": "⚪"}
                sym = s.get("symbol", "?")
                name = s.get("name", "")
                print(f"\n{icon.get(consensus['consensus_level'], '⚪')} **{sym} {name}**")
                print(f"  共识: {consensus['consensus_level']} | 置信度: {consensus['conviction']}% | 质量: {consensus['signal_quality']}")
                print(f"  看多 {consensus['bull_count']} | 看空 {consensus['bear_count']} | 中性 {consensus['hold_count']}")
                print(f"  🟢 {consensus['bull_case']}")
                print(f"  🔴 {consensus['bear_case']}")
                print(f"  💡 {consensus['suggestion']}")
                # 标记分歧
                if consensus['consensus_level'] == "conflicted":
                    print(f"  ⚠️ 多空分歧，观望为主")
        except Exception as e:
            print(f"[consensus] 分析失败: {e}")

        # 记录到决策记忆系统
        try:
            sys.path.insert(0, os.path.join(PROJECT_ROOT, "memory"))
            from memory_log import store_decision, review_pending
            store_decision(signals)
            review_pending()
        except Exception as e:
            print(f"[memory] 记录失败: {e}")

        # 输出记忆上下文摘要
        try:
            from memory_log import get_past_context
            ctx = get_past_context()
            if len(ctx) > 20:
                print(f"\n📋 {ctx}")
        except Exception:
            pass
    else:
        # 回测模式
        from backtest.engine import run_backtest, generate_report
        signals = []
        for symbol in args.symbols:
            result = run_backtest(symbol, config, args.days)
            signals.append(result)
            print(f"[{symbol}] 回测完成: {result.get('backtest', {}).get('total_return_pct', '?')}%")

        now = datetime.now().strftime("%Y%m%d_%H%M%S")
        summary_path = os.path.join(reports_dir, f"backtest_{now}.json")
        with open(summary_path, "w", encoding="utf-8") as f:
            json.dump(signals, f, ensure_ascii=False, indent=2, default=str)
        print(f"\n报告已保存: {summary_path}")

    return signals


if __name__ == "__main__":
    main()
