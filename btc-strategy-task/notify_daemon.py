#!/usr/bin/env python3
"""
通知守护进程
每30秒检查pending文件，发现新开仓通知立即写入待发送队列
由agent心跳检查并发送微信
"""
import os, time, json
from datetime import datetime

PENDING_FILE = '/root/.openclaw/workspace/btc-strategy-task/databases/pending_wechat.txt'
QUEUE_FILE = '/root/.openclaw/workspace/btc-strategy-task/databases/notify_queue.json'

def check_and_queue():
    # 安全读取队列文件
    queue = []
    if os.path.exists(QUEUE_FILE):
        try:
            with open(QUEUE_FILE, 'r') as f:
                data = json.load(f)
            # 确保是列表格式
            if isinstance(data, list):
                queue = data
            elif isinstance(data, dict):
                # 兼容：单条通知格式，转成列表
                queue = [data]
            else:
                # 损坏，直接清空
                queue = []
        except (json.JSONDecodeError, ValueError, TypeError) as e:
            print(f"⚠️ 队列文件损坏，已重建: {e}")
            queue = []

    # 检查pending文件
    if os.path.exists(PENDING_FILE):
        with open(PENDING_FILE, 'r') as f:
            content = f.read().strip()

        if content:
            # 检查是否已在队列中（避免重复）
            if not any(isinstance(item, dict) and item.get('msg') == content for item in queue):
                queue.append({
                    'msg': content,
                    'time': datetime.now().isoformat(),
                    'sent': False
                })
                print(f"[{datetime.now().strftime('%H:%M:%S')}] 📬 新通知入队")

            # 清空pending文件
            with open(PENDING_FILE, 'w') as f:
                f.write('')

    # 写回队列文件
    with open(QUEUE_FILE, 'w') as f:
        json.dump(queue, f, ensure_ascii=False)

def main():
    print(f"通知守护进程启动 (每30秒检查)")
    while True:
        try:
            check_and_queue()
        except Exception as e:
            print(f"异常: {e}")
        time.sleep(30)

if __name__ == '__main__':
    main()
