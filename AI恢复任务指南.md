# AI恢复任务指南

## 适用场景
当BTC合约交易AI宕机、重装系统、或更换AI时，使用本指南快速恢复任务。

---

## 🔄 方式一：一键自动恢复（推荐）

在新服务器上执行：

```bash
cd /root/.openclaw/workspace
git clone https://github.com/l594594158-dev/btc-strategy-backup.git .
cd btc-strategy-task
bash setup.sh
```

**setup.sh 会自动完成：**
1. 克隆 GitHub 仓库代码
2. 安装 Python 依赖（ccxt / pandas / numpy / ta）
3. 恢复 crontab 定时任务
4. 检查 OpenClaw 配置
5. 启动 BTC 合约自动交易任务
6. 启动 XXYY 扫描任务（如有）
7. 显示任务运行状态

---

## ⚠️ 需要手动备份的敏感文件

OpenClaw 配置包含敏感信息（Token/Secret），**不**存在 GitHub 中，需要单独备份：

```bash
# 备份
cp /root/.openclaw/openclaw.json /root/.openclaw/workspace/.backup/openclaw.json
cd /root/.openclaw/workspace
git add -A && git commit -m "backup openclaw config" && git push

# 恢复
cp /root/.openclaw/workspace/.backup/openclaw.json /root/.openclaw/openclaw.json
openclaw gateway restart
```

---

## 🔧 完整备份脚本

在当前服务器上运行，可备份所有环境配置：

```bash
python3 /root/.openclaw/workspace/btc-strategy-task/backup_full.py
```

备份内容（保存在 `.backup/` 目录）：
- `requirements.txt` - Python依赖版本
- `crontab.txt` - 定时任务配置
- `openclaw_config_masked.json` - OpenClaw配置（敏感信息已脱敏）
- `openclaw_agents.json` - Agent/模型配置

---

## 📋 任务总览

### 1. BTC合约自动交易
- **目录:** `btc-strategy-task/`
- **脚本:** `auto_trade.py` (主策略) / `health_check.py` (自检) / `backup_full.py` (备份)
- **参数:** 20x杠杆，0.030 BTC，止损1.5%，止盈2.5%
- **API:** 币安U本位永续

### 2. XXYY链上扫描
- **目录:** `xxyy-ave-scan-task/`
- **脚本:** `scan_task.py`

### 3. XXYY交易
- **目录:** `xxyy-trading-task/`
- **脚本:** `trading_task.py`

---

## ⏰ Crontab 定时任务

| 频率 | 任务 |
|------|------|
| 每30分钟 | 健康检查 (`health_check.py`) |
| 每天02:00 | GitHub自动备份 |
| 每分钟 | 微信通知守护进程 (`send_notify.py`) |

---

## 检查日志

- BTC任务日志：`btc-strategy-task/logs/auto_trade_*.log`
- 自检日志：`btc-strategy-task/logs/health_check/check_log.json`
- 修复记录：`btc-strategy-task/logs/health_check/修复记录.md`
- 工作日志：`btc-strategy-task/logs/work_log.txt`
- 自动备份日志：`logs/auto_backup.log`

---

## 当前版本

- BTC策略: v2.3
- 仓库: https://github.com/l594594158-dev/btc-strategy-backup

---

## 常见问题

### Q: 进程没起来怎么办？
```bash
cd btc-strategy-task
tail -30 logs/auto_trade_*.log | tail
```

### Q: 余额不足怎么办？
当前余额约15 USDT，如需充值，充值到币安账户。

### Q: 如何查看任务状态？
```bash
cd btc-strategy-task && python3 health_check.py
```

### Q: 怎么手动触发GitHub备份？
```bash
cd /root/.openclaw/workspace
git add -A && git commit -m 'update' && git push
```

---
