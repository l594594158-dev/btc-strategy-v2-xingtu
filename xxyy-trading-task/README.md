# XXYY 自动交易任务

## 📁 文件结构

```
xxyy-trading-task/
├── config.json          # 任务配置
├── trading_task.py     # 主交易脚本
├── 交易任务汇报.md      # 交易记录通知
├── databases/
│   ├── db1.json        # 数据库1号-待扫描
│   ├── db2.json        # 数据库2号-待买入
│   ├── db3.json        # 数据库3号-已买入
│   └── db4.json        # 数据库4号-不满足
└── README.md
```

## ⚙️ 配置说明

### config.json
- `scan_interval_seconds`: 扫描间隔（默认3秒）
- `liquidity_threshold_usd`: 流动性阈值（默认6000 USD）
- `chains.bsc.enabled`: 是否启用BSC链
- `chains.bsc.buy_amount`: 买入金额（BNB）

## 🚀 使用方法

### 启动任务
```bash
cd /root/.openclaw/workspace/xxyy-trading-task
python3 trading_task.py
```

### 添加代币到数据库2号
手动编辑 `databases/db2.json`，添加代币：
```json
{
  "tokenAddress": "代币合约地址",
  "chain": "bsc",
  "symbol": "代币符号",
  "add_time": "添加时间"
}
```

### 查看交易记录
打开 `交易任务汇报.md`

## 📊 数据库状态

| 数据库 | 说明 | 状态 |
|--------|------|------|
| db1 | 待扫描 | 预留 |
| db2 | 待买入检测 | 活跃 |
| db3 | 已买入持仓 | 持仓记录 |
| db4 | 不满足条件 | 被拒绝代币 |

## 🔔 买入通知格式

```
🔔 买入成功

🪙 代币: *****
📊 现价: $********
💰 买入金额: 0.003 BNB
📦 预估持仓: *******
💎 CA: ****************
⏰ 时间: 2026-04-02 19:05:00
```
