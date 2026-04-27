#!/usr/bin/env python3
"""
BTC策略 - 持续监控版本
每60秒自动运行一次，支持信号告警
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from strategy import run_strategy_cycle, log
import time

INTERVAL = 60  # 每60秒运行一次

def main():
    count = 0
    log(f"🔄 持续监控模式启动 (每{INTERVAL}秒一次)")
    try:
        while True:
            count += 1
            log(f"--- 第{count}轮监控 ---")
            result = run_strategy_cycle()
            time.sleep(INTERVAL)
    except KeyboardInterrupt:
        log("🛑 监控已停止")

if __name__ == "__main__":
    main()
