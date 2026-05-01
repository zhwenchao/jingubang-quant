#!/home/administrator/.hermes/hermes-agent/venv/bin/python3
"""
金箍棒记忆系统 — 决策日志 + 延迟复盘
借鉴 TradingAgents 的 trading_memory.md 模式

每次信号输出时记录，下次运行时复盘前次准确率。
"""
import json
import os
import re
from datetime import datetime, date
from pathlib import Path

MEMORY_DIR = Path(__file__).parent
MEMORY_FILE = MEMORY_DIR / "trading_memory.md"
REPORTS_DIR = MEMORY_DIR.parent / "reports"
SIGNALS_DIR = MEMORY_DIR.parent / "signals"

# 信号强度 → 看多/看空/中性
def _signal_bias(signal: str, strength: float) -> str:
    s = signal.lower()
    if s == "buy":
        return "bullish" if strength >= 5 else "bullish_weak"
    elif s == "sell":
        return "bearish" if strength >= 5 else "bearish_weak"
    return "neutral"

def _resolve_entry(entry: dict) -> dict:
    """
    解析一条 pending 决策的实际结果。
    比较预测价格 vs 下个交易日的实际价格（从最新信号文件读取）。
    """
    symbol = entry.get("symbol", "")
    predicted_direction = entry.get("signal", "")
    predicted_price = entry.get("price", 0)
    record_date = entry.get("date", "")

    # 找之后的最新信号文件
    latest_signal = _get_latest_signal(symbol)
    if not latest_signal:
        return {**entry, "status": "pending", "actual_return": None, "correct": None}

    actual_price = latest_signal.get("price", 0)
    if not actual_price or not predicted_price:
        return {**entry, "status": "pending", "actual_return": None, "correct": None}

    actual_return = (actual_price - predicted_price) / predicted_price * 100

    # 判断预测方向是否正确
    correct = None
    if predicted_direction == "buy":
        correct = actual_return > 0  # 看涨则实际涨了算对
    elif predicted_direction == "sell":
        correct = actual_return < 0  # 看跌则实际跌了算对
    else:
        correct = abs(actual_return) < 1.5  # 持有则波动小于1.5%算对

    return {
        **entry,
        "status": "resolved",
        "actual_price": round(actual_price, 3),
        "actual_return": round(actual_return, 2),
        "correct": correct,
    }


def _get_latest_signal(symbol: str) -> dict | None:
    """从 signals/ 目录读取某个标的最新信号"""
    signal_file = SIGNALS_DIR / f"{symbol}_signal.json"
    if signal_file.exists():
        try:
            return json.loads(signal_file.read_text(encoding="utf-8"))
        except Exception:
            return None
    return None


def store_decision(signals: list[dict]):
    """
    存储一次完整的信号输出到 memory。
    每次 signal 追加一条 pending 记录。
    """
    today = date.today().isoformat()

    # 读取历史
    history = _read_log()

    # 追加新条目
    for sig in signals:
        entry = {
            "date": today,
            "symbol": sig.get("symbol", ""),
            "name": sig.get("name", ""),
            "signal": sig.get("signal", ""),
            "strength": sig.get("strength", 0),
            "price": sig.get("price", 0),
            "change_pct": sig.get("change_pct", 0),
            "reason": sig.get("reason", ""),
            "risk_level": sig.get("risk_level", ""),
            "status": "pending",  # pending / resolved
            "actual_return": None,
            "correct": None,
        }
        history.append(entry)

    _write_log(history)
    print(f"[memory] 已记录 {len(signals)} 条决策到 {MEMORY_FILE}")


def review_pending():
    """
    复盘所有 pending 记录，更新实际收益率和正确性。
    返回复盘总结（用于注入到信号报告中）。
    """
    history = _read_log()
    resolved_count = 0
    correct_count = 0

    for entry in history:
        if entry.get("status") != "pending":
            if entry.get("correct") is True:
                correct_count += 1
                resolved_count += 1
            elif entry.get("correct") is False:
                resolved_count += 1
            continue

        # 尝试解析 pending 条目
        resolved = _resolve_entry(entry)
        if resolved.get("status") == "resolved":
            resolved_count += 1
            if resolved.get("correct"):
                correct_count += 1
            entry.update(resolved)

    _write_log(history)

    total = len(history)
    pending = sum(1 for e in history if e.get("status") == "pending")
    accuracy = round(correct_count / resolved_count * 100, 1) if resolved_count > 0 else None

    print(f"[memory] 复盘完成：共{total}条，已解决{resolved_count}条，正确率{accuracy}%")
    return {
        "total": total,
        "resolved": resolved_count,
        "pending": pending,
        "correct": correct_count,
        "accuracy": accuracy,
    }


def get_past_context(symbol: str = None, max_entries: int = 5) -> str:
    """
    获取最近N条记忆上下文，用于注入 prompt。
    包含 pending 和 resolved 的条目，resolved 的带上回测结果。
    """
    history = _read_log()
    if not history:
        return "（无历史决策记录）"

    if symbol:
        filtered = [e for e in history if e.get("symbol") == symbol]
    else:
        filtered = history

    recent = filtered[-max_entries:]
    if not recent:
        return "（无相关历史决策记录）"

    lines = ["## 近期决策回顾", ""]
    for e in recent:
        status_mark = "⏳" if e.get("status") == "pending" else ("✅" if e.get("correct") else "❌")
        ret = ""
        if e.get("actual_return") is not None:
            arrow = "↑" if e.get("actual_return", 0) > 0 else "↓"
            ret = f" | 实际收益: {e['actual_return']:+.2f}%{arrow}"
        lines.append(
            f"{status_mark} **{e['date']}** {e['name']}({e['symbol']}) "
            f"→ **{e['signal'].upper()}** (强度{e['strength']}%){ret}"
        )

    # 准确率统计
    resolved = [e for e in history if e.get("status") == "resolved"]
    if resolved:
        correct = sum(1 for e in resolved if e.get("correct"))
        accuracy = round(correct / len(resolved) * 100, 1)
        lines.append("")
        lines.append(f"📊 历史准确率: {accuracy}% ({correct}/{len(resolved)})")

    return "\n".join(lines)


def _read_log() -> list[dict]:
    """读取 trading_memory.md 并解析为结构化数据"""
    if not MEMORY_FILE.exists():
        return []
    try:
        text = MEMORY_FILE.read_text(encoding="utf-8")
        # 解析 JSON 块
        match = re.search(r"```json\n(.+?)\n```", text, re.DOTALL)
        if match:
            return json.loads(match.group(1))
        return []
    except Exception:
        return []


def _write_log(entries: list[dict]):
    """原子写入 memory 文件"""
    today = date.today().isoformat()
    content = f"""# 金箍棒量化决策日志

> 自动记录每次信号输出，下次运行时自动复盘实际收益率。
> 格式借鉴 TradingAgents 的 trading_memory.md。

## 统计

- 总决策数: {len(entries)}
- 已复盘: {sum(1 for e in entries if e.get('status') == 'resolved')}
- 待复盘: {sum(1 for e in entries if e.get('status') == 'pending')}
- 最后更新: {today}

## 决策记录

```json
{json.dumps(entries, ensure_ascii=False, indent=2)}
```
"""
    # 原子写入
    tmp = MEMORY_FILE.with_suffix(".md.tmp")
    tmp.write_text(content, encoding="utf-8")
    tmp.replace(MEMORY_FILE)
