#!/bin/bash
# ================================================
# 服务器完整恢复脚本
# 在新服务器上一键恢复所有任务环境
# 使用方法: bash setup.sh
# ================================================

set -e

REPO_URL="https://github.com/l594594158-dev/btc-strategy-backup.git"
WORKSPACE="/root/.openclaw/workspace"
BACKUP_DIR="$WORKSPACE/.backup"

echo "=========================================="
echo "🚀 服务器完整恢复脚本"
echo "=========================================="

# ---- 1. 克隆仓库 ----
echo ""
echo "[1/7] 克隆仓库..."
if [ -d "$WORKSPACE/.git" ]; then
    echo "  仓库已存在，更新代码..."
    cd "$WORKSPACE"
    git pull origin main
else
    git clone "$REPO_URL" "$WORKSPACE"
fi
echo "  ✅ 完成"

# ---- 2. 安装Python依赖 ----
echo ""
echo "[2/7] 安装Python依赖..."
if [ -f "$BACKUP_DIR/requirements.txt" ]; then
    pip3 install -r "$BACKUP_DIR/requirements.txt" -q
    echo "  ✅ 依赖安装完成"
else
    echo "  ⚠️ 未找到requirements.txt，安装基础包..."
    pip3 install ccxt==4.5.46 pandas==3.0.2 numpy==2.4.4 ta==0.11.0 -q
fi

# ---- 3. 恢复Crontab ----
echo ""
echo "[3/7] 恢复Crontab定时任务..."
if [ -f "$BACKUP_DIR/crontab.txt" ]; then
    # 备份现有
    crontab -l > /tmp/crontab.old 2>/dev/null || true
    # 合并crontab（保留原有的，不重复）
    (crontab -l 2>/dev/null | grep -v "btc-strategy-task\|xxyy-ave-scan-task\|xxyy-trading-task\|auto_backup\|send_notify"; \
     cat "$BACKUP_DIR/crontab.txt" | grep -v "^#") | crontab -
    echo "  ✅ Crontab已恢复"
    echo "  当前Crontab:"
    crontab -l | grep -v "^#"
else
    echo "  ⚠️ 未找到crontab.txt，跳过"
fi

# ---- 4. 检查并告知OpenClaw配置 ----
echo ""
echo "[4/7] OpenClaw配置..."
if [ -f "/root/.openclaw/openclaw.json" ]; then
    echo "  ✅ OpenClaw配置已存在，跳过"
else
    echo "  ⚠️ 未找到 /root/.openclaw/openclaw.json"
    echo "  请手动从以下位置恢复(如果有备份):"
    echo "    - GitHub备份: openclaw_config_masked.json (已脱敏)"
    echo "    - 本地备份: /root/.openclaw/openclaw.json.bak"
fi

# ---- 5. 启动BTC合约任务 ----
echo ""
echo "[5/7] 启动BTC合约自动交易任务..."
if pgrep -f "auto_trade.py" > /dev/null; then
    echo "  已在运行，跳过"
else
    cd "$WORKSPACE/btc-strategy-task"
    mkdir -p logs
    nohup python3 -u auto_trade.py > logs/auto_trade_$(date +%Y%m%d_%H%M%S).log 2>&1 &
    sleep 3
    if pgrep -f "auto_trade.py" > /dev/null; then
        echo "  ✅ BTC合约任务已启动"
    else
        echo "  ⚠️ 启动可能失败，请检查日志: logs/auto_trade_*.log"
    fi
fi

# ---- 6. 启动XXYY扫描任务 ----
echo ""
echo "[6/7] 启动XXYY链上扫描任务..."
if [ -f "$WORKSPACE/xxyy-ave-scan-task/scan_task.py" ]; then
    if pgrep -f "scan_task.py" > /dev/null; then
        echo "  已在运行，跳过"
    else
        cd "$WORKSPACE/xxyy-ave-scan-task"
        mkdir -p logs
        nohup python3 -u scan_task.py > logs/scan_$(date +%Y%m%d_%H%M%S).log 2>&1 &
        sleep 2
        echo "  ✅ XXYY扫描任务已启动"
    fi
else
    echo "  无XXYY扫描任务，跳过"
fi

# ---- 7. 确认状态 ----
echo ""
echo "[7/7] 检查任务状态..."
echo ""
echo "--- 运行中的任务进程 ---"
ps aux | grep -E "auto_trade|scan_task|trading_task" | grep -v grep || echo "  无"
echo ""
echo "--- Crontab ---"
crontab -l | grep -v "^#"
echo ""
echo "=========================================="
echo "✅ 恢复完成！"
echo "=========================================="
echo ""
echo "查看BTC日志:"
echo "  tail -f $WORKSPACE/btc-strategy-task/logs/auto_trade_*.log"
echo ""
echo "检查任务状态:"
echo "  cd $WORKSPACE/btc-strategy-task && python3 health_check.py"
echo ""
echo "手动备份OpenClaw配置(敏感):"
echo "  cp /root/.openclaw/openclaw.json /root/.openclaw/workspace/.backup/"
echo "  # 然后 git add -A && git commit -m 'backup openclaw config' && git push"
echo "=========================================="
