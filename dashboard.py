"""
金箍棒量化仪表盘 — 单文件 Web UI
信息丰富 + 框架逻辑清晰
"""
import os
import sys
import json
import yaml
from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.resolve()
sys.path.insert(0, str(PROJECT_ROOT))

from utils.config_loader import load_config
from data.adapters import get_adapter, list_adapters
from data.data_loader import get_historical_data
from main import live_signal, load_all_hist_data
from strategies.consensus import analyze_consensus
from memory.memory_log import get_past_context, review_pending

HOST = "0.0.0.0"
PORT = int(os.environ.get("PORT", 8899))


class QuantDashboard(BaseHTTPRequestHandler):

    def do_GET(self):
        if self.path == "/":
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(self._render_dashboard().encode("utf-8"))
        elif self.path == "/api/signals":
            self._send_json(self._get_live_signals())
        elif self.path == "/api/memory":
            self._send_json(self._get_memory_stats())
        elif self.path == "/api/config":
            self._send_json(self._get_config_info())
        elif self.path == "/api/refresh":
            self._refresh_signals()
            self.send_response(302)
            self.send_header("Location", "/")
            self.end_headers()
        else:
            self.send_response(404)
            self.end_headers()

    def _send_json(self, data: dict):
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8"))

    # ─── 数据层 ───────────────────────────────────────────

    def _get_live_signals(self) -> dict:
        """运行实盘信号分析，返回结构化结果"""
        try:
            config = load_config()
            symbols = config.get("trading", {}).get("symbols", ["510050", "510300", "510500", "588000"])
            hist_data = load_all_hist_data(symbols, config)
            signals = []
            for sym in symbols:
                try:
                    sig = live_signal(sym, config, hist_data)
                    consensus = analyze_consensus(
                        sig.get("strategy_details", []),
                        sig.get("strength", 0),
                        sig.get("signal", "hold"),
                    )
                    sig["consensus"] = consensus
                    signals.append(sig)
                except Exception as e:
                    signals.append({"symbol": sym, "signal": "error", "error": str(e)})

            # 记忆上下文
            memory_ctx = get_past_context(max_entries=5)
            review = review_pending()

            return {
                "status": "ok",
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "signals": signals,
                "memory": review,
                "memory_ctx": memory_ctx,
            }
        except Exception as e:
            return {"status": "error", "error": str(e)}

    def _get_memory_stats(self) -> dict:
        """读取记忆统计"""
        try:
            memory_file = PROJECT_ROOT / "memory" / "trading_memory.md"
            if not memory_file.exists():
                return {"entries": 0, "resolved": 0, "accuracy": None}

            text = memory_file.read_text("utf-8")
            import re
            match = re.search(r"```json\n(.+?)\n```", text, re.DOTALL)
            if not match:
                return {"entries": 0, "resolved": 0}

            entries = json.loads(match.group(1))
            resolved = [e for e in entries if e.get("status") == "resolved"]
            correct = sum(1 for e in resolved if e.get("correct"))
            accuracy = round(correct / len(resolved) * 100, 1) if resolved else None

            return {
                "entries": len(entries),
                "resolved": len(resolved),
                "pending": sum(1 for e in entries if e.get("status") == "pending"),
                "correct": correct,
                "accuracy": accuracy,
                "recent": entries[-10:] if entries else [],
            }
        except Exception as e:
            return {"error": str(e)}

    def _get_config_info(self) -> dict:
        """返回配置信息"""
        try:
            config = load_config()
            strategies = config.get("strategies", {})
            symbols = config.get("trading", {}).get("symbols", [])
            return {
                "symbols": symbols,
                "strategies": {k: {kk: vv for kk, vv in v.items() if kk != "enabled"}
                               for k, v in strategies.items() if v.get("enabled")},
                "adapters": list_adapters(),
                "data_adapter": config.get("data_adapter", "sina"),
                "risk": config.get("risk", {}),
            }
        except Exception as e:
            return {"error": str(e)}

    def _refresh_signals(self):
        """手动触发信号刷新"""
        try:
            config = load_config()
            from main import main as run_main
            import argparse
            run_main()
        except Exception as e:
            print(f"[dashboard] 刷新失败: {e}")

    # ─── 渲染层 ───────────────────────────────────────────

    def _render_dashboard(self) -> str:
        """渲染完整仪表盘 HTML"""
        return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>金箍棒量化仪表盘</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500;600;700&family=Noto+Sans+SC:wght@300;400;500;600;700&display=swap" rel="stylesheet">
<style>
:root {{
  --bg-base: #0b1120;
  --bg-card: #131c2e;
  --bg-card-hover: #1a2744;
  --border: #1e3150;
  --text-primary: #e2e8f0;
  --text-secondary: #94a3b8;
  --text-muted: #64748b;
  --cyan: #22d3ee;
  --emerald: #34d399;
  --violet: #a78bfa;
  --amber: #fbbf24;
  --rose: #fb7185;
  --red: #f85149;
  --green: #3fb950;
  --yellow: #d29922;
  --gray: #8b949e;
}}
* {{ margin:0; padding:0; box-sizing:border-box; }}
body {{
  background: var(--bg-base);
  color: var(--text-primary);
  font-family: 'Noto Sans SC', sans-serif;
  min-height: 100vh;
}}
.mono {{ font-family: 'JetBrains Mono', monospace; }}

/* ── 头部 ── */
.header {{
  background: linear-gradient(135deg, #0f1a30 0%, #162240 100%);
  border-bottom: 1px solid var(--border);
  padding: 20px 30px;
  display: flex;
  align-items: center;
  justify-content: space-between;
}}
.header-title {{
  display: flex;
  align-items: center;
  gap: 14px;
}}
.header-title h1 {{
  font-size: 22px;
  font-weight: 700;
  background: linear-gradient(135deg, var(--cyan), var(--emerald));
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
}}
.header-title .subtitle {{
  font-size: 13px;
  color: var(--text-muted);
  -webkit-text-fill-color: var(--text-muted);
}}
.header-actions {{
  display: flex;
  align-items: center;
  gap: 16px;
}}
.header-time {{
  font-size: 13px;
  color: var(--text-secondary);
  font-family: 'JetBrains Mono', monospace;
}}
.btn {{
  background: var(--bg-card);
  border: 1px solid var(--border);
  color: var(--text-primary);
  padding: 8px 18px;
  border-radius: 6px;
  cursor: pointer;
  font-size: 13px;
  font-family: inherit;
  transition: all 0.2s;
}}
.btn:hover {{
  background: var(--bg-card-hover);
  border-color: var(--cyan);
}}
.btn-primary {{
  background: linear-gradient(135deg, rgba(34,211,238,0.15), rgba(52,211,153,0.15));
  border-color: var(--cyan);
}}
.btn-primary:hover {{
  background: linear-gradient(135deg, rgba(34,211,238,0.25), rgba(52,211,153,0.25));
}}

/* ── 布局 ── */
.container {{
  max-width: 1480px;
  margin: 0 auto;
  padding: 20px;
}}
.grid {{
  display: grid;
  gap: 16px;
}}
.grid-2 {{ grid-template-columns: 1fr 1fr; }}
.grid-4 {{ grid-template-columns: repeat(4, 1fr); }}
.grid-stats {{ grid-template-columns: repeat(6, 1fr); }}

/* ── 卡片 ── */
.card {{
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 18px;
  transition: all 0.2s;
}}
.card:hover {{
  border-color: rgba(34,211,238,0.3);
}}
.card-header {{
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 14px;
}}
.card-title {{
  font-size: 14px;
  font-weight: 600;
  color: var(--text-secondary);
  letter-spacing: 0.5px;
}}
.card-value {{
  font-size: 28px;
  font-weight: 700;
  font-family: 'JetBrains Mono', monospace;
}}
.card-label {{
  font-size: 12px;
  color: var(--text-muted);
  margin-top: 4px;
}}

/* ── 信号卡片 ── */
.signal-card {{
  border-left: 4px solid var(--gray);
}}
.signal-card.buy {{ border-left-color: var(--green); }}
.signal-card.sell {{ border-left-color: var(--red); }}
.signal-card.hold {{ border-left-color: var(--yellow); }}
.signal-card.error {{ border-left-color: var(--rose); }}

.signal-symbol {{
  font-size: 20px;
  font-weight: 700;
  font-family: 'JetBrains Mono', monospace;
}}
.signal-name {{
  font-size: 12px;
  color: var(--text-muted);
}}
.signal-tag {{
  display: inline-block;
  padding: 2px 10px;
  border-radius: 4px;
  font-size: 12px;
  font-weight: 600;
  font-family: 'JetBrains Mono', monospace;
}}
.signal-tag.buy {{ background: rgba(63,185,80,0.15); color: var(--green); }}
.signal-tag.sell {{ background: rgba(248,81,73,0.15); color: var(--red); }}
.signal-tag.hold {{ background: rgba(210,153,34,0.15); color: var(--yellow); }}

.signal-price {{
  font-size: 18px;
  font-weight: 600;
  font-family: 'JetBrains Mono', monospace;
}}
.signal-strength-bar {{
  height: 6px;
  border-radius: 3px;
  background: var(--bg-base);
  overflow: hidden;
  margin-top: 6px;
}}
.signal-strength-fill {{
  height: 100%;
  border-radius: 3px;
  transition: width 0.5s;
}}

/* 共识分析 */
.consensus-line {{
  font-size: 12px;
  margin: 3px 0;
  color: var(--text-secondary);
  line-height: 1.5;
}}
.consensus-bull {{ color: var(--green); }}
.consensus-bear {{ color: var(--red); }}
.consensus-neutral {{ color: var(--text-muted); }}
.consensus-tag {{
  display: inline-block;
  font-size: 11px;
  padding: 1px 8px;
  border-radius: 3px;
  font-family: 'JetBrains Mono', monospace;
  font-weight: 500;
}}
.consensus-tag.strong {{ background: rgba(63,185,80,0.2); color: var(--green); }}
.consensus-tag.moderate {{ background: rgba(210,153,34,0.2); color: var(--yellow); }}
.consensus-tag.weak {{ background: rgba(139,148,158,0.2); color: var(--gray); }}
.consensus-tag.conflicted {{ background: rgba(248,81,73,0.2); color: var(--red); }}

/* 策略明细表 */
.strategy-table {{
  width: 100%;
  border-collapse: collapse;
  font-size: 12px;
  margin-top: 12px;
}}
.strategy-table th {{
  text-align: left;
  padding: 6px 8px;
  color: var(--text-muted);
  font-weight: 500;
  border-bottom: 1px solid var(--border);
  font-size: 11px;
}}
.strategy-table td {{
  padding: 6px 8px;
  border-bottom: 1px solid rgba(30,49,80,0.5);
  font-family: 'JetBrains Mono', monospace;
  font-size: 11px;
}}
.strategy-table tr:last-child td {{ border: none; }}
.strategy-signal {{
  font-weight: 600;
  font-size: 11px;
}}

/* 记忆 */
.memory-item {{
  padding: 8px 0;
  border-bottom: 1px solid rgba(30,49,80,0.3);
  font-size: 13px;
  line-height: 1.5;
}}
.memory-item:last-child {{ border: none; }}
.memory-correct {{ color: var(--green); }}
.memory-wrong {{ color: var(--red); }}
.memory-pending {{ color: var(--yellow); }}

/* 配置表 */
.config-table {{
  width: 100%;
  font-size: 13px;
  border-collapse: collapse;
}}
.config-table td {{
  padding: 6px 10px;
  border-bottom: 1px solid rgba(30,49,80,0.3);
}}
.config-table td:first-child {{
  color: var(--text-muted);
  width: 140px;
}}

/* 响应式 */
@media (max-width: 1024px) {{
  .grid-4 {{ grid-template-columns: repeat(2, 1fr); }}
  .grid-stats {{ grid-template-columns: repeat(3, 1fr); }}
}}
@media (max-width: 640px) {{
  .grid-4, .grid-2, .grid-stats {{ grid-template-columns: 1fr; }}
  .header {{ flex-direction: column; gap: 12px; }}
}}
</style>
</head>
<body>

<div class="header">
  <div class="header-title">
    <div>
      <h1>⚔️ 金箍棒</h1>
      <div class="subtitle">多策略量化信号仪表盘</div>
    </div>
  </div>
  <div class="header-actions">
    <span class="header-time" id="currentTime">{datetime.now().strftime("%Y-%m-%d %H:%M:%S")}</span>
    <button class="btn btn-primary" onclick="location.reload()">⟳ 刷新</button>
    <a href="/api/refresh" class="btn">⚡ 重新分析</a>
  </div>
</div>

<div class="container">

  <!-- 加载状态 -->
  <div id="loading" style="text-align:center;padding:60px 0;color:var(--text-muted)">
    <div style="font-size:36px;margin-bottom:12px">⏳</div>
    <div>加载信号数据中...</div>
  </div>

  <!-- 主内容（初始隐藏） -->
  <div id="content" style="display:none">

    <!-- 统计栏 -->
    <div class="grid grid-stats" id="statsGrid"></div>

    <!-- ETF信号 + 记忆 -->
    <div class="grid grid-2" style="margin-top:16px">
      <div id="signalsPanel"></div>
      <div id="rightPanel"></div>
    </div>

    <!-- 底部：配置信息 -->
    <div class="grid grid-2" style="margin-top:16px">
      <div class="card" id="configCard"></div>
      <div class="card" id="memoryCard"></div>
    </div>

  </div>
</div>

<script>
const SYMBOL_NAMES = {{
  "510050": "上证50ETF", "510300": "沪深300ETF",
  "510500": "中证500ETF", "588000": "科创50ETF"
}};

async function loadData() {{
  try {{
    const [sigRes, memRes, cfgRes] = await Promise.all([
      fetch("/api/signals"),
      fetch("/api/memory"),
      fetch("/api/config")
    ]);
    const signals = await sigRes.json();
    const memory = await memRes.json();
    const config = await cfgRes.json();

    document.getElementById("loading").style.display = "none";
    document.getElementById("content").style.display = "block";

    renderStats(signals, memory);
    renderSignals(signals);
    renderRightPanel(signals);
    renderConfig(config);
    renderMemory(memory);
  }} catch(e) {{
    document.getElementById("loading").innerHTML =
      `<div style="color:var(--red);font-size:18px">❌ 加载失败: ${{e.message}}</div>` +
      `<div style="margin-top:10px;color:var(--text-muted);font-size:14px">` +
      `请确认运行了 <code style="background:#1a2744;padding:2px 6px;border-radius:4px">python dashboard.py</code></div>`;
  }}
}}

function renderStats(signals, memory) {{
  const sigs = signals.signals || [];
  const buyCount = sigs.filter(s => s.signal === 'buy').length;
  const sellCount = sigs.filter(s => s.signal === 'sell').length;
  const holdCount = sigs.filter(s => s.signal === 'hold').length;
  const errCount = sigs.filter(s => s.signal === 'error').length;
  const avgStrength = sigs.length > 0
    ? (sigs.reduce((a, s) => a + (s.strength || 0), 0) / sigs.length).toFixed(1)
    : 0;
  const accuracy = memory.accuracy !== null && memory.accuracy !== undefined
    ? memory.accuracy.toFixed(1)
    : '--';

  document.getElementById("statsGrid").innerHTML = `
    <div class="card"><div class="card-value" style="color:var(--cyan)">${{sigs.length}}</div><div class="card-label">标的数</div></div>
    <div class="card"><div class="card-value" style="color:var(--green)">${{buyCount}}</div><div class="card-label">买入</div></div>
    <div class="card"><div class="card-value" style="color:var(--red)">${{sellCount}}</div><div class="card-label">卖出</div></div>
    <div class="card"><div class="card-value" style="color:var(--yellow)">${{holdCount}}</div><div class="card-label">持有/中性</div></div>
    <div class="card"><div class="card-value" style="color:var(--amber)">${{avgStrength}}%</div><div class="card-label">平均强度</div></div>
    <div class="card"><div class="card-value" style="color:${{accuracy >= 50 ? 'var(--green)' : 'var(--text-muted)'}}">${{accuracy}}%</div><div class="card-label">历史准确率</div></div>
  `;
}}

function renderSignals(signals) {{
  const sigs = signals.signals || [];
  let html = `<div class="card"><div class="card-title" style="margin-bottom:14px">📊 ETF实时信号</div>`;
  sigs.forEach(s => {{
    const consensus = s.consensus || {{}};
    const cl = consensus.consensus_level || 'unknown';
    const sigClass = s.signal === 'buy' ? 'buy' : s.signal === 'sell' ? 'sell' : 'hold';
    const changeColor = s.change_pct >= 0 ? 'var(--green)' : 'var(--red)';
    const changeArrow = s.change_pct >= 0 ? '↑' : '↓';
    const strengthColor = s.strength >= 10 ? 'var(--green)' : s.strength >= 5 ? 'var(--yellow)' : 'var(--text-muted)';

    html += `<div class="card signal-card ${sigClass}" style="margin-bottom:12px">`;
    html += `<div style="display:flex;justify-content:space-between;align-items:start">`;
    html += `<div><span class="signal-symbol">${{s.symbol}}</span> <span class="signal-name">${{s.name || SYMBOL_NAMES[s.symbol] || ''}}</span></div>`;
    html += `<span class="signal-tag ${sigClass}">${{s.signal.toUpperCase()}}</span>`;
    html += `</div>`;

    html += `<div style="display:flex;justify-content:space-between;align-items:end;margin-top:10px">`;
    html += `<div><span class="signal-price">${{s.price ? s.price.toFixed(3) : '--'}}</span>`;
    html += ` <span style="font-size:13px;color:${{changeColor}}">${{s.change_pct >= 0 ? '+' : ''}}${{(s.change_pct || 0).toFixed(2)}}%${{changeArrow}}</span></div>`;
    html += `<div style="text-align:right"><span style="font-size:13px;color:${{strengthColor}};font-family:'JetBrains Mono'">强度 ${{(s.strength || 0).toFixed(1)}}%</span>`;
    html += `<div class="signal-strength-bar"><div class="signal-strength-fill" style="width:${{Math.min(s.strength || 0, 100)}}%;background:${{strengthColor}}"></div></div></div>`;
    html += `</div>`;

    // 共识分析
    html += `<div style="margin-top:10px;padding-top:10px;border-top:1px solid var(--border)">`;
    html += `<span class="consensus-tag ${{cl}}">${{cl.toUpperCase()}}</span>`;
    html += ` <span style="font-size:12px;color:var(--text-muted)">置信度 ${{(consensus.conviction || 0).toFixed(0)}}% · 质量 ${{consensus.signal_quality || '--'}}</span>`;
    html += `<div class="consensus-line" style="margin-top:6px">`;
    html += `<span class="consensus-bull">🟢 看多 ${{consensus.bull_count || 0}}</span>`;
    html += ` <span class="consensus-bear">🔴 看空 ${{consensus.bear_count || 0}}</span>`;
    html += ` <span class="consensus-neutral">⚪ 中性 ${{consensus.hold_count || 0}}</span>`;
    html += `</div>`;
    html += `<div style="font-size:11px;color:var(--text-muted);margin-top:4px;line-height:1.4">💡 ${{consensus.suggestion || ''}}</div>`;
    html += `</div>`;

    // 策略明细
    const details = s.strategy_details || [];
    if (details.length > 0) {{
      html += `<table class="strategy-table">`;
      html += `<tr><th>策略</th><th>信号</th><th>强度</th><th>说明</th></tr>`;
      details.forEach(d => {{
        const dSig = d.signal === 'buy' ? '🟢' : d.signal === 'sell' ? '🔴' : '⚪';
        const dStr = typeof d.strength === 'number' ? d.strength.toFixed(1) + '%' : '--';
        html += `<tr><td style="color:var(--cyan)">${{d.strategy}}</td><td class="strategy-signal" style="color:${{d.signal === 'buy' ? 'var(--green)' : d.signal === 'sell' ? 'var(--red)' : 'var(--yellow)'}}">${{dSig}} ${{d.signal}}</td><td>${{dStr}}</td><td style="color:var(--text-muted);font-size:10px">${{(d.detail || '').substring(0, 50)}}</td></tr>`;
      }});
      html += `</table>`;
    }}
    html += `</div>`;
  }});
  html += `</div>`;
  document.getElementById("signalsPanel").innerHTML = html;
}}

function renderRightPanel(signals) {{
  const memCtx = signals.memory_ctx || '(无历史记录)';
  html = `<div class="card"><div class="card-title" style="margin-bottom:14px">📋 近期决策回顾</div>`;
  if (memCtx.includes('近期决策回顾')) {{
    const lines = memCtx.split('\\n').filter(l => l.trim());
    lines.forEach(l => {{
      if (l.startsWith('##')) return;
      if (l.startsWith('📊')) {{
        html += `<div style="margin-top:12px;padding-top:10px;border-top:1px solid var(--border);font-size:13px;color:var(--cyan);font-weight:600">${{l}}</div>`;
        return;
      }}
      let cls = 'memory-pending';
      let icon = '⏳';
      if (l.includes('✅')) {{ cls = 'memory-correct'; icon = '✅'; }}
      else if (l.includes('❌')) {{ cls = 'memory-wrong'; icon = '❌'; }}
      html += `<div class="memory-item ${{cls}}">${{l}}</div>`;
    }});
  }} else {{
    html += `<div style="color:var(--text-muted);font-size:14px;padding:20px 0;text-align:center">${{memCtx}}</div>`;
  }}
  html += `</div>`;

  // 信号时间
  html += `<div class="card" style="margin-top:16px"><div class="card-title" style="margin-bottom:10px">⏰ 分析时间</div>`;
  html += `<div style="font-family:'JetBrains Mono';font-size:14px;color:var(--text-secondary)">${{signals.timestamp || '--'}}</div>`;
  html += `<div style="margin-top:10px;font-size:12px;color:var(--text-muted)">双击 <code style="background:#1a2744;padding:1px 6px;border-radius:3px">F5</code> 或点击"刷新"更新数据</div>`;
  html += `</div>`;

  document.getElementById("rightPanel").innerHTML = html;
}}

function renderConfig(config) {{
  const symbols = (config.symbols || ['510050','510300','510500','588000']).join(', ');
  const strategies = config.strategives || {{}};
  const adapters = (config.adapters || []).join(', ');
  const risk = config.risk || {{}};

  let html = `<div class="card-title" style="margin-bottom:14px">⚙️ 系统配置</div>`;
  html += `<table class="config-table">`;
  html += `<tr><td>标的</td><td style="font-family:'JetBrains Mono'">${{symbols}}</td></tr>`;
  html += `<tr><td>数据源</td><td style="font-family:'JetBrains Mono'">${{config.data_adapter || 'sina'}} (可用: ${{adapters}})</td></tr>`;
  html += `<tr><td>风控</td><td style="font-family:'JetBrains Mono'">止损 ${{risk.stop_loss || -5}}% · 追踪止损 ${{risk.trailing_stop ? '开' : '关'}}</td></tr>`;
  html += `<tr><td>策略数</td><td style="font-family:'JetBrains Mono'">${{Object.keys(strategies).length}} 个</td></tr>`;
  html += `</table>`;
  html += `<div style="margin-top:12px;font-size:12px;color:var(--text-muted)">策略参数：</div>`;
  html += `<table class="strategy-table">`;
  html += `<tr><th>策略</th><th>权重</th><th>参数</th></tr>`;
  Object.entries(strategies).forEach(([name, params]) => {{
    const paramStr = Object.entries(params).filter(([k]) => k !== 'enabled' && k !== 'weight')
      .map(([k, v]) => `${{k}}=${{v}}`).join(' ');
    html += `<tr><td style="color:var(--cyan)">${{name}}</td><td>${{((params.weight || 0) * 100).toFixed(0)}}%</td><td style="color:var(--text-muted);font-size:10px">${{paramStr}}</td></tr>`;
  }});
  html += `</table>`;
  document.getElementById("configCard").innerHTML = html;
}}

function renderMemory(memory) {{
  let html = `<div class="card-title" style="margin-bottom:14px">📈 决策记忆</div>`;
  html += `<div style="display:flex;gap:20px;margin-bottom:12px;flex-wrap:wrap">`;
  html += `<div><span style="color:var(--text-muted);font-size:12px">总决策</span><br><span class="mono" style="font-size:20px;font-weight:600">${{memory.entries || 0}}</span></div>`;
  html += `<div><span style="color:var(--text-muted);font-size:12px">已复盘</span><br><span class="mono" style="font-size:20px;font-weight:600">${{memory.resolved || 0}}</span></div>`;
  html += `<div><span style="color:var(--text-muted);font-size:12px">待复盘</span><br><span class="mono" style="font-size:20px;font-weight:600;color:var(--yellow)">${{memory.pending || 0}}</span></div>`;
  html += `<div><span style="color:var(--text-muted);font-size:12px">正确率</span><br><span class="mono" style="font-size:20px;font-weight:600;color:${{memory.accuracy >= 50 ? 'var(--green)' : 'var(--text-muted)'}}">${{memory.accuracy !== null ? memory.accuracy.toFixed(1) + '%' : '--'}}</span></div>`;
  html += `</div>`;

  const recent = memory.recent || [];
  if (recent.length > 0) {{
    html += `<div style="font-size:12px;color:var(--text-muted);margin-bottom:8px">最近决策：</div>`;
    recent.slice(-5).reverse().forEach(e => {{
      const icon = e.correct === true ? '✅' : e.correct === false ? '❌' : '⏳';
      const ret = e.actual_return !== null ? ` · ${{e.actual_return > 0 ? '+' : ''}}${{(e.actual_return || 0).toFixed(2)}}%` : '';
      const corCls = e.correct === true ? 'memory-correct' : e.correct === false ? 'memory-wrong' : 'memory-pending';
      html += `<div class="memory-item ${{corCls}}" style="font-size:12px">${{icon}} [${{e.date}}] ${{e.name || e.symbol}} → <strong>${{(e.signal || '').toUpperCase()}}</strong> (强度 ${{e.strength}}%)${{ret}}</div>`;
    }});
  }}
  html += `</div>`;
  document.getElementById("memoryCard").innerHTML = html;
}}

window.onload = loadData;
</script>
</body>
</html>"""

    def log_message(self, format, *args):
        pass  # 静默日志


def main():
    server = HTTPServer((HOST, PORT), QuantDashboard)
    print(f"\n  ⚔️  金箍棒量化仪表盘")
    print(f"  ─────────────────────")
    print(f"  🌐  http://localhost:{PORT}")
    print(f"  📡  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  ─────────────────────")
    print(f"  按 Ctrl+C 停止服务\n")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n  服务已停止")
        server.server_close()


if __name__ == "__main__":
    main()
