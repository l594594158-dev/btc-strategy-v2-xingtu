#!/usr/bin/env python3
"""
notifier.py — 通知队列消费者 & 企业微信推送 (v2)
职责:
  1. 持续读取 notify_queue.jsonl，逐行消费
  2. 写入 openclaw delivery-queue 目录（由openclaw网关负责推送到企业微信）
  3. 消费成功后标记 delivered=true，失败保留供重试
  4. 定期清理已送达的旧条目

使用 openclaw delivery-queue 机制，避免 CLI 调用超时卡死。
supervisor 托管，异常自动重启。
"""
import json
import os
import time
import uuid
from datetime import datetime

BASE_DIR = '/root/btc-strategy-backup/btc-strategy-task'
QUEUE_FILE = os.path.join(BASE_DIR, 'databases', 'notify_queue.jsonl')
DELIVERY_DIR = '/root/.openclaw/delivery-queue'
LOG_DIR = os.path.join(BASE_DIR, 'logs', 'notifier')
os.makedirs(LOG_DIR, exist_ok=True)

POLL_INTERVAL = 2       # 队列检查间隔(秒)
MAX_RETRIES = 20        # 单条最大重试次数
RETRY_DELAY = 15        # 失败后重试间隔(秒)

def log(msg):
    ts = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    with open(os.path.join(LOG_DIR, 'notifier.log'), 'a') as f:
        f.write(f'[{ts}] {msg}\n')
    print(f'[{ts}] {msg}')

def write_delivery_queue(msg_text):
    """
    写入 openclaw delivery-queue 目录。
    格式与 openclaw 的 delivery-queue 一致，由 openclaw 网关进程消费。
    返回 True（不管最终是否送达，openclaw网关会处理重试）
    """
    try:
        os.makedirs(DELIVERY_DIR, exist_ok=True)
        entry = {
            'id': str(uuid.uuid4()),
            'enqueuedAt': int(time.time() * 1000),
            'channel': 'wecom',
            'to': 'LiuGang',
            'payloads': [{'text': msg_text, 'replyToTag': False, 'replyToCurrent': False, 'audioAsVoice': False}],
            'gifPlayback': False,
            'forceDocument': False,
            'silent': False,
        }
        # 添加session/mirror字段（openclaw gateway据此识别会话）
        entry['session'] = {'key': 'agent:main:wecom:group:liugang', 'agentId': 'main'}
        entry['mirror'] = {'sessionKey': 'agent:main:wecom:group:liugang', 'agentId': 'main', 'text': msg_text}
        # 写入临时文件后原子重命名，避免读取到半成品
        tmp = os.path.join(DELIVERY_DIR, f'.{entry["id"]}.tmp')
        final = os.path.join(DELIVERY_DIR, f'{entry["id"]}.json')
        with open(tmp, 'w') as f:
            json.dump(entry, f, ensure_ascii=False)
        os.rename(tmp, final)
        return True
    except Exception as e:
        log(f"❌ delivery-queue写入失败: {e}")
        return False

def consume_queue():
    """读取并消费队列文件"""
    if not os.path.exists(QUEUE_FILE):
        return

    try:
        with open(QUEUE_FILE, 'r') as f:
            lines = f.readlines()
    except Exception as e:
        log(f"❌ 读取队列失败: {e}")
        return

    if not lines:
        return

    updated = False
    new_lines = []

    for line in lines:
        line = line.strip()
        if not line:
            continue

        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue

        # 已送达的保留后清理
        if entry.get('delivered'):
            new_lines.append(line)
            continue

        # 超过最大重试次数的放弃
        if entry.get('retries', 0) >= MAX_RETRIES:
            log(f"⏭️ 放弃（超重试）: {entry.get('type','?')} 重试{entry['retries']}次")
            entry['delivered'] = True
            entry['abandoned'] = True
            new_lines.append(json.dumps(entry, ensure_ascii=False))
            updated = True
            continue

        # 构建消息文本
        entry_data = entry
        if 'msg' in entry_data and entry_data['msg']:
            msg = entry_data['msg']
        else:
            event_type = entry_data.get('type', '?')
            direction = entry_data.get('direction', '?')
            entry_price = entry_data.get('entry_price', 0)
            qty = entry_data.get('qty', 0)
            reason = entry_data.get('reason', '')

            side_emoji = {'long': '🟢【做多LONG】📈', 'short': '🔴【做空SHORT】📉'}.get(direction, '⚪')
            action = '开仓' if event_type == 'open' else ('平仓' if event_type == 'close' else event_type)

            msg = (
                f"🚨 BTC{action}通知\n"
                f"━━━━━━━━━━━━━━━━\n"
                f"方向: {side_emoji}\n"
                f"数量: {qty} BTC\n"
            )
            if entry_price:
                msg += f"价格: ${entry_price:,.2f}\n"
            msg += f"━━━━━━━━━━━━━━━━\n"
            if reason:
                msg += f"📋 理由:\n{reason}\n"
            msg += f"⏰ {datetime.now().strftime('%H:%M:%S')}"

        # 写入 delivery-queue（由openclaw网关负责推送）
        ok = write_delivery_queue(msg)
        entry['retries'] += 1

        if ok:
            entry['delivered'] = True
            log(f"✅ 已入delivery-queue: {entry_data.get('type','msg')}")
        else:
            log(f"⏳ 入delivery-queue失败(第{entry['retries']}次)")

        new_lines.append(json.dumps(entry, ensure_ascii=False))
        updated = True

    if updated:
        try:
            # 只保留：未送达的 / 最近30分钟内送达的
            now = time.time()
            keep_lines = []
            for line in new_lines:
                try:
                    e = json.loads(line)
                    if not e.get('delivered') or (e.get('ts') and (now - _parse_ts(e['ts'])) < 1800):
                        keep_lines.append(line)
                    elif not e.get('ts'):
                        keep_lines.append(line)
                except:
                    keep_lines.append(line)
            keep_lines = keep_lines[-200:]
            with open(QUEUE_FILE, 'w') as f:
                f.write('\n'.join(keep_lines) + ('\n' if keep_lines else ''))
        except Exception as e:
            log(f"❌ 写回队列失败: {e}")

def _parse_ts(ts_str):
    """解析时间字符串为时间戳"""
    try:
        return datetime.fromisoformat(ts_str).timestamp()
    except:
        return 0

def main():
    log("🚀 notifier v2 启动 (delivery-queue模式)")

    # 启动时先消费已积压的消息
    consume_queue()

    while True:
        try:
            consume_queue()
        except Exception as e:
            log(f"⚠️ 消费异常: {e}")
        time.sleep(POLL_INTERVAL)

if __name__ == '__main__':
    main()
