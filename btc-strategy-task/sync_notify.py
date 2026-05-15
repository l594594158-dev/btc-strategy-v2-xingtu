#!/usr/bin/env python3
"""
sync_notify.py — 仓位状态同步 & 通知事件生产
职责:
  1. 定时轮询 state.json，检测开仓/平仓事件
  2. 检测到事件后，追加一行 JSON 到 notify_queue.jsonl
  3. 由 notifier.py 消费队列并推送企业微信

supervisor 托管，异常自动重启。
"""
import json
import os
import time
import hashlib
from datetime import datetime

BASE_DIR = '/root/btc-strategy-backup/btc-strategy-task'
STATE_FILE = os.path.join(BASE_DIR, 'databases', 'state.json')
QUEUE_FILE = os.path.join(BASE_DIR, 'databases', 'notify_queue.jsonl')
LOG_DIR = os.path.join(BASE_DIR, 'logs', 'sync')
os.makedirs(LOG_DIR, exist_ok=True)

POLL_INTERVAL = 3      # 轮询间隔(秒)
MAX_EVENT_AGE = 300    # 5分钟内的事件才推送（避免启动时重复推旧事件）

def log(msg):
    ts = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    with open(os.path.join(LOG_DIR, 'sync.log'), 'a') as f:
        f.write(f'[{ts}] {msg}\n')
    print(f'[{ts}] {msg}')

def load_state():
    try:
        with open(STATE_FILE) as f:
            return json.load(f)
    except Exception:
        return {}

def get_state_hash(s):
    """用 positions 列表的稳定部分计算哈希，用于检测变化"""
    pos_list = s.get('positions', [])
    # 只取关键字段
    stable = json.dumps([{
        'entry_price': p.get('entry_price'),
        'qty': p.get('qty'),
        'direction': p.get('direction'),
    } for p in pos_list], sort_keys=True)
    return hashlib.md5(stable.encode()).hexdigest()

def enqueue(event_type, position):
    """追加一行 JSON 到队列文件"""
    entry = {
        'ts': datetime.now().isoformat(),
        'type': event_type,       # 'open' | 'close' | 'partial_close'
        'direction': position.get('direction', 'unknown'),
        'entry_price': position.get('entry_price'),
        'qty': position.get('qty'),
        'reason': position.get('reason', ''),
        'delivered': False,
        'retries': 0,
    }
    try:
        with open(QUEUE_FILE, 'a') as f:
            f.write(json.dumps(entry, ensure_ascii=False) + '\n')
        log(f"📝 入队: {event_type} {position.get('direction','?')} {position.get('qty','?')}BTC @ ${position.get('entry_price','?')}")
    except Exception as e:
        log(f"❌ 入队失败: {e}")

def build_notify_msg(event_type, direction, entry_price, qty, reason, leverage=20):
    """生成推送到企业微信的消息文本"""
    side_emoji = '🟢【做多-LONG】📈' if direction == 'long' else '🔴【做空-SHORT】📉'
    action = '开仓' if event_type == 'open' else '平仓'
    
    lines = [
        f"🚨 BTC{action}通知",
        f"━━━━━━━━━━━━━━━━",
        f"方向: {side_emoji}",
        f"杠杆: {leverage}x",
        f"数量: {qty} BTC",
        f"价格: ${entry_price:,.2f}",
        f"━━━━━━━━━━━━━━━━",
    ]
    if reason:
        lines.append(f"📋 理由:\n{reason}")
    lines.append(f"⏰ {datetime.now().strftime('%H:%M:%S')}")
    return '\n'.join(lines)

def main():
    log("🚀 sync_notify 启动")
    last_hash = None
    first_run = True

    while True:
        try:
            state = load_state()
            current_hash = get_state_hash(state)

            if first_run:
                # 首次启动记录hash，但不触发通知（防止重复推送旧事件）
                last_hash = current_hash
                first_run = False
                log(f"初始化完成，当前仓位数={len(state.get('positions', []))}")
                time.sleep(POLL_INTERVAL)
                continue

            if current_hash != last_hash:
                # 检测到状态变化
                old_positions = []  # 简化处理：只对比当前状态
                new_positions = state.get('positions', [])
                
                if new_positions:
                    # 有持仓 → 开仓事件
                    for pos in new_positions:
                        direction = pos.get('direction', 'unknown')
                        entry_price = pos.get('entry_price', 0)
                        qty = pos.get('qty', 0)
                        reason = pos.get('reason', '')
                        enqueue('open', pos)
                        msg = build_notify_msg('open', direction, entry_price, qty, reason)
                        log(f"📢 检测到开仓: {direction} {qty}BTC @ ${entry_price}")

                if not new_positions and last_hash != 'empty':
                    # 持仓从有到无 → 平仓事件
                    enqueue('close', {'direction': 'unknown', 'entry_price': 0, 'qty': 0, 'reason': '全部平仓'})
                    log("📢 检测到全部平仓")

                last_hash = current_hash

        except Exception as e:
            log(f"⚠️ 轮询异常: {e}")

        time.sleep(POLL_INTERVAL)

if __name__ == '__main__':
    main()
