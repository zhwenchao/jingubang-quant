"""金箍棒多Agent调度器 - 三太子的执行核心"""
import os
import sys
import json
import argparse
from datetime import datetime

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from utils.config_loader import load_config
from data.data_loader import get_etf_realtime
from main import live_signal
from backtest.engine import run_backtest, generate_report


def dispatch_data(symbols: list, config: dict) -> dict:
    """数据Agent - 实时行情"""
    results = {}
    for sym in symbols:
        data = get_etf_realtime(sym)
        results[sym] = data
    return results


def dispatch_signal(symbols: list, config: dict) -> dict:
    """策略Agent - 生成信号"""
    results = {}
    for sym in symbols:
        result = live_signal(sym, config)
        results[sym] = result
    return results


def dispatch_backtest(symbol: str, config: dict, days: int = 800) -> dict:
    """回测Agent - 执行回测"""
    try:
        result = run_backtest(symbol, config, days)
        return result
    except Exception as e:
        return {"symbol": symbol, "error": str(e)}


def dispatch_risk(signals: dict, config: dict) -> dict:
    """风控Agent - 评估风险"""
    assessments = {}
    for sym, signal in signals.items():
        risk_level = signal.get("risk_level", "unknown")
        issues = signal.get("risk_issues", [])
        assessments[sym] = {
            "risk_level": risk_level,
            "pass": signal.get("signal") != "error",
            "issues": issues,
        }
    return assessments


def dispatch_summary(signals: dict, risk: dict) -> str:
    """生成综合摘要报告（取代Agent的AI分析）"""
    lines = [f"## 📊 金箍棒量化报告", f"**时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", ""]
    lines.append("### 实盘信号")
    lines.append("| 标的 | 信号 | 价格 | 强度 | 风控 | 策略依据 |")
    lines.append("|------|------|------|------|------|---------|")
    for sym, s in signals.items():
        icon = {"buy": "🟢买入", "sell": "🔴卖出", "hold": "⚪持有", "error": "❌错误"}
        sig = s.get("signal", "?")
        risk_icon = {"low": "✅", "medium": "⚠️", "high": "🚨"}
        rl = risk.get(sym, {}).get("risk_level", "unknown")
        lines.append(f"| {sym} | {icon.get(sig, sig)} | {s.get('price', '?')} | {s.get('strength', 0):.0f}% | {risk_icon.get(rl, '?')} | {s.get('reason', '')} |")

    lines.append("")
    lines.append("### 风险提示")
    for sym, ra in risk.items():
        if ra.get("issues"):
            lines.append(f"- **{sym}**: {'; '.join(ra['issues'])}")

    return "\n".join(lines)


def scheduler_main():
    """调度器主入口"""
    parser = argparse.ArgumentParser(description="金箍棒多Agent调度器")
    parser.add_argument("--mode", choices=["live", "backtest", "full"], default="live")
    parser.add_argument("--symbols", nargs="+", default=["510050", "510300", "510500", "588000"])
    parser.add_argument("--days", type=int, default=800)
    args = parser.parse_args()

    config = load_config()
    symbols = args.symbols

    print(f"🚀 金箍棒调度器启动 [{args.mode.upper()}]")
    print(f"📅 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"📡 标的: {', '.join(symbols)}")
    print("-" * 50)

    # 1. 数据Agent - 行情获取
    print("📊 [数据Agent] 获取实时行情...")
    data = dispatch_data(symbols, config)

    # 2. 策略Agent - 信号生成
    print("🧠 [策略Agent] 计算信号...")
    signals = dispatch_signal(symbols, config)

    # 3. 风控Agent - 风险评估
    print("🛡️ [风控Agent] 风险评估...")
    risk = dispatch_risk(signals, config)

    # 4. 摘要报告
    print("📋 [汇总Agent] 生成报告...")
    report = dispatch_summary(signals, risk)
    print(report)

    # 保存报告
    reports_dir = config.get("paths", {}).get("reports_dir", "reports")
    os.makedirs(reports_dir, exist_ok=True)
    now = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_path = os.path.join(reports_dir, f"summary_{now}.md")
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(report)
    print(f"\n📄 报告已保存: {report_path}")

    return signals, risk, report


if __name__ == "__main__":
    scheduler_main()
