# XXYY + AVE 联合扫描任务

## 任务流程

```
Phase1 (XXYY初筛，每5秒):
  获取SOL/BSC NEW + ALMOST代币
    → 流动性 > $8,000
    → 市值 $800k - $10M
    → Top10 Holder < 35%
    → 持币人数 > 50
    → 成交量 > $30,000
  → 通过 → 数据库1号
  → 不通过 → 过滤

Phase2 (AVE KOL验证，每5秒):
  扫描数据库1号代币
    → 5分钟内买 < 卖
    → KOL钱包买入数量 > 2
    → KOL钱包买入金额 > $100
    → KOL未实现盈利 < 10%
    → KOL购买时间 < 5分钟
  → 通过 → 数据库2号（待买入）
  → 不通过 → 冷却30秒，重复验证3次 → 数据库4号
```

## 数据库

| 数据库 | 说明 | 状态 |
|--------|------|------|
| db1 | XXYY初筛通过的代币 | 活跃 |
| db2 | KOL验证达标的代币 | 待人工确认 |
| db3 | 已买入持仓 | 人工操作 |
| db4 | KOL验证不通过的代币 | 归档 |

## 启动

```bash
cd /root/.openclaw/workspace/xxyy-ave-scan-task
python3 scan_task.py
```

## XXYY过滤指标

- `liquidity_min`: 8000
- `marketcap_min`: 800000
- `marketcap_max`: 10000000
- `top10_holder_max`: 35
- `holder_min`: 50
- `volume_min`: 30000

## AVE KOL验证指标

- `buy_lt_sell_ratio_5m`: true
- `kol_buy_count_min`: 2
- `kol_buy_amount_min`: 100
- `kol_unrealized_profit_max`: 10
- `kol_buy_time_max_minutes`: 5
