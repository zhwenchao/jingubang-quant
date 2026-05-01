# Jingubang-Quant (金箍棒量化交易系统)

AI多智能体量化交易系统。
- 多Agent调度：数据Agent → 策略Agent → 风控Agent → 汇总
- 4种策略：均线(3/10)、动量(5日)、波动率(20日)、RSRS(18日)
- 实盘信号 + 回测验证
- 风控：止损-5%、移动止损、连续信号过滤

## 使用

```bash
# 实盘信号
python main.py --mode live --symbols 510050 510300 510500 588000

# 多Agent调度
python scheduler.py --mode live

# 回测
python main.py --mode backtest --symbols 510050 --days 800
```
