"""
金箍棒信号裁决器 — 多空对抗 + 共识分析
借鉴 TradingAgents 的 Bull/Bear Researcher 辩论机制

输入：4个策略的原始信号
输出：共识分析 + 多空理由对比
"""
import json
from typing import Any


def analyze_consensus(strategy_details: list[dict], total_strength: float, final_signal: str) -> dict:
    """
    分析4个策略之间的共识/分歧程度。

    输入 strategy_details 格式：
    [{"strategy": "ma", "signal": "buy", "strength": 4.9, "detail": "..."}, ...]

    输出：
    {
        "consensus_level": "strong" | "moderate" | "weak" | "conflicted",
        "bull_count": int,    # 看多策略数
        "bear_count": int,    # 看空策略数
        "hold_count": int,    # 中性策略数
        "conviction": float,  # 置信度 0-100
        "bull_case": str,     # 看多理由摘要
        "bear_case": str,     # 看空理由摘要
        "signal_quality": "high" | "medium" | "low",
        "suggestion": str,    # 操作建议
    }
    """
    if not strategy_details:
        return _empty_result("无策略信号输入")

    bull_count = sum(1 for s in strategy_details if s.get("signal") == "buy")
    bear_count = sum(1 for s in strategy_details if s.get("signal") == "sell")
    hold_count = sum(1 for s in strategy_details if s.get("signal") == "hold")

    total = len(strategy_details)
    bull_ratio = bull_count / total if total > 0 else 0
    bear_ratio = bear_count / total if total > 0 else 0

    # 共识程度
    if bull_count == total:
        consensus_level = "strong"
        conviction = min(100, total_strength * 3 + 20)  # 全一致，置信度更高
    elif bear_count == total:
        consensus_level = "strong"
        conviction = min(100, total_strength * 3 + 20)
    elif bull_count > bear_count and bull_ratio >= 0.75:
        consensus_level = "moderate"
        conviction = min(80, total_strength * 2 + 10)
    elif bear_count > bull_count and bear_ratio >= 0.75:
        consensus_level = "moderate"
        conviction = min(80, total_strength * 2 + 10)
    elif bull_count == bear_count or (bull_count > 0 and bear_count > 0):
        consensus_level = "conflicted"
        conviction = max(5, total_strength * 0.5)
    else:
        consensus_level = "weak"
        conviction = max(10, total_strength * 0.5)

    # 多空理由
    bull_reasons = [s.get("detail", "") for s in strategy_details if s.get("signal") == "buy"]
    bear_reasons = [s.get("detail", "") for s in strategy_details if s.get("signal") == "sell"]

    # 提取看多方/看空方的策略名称
    bull_strategies = [s["strategy"] for s in strategy_details if s.get("signal") == "buy"]
    bear_strategies = [s["strategy"] for s in strategy_details if s.get("signal") == "sell"]
    hold_strategies = [s["strategy"] for s in strategy_details if s.get("signal") == "hold"]

    bull_case = _summarize_case("看多", bull_strategies, bull_reasons) if bull_reasons else "（无策略看多）"
    bear_case = _summarize_case("看空", bear_strategies, bear_reasons) if bear_reasons else "（无策略看空）"

    # 信号质量
    if conviction >= 60 and consensus_level in ("strong", "moderate"):
        signal_quality = "high"
    elif conviction >= 30:
        signal_quality = "medium"
    else:
        signal_quality = "low"

    # 操作建议
    if consensus_level == "strong" and final_signal == "buy":
        suggestion = "🟢 强共识看多 — 策略一致，考虑执行"
    elif consensus_level == "strong" and final_signal == "sell":
        suggestion = "🔴 强共识看空 — 策略一致，考虑减仓"
    elif consensus_level == "conflicted":
        suggestion = "🟡 多空分歧 — 策略不一致，观望为主"
    elif final_signal == "hold":
        suggestion = "⚪ 策略中性 — 无明确方向，继续持有"
    elif consensus_level in ("weak", "moderate") and final_signal == "buy":
        suggestion = "🟢 弱偏多 — 方向偏多但力度不足，轻仓试探"
    elif consensus_level in ("weak", "moderate") and final_signal == "sell":
        suggestion = "🔴 弱偏空 — 方向偏空但力度不足，控制仓位"
    else:
        suggestion = "⚪ 建议观望"

    return {
        "consensus_level": consensus_level,
        "bull_count": bull_count,
        "bear_count": bear_count,
        "hold_count": hold_count,
        "conviction": round(conviction, 1),
        "signal_quality": signal_quality,
        "bull_case": bull_case,
        "bear_case": bear_case,
        "bull_strategies": bull_strategies,
        "bear_strategies": bear_strategies,
        "hold_strategies": hold_strategies,
        "suggestion": suggestion,
    }


def _summarize_case(direction: str, strategies: list[str], details: list[str]) -> str:
    """生成简洁的多/空理由摘要"""
    if not strategies:
        return f"{direction}（无策略支持）"

    # 按策略类型分组
    ma_detail = [d for s, d in zip(strategies, details) if s == "ma"]
    momentum_detail = [d for s, d in zip(strategies, details) if s == "momentum"]
    volatility_detail = [d for s, d in zip(strategies, details) if s == "volatility"]
    rsrs_detail = [d for s, d in zip(strategies, details) if s == "rsrs"]

    parts = []
    if ma_detail:
        parts.append(f"均线({len(ma_detail)}): {'; '.join(ma_detail[:1])}")  # 只取第一条
    if momentum_detail:
        parts.append(f"动量({len(momentum_detail)}): {'; '.join(momentum_detail[:1])}")
    if volatility_detail:
        parts.append(f"波动率({len(volatility_detail)}): {'; '.join(volatility_detail[:1])}")
    if rsrs_detail:
        parts.append(f"RSRS({len(rsrs_detail)}): {'; '.join(rsrs_detail[:1])}")

    return f"{direction}策略({','.join(strategies)}): {' | '.join(parts)}"


def _empty_result(reason: str) -> dict:
    return {
        "consensus_level": "unknown",
        "bull_count": 0, "bear_count": 0, "hold_count": 0,
        "conviction": 0, "signal_quality": "low",
        "bull_case": "无数据", "bear_case": "无数据",
        "bull_strategies": [], "bear_strategies": [], "hold_strategies": [],
        "suggestion": f"⚪ {reason}",
    }
