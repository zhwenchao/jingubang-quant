"""风控模块"""
import json
import os


def check_risk(signal: dict, previous: dict, config: dict) -> dict:
    """风控检查"""
    issues = []
    risk_level = "low"

    # 1. 连续同向信号检查
    if previous and previous.get("signal") == signal.get("signal"):
        prev_count = previous.get("consecutive_count", 1)
        if prev_count >= 3:
            issues.append(f"连续{prev_count + 1}次{signal.get('signal')}信号，建议谨慎")

    # 2. 价格异常检查
    price = signal.get("price", 0)
    last_price = previous.get("price", 0)
    if last_price > 0:
        pct = abs(price - last_price) / last_price
        if pct > 0.05:
            issues.append(f"价格波动{pct:.1%}超过5%，可能数据异常")

    # 3. 强度过低过滤（仅极端低强度才提示，避免震荡市大量误报）
    strength = signal.get("strength", 0)
    if strength < 5 and signal.get("signal") in ("buy", "sell"):
        issues.append(f"信号强度{strength:.0f}%过低，建议忽略")

    if len(issues) >= 2:
        risk_level = "high"
    elif len(issues) >= 1:
        risk_level = "medium"

    return {
        "pass": len(issues) == 0,
        "risk_level": risk_level,
        "issues": issues,
        "consecutive_count": previous.get("consecutive_count", 0) + 1 if previous and previous.get("signal") == signal.get("signal") else 1,
    }
