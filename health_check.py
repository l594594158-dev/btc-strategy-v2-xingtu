#!/usr/bin/env python3
"""
五策略统一健康自检脚本
BTC v4.0 / HYPE v4.0 / ZEC v2.0 / NEAR v3.0 / XLM v6.1
- 每轮检查: 进程存活 + 数据获取 + 持仓同步 + 孤儿仓清理
- 发现问题: 自动重启进程 / 清理孤儿仓
- 仅本地日志, 不发送通知
"""
import ccxt
import os
import json
import subprocess
import time
from datetime import datetime, timezone

# ========== API ==========
from api_config import TRADE_API_KEY, TRADE_SECRET

def get_exchange():
    return ccxt.binance({
        'apiKey': TRADE_API_KEY,
        'secret': TRADE_SECRET,
        'options': {'defaultType': 'swap'},
        'enableRateLimit': True,
    })

LOG_DIR = '/root/liucangyang/logs/health_check'
os.makedirs(LOG_DIR, exist_ok=True)

def log(msg):
    ts = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    line = f"[{ts}] {msg}"
    print(line)
    with open(f'{LOG_DIR}/check.log', 'a') as f:
        f.write(line + '\n')

# ========== 五策略配置 ==========
STRATEGIES = {
    'BTC': {
        'symbol': 'BTC/USDT:USDT',
        'dir': '/root/liucangyang',
        'state_file': 'databases/state_btc.json',
        'state_key_long': 'longpos',
        'state_key_short': 'shortpos',
        'qty': 0.005,
        'max_pos': 3,
    },
    'HYPE': {
        'symbol': 'HYPE/USDT:USDT',
        'dir': '/root/liucangyang_hype',
        'state_file': 'databases/state_hype.json',
        'state_key_long': 'longpositions',
        'state_key_short': 'shortpositions',
        'qty': 3,
        'max_pos': 2,
    },
    'ZEC': {
        'symbol': 'ZEC/USDT:USDT',
        'dir': '/root/liucangyang/zec',
        'state_file': 'databases/state_zec.json',
        'state_key_long': 'longpos',
        'state_key_short': 'shortpos',
        'qty': 0.8,
        'max_pos': 2,
    },
    'NEAR': {
        'symbol': 'NEAR/USDT:USDT',
        'dir': '/root/liucangyang/near',
        'state_file': 'databases/state_near.json',
        'state_key_long': 'longposs',
        'state_key_short': 'shortposs',
        'qty': 150,
        'max_pos': 2,
    },
    'XLM': {
        'symbol': 'XLM/USDT:USDT',
        'dir': '/root/liucangyang/xlm',
        'state_file': 'databases/state_xlm.json',
        'state_key_long': 'longpos',
        'state_key_short': 'shortpos',
        'qty': 1000,
        'max_pos': 3,
    },
}

def is_process_running(directory):
    """检查目录下是否有auto_trade.py进程在运行"""
    try:
        result = subprocess.run(
            ['pgrep', '-f', f'python3.*auto_trade'],
            capture_output=True, text=True, timeout=5
        )
        pids = result.stdout.strip().split()
        for pid in pids:
            if not pid: continue
            try:
                cwd = os.readlink(f'/proc/{pid}/cwd')
                if cwd.startswith(directory):
                    return True, int(pid)
            except:
                pass
        return False, None
    except:
        return False, None

def restart_strategy(name, cfg):
    """重启策略进程"""
    log(f"  [{name}] 重启进程...")
    try:
        subprocess.run(['pkill', '-f', f'{cfg["dir"]}/auto_trade'], 
                       capture_output=True, timeout=5)
        time.sleep(1)
        subprocess.Popen(
            ['nohup', 'python3', '-u', 'auto_trade.py'],
            cwd=cfg['dir'],
            stdout=open(f'{cfg["dir"]}/logs/check_restart.log', 'a'),
            stderr=subprocess.STDOUT,
        )
        log(f"  [{name}] 重启完成")
        return True
    except Exception as e:
        log(f"  [{name}] 重启失败: {e}")
        return False

def load_state(cfg):
    """加载state文件"""
    sp = os.path.join(cfg['dir'], cfg['state_file'])
    if os.path.exists(sp):
        with open(sp) as f:
            return json.load(f)
    return {}

def get_exchange_positions(exchange, symbol):
    """获取交易所持仓"""
    try:
        positions = exchange.fetch_positions([symbol])
        result = {'long': 0, 'short': 0}
        for p in positions:
            amt = abs(float(p.get('contracts', 0) or 0))
            side = p.get('side', '')
            if side == 'long':
                result['long'] += amt
            elif side == 'short':
                result['short'] += amt
        return result
    except Exception as e:
        log(f"  获取持仓失败: {e}")
        return None

def check_orphan(exchange, name, cfg):
    """检查并清理孤儿仓"""
    symbol = cfg['symbol']
    state = load_state(cfg)
    
    # state中记录的持仓数量
    state_long_count = len(state.get(cfg['state_key_long'], []))
    state_short_count = len(state.get(cfg['state_key_short'], []))
    state_long_qty = state_long_count * cfg['qty']
    state_short_qty = state_short_count * cfg['qty']
    
    # 交易所实际持仓
    pos = get_exchange_positions(exchange, symbol)
    if pos is None:
        return
    
    # 比对: 交易所 vs state
    ex_long = pos['long']
    ex_short = pos['short']
    
    if abs(ex_long - state_long_qty) > cfg['qty'] * 0.1 or abs(ex_short - state_short_qty) > cfg['qty'] * 0.1:
        log(f"  [{name}] ⚠ 持仓不匹配: state L={state_long_qty}/S={state_short_qty} vs 交易所 L={ex_long}/S={ex_short}")
        
        # 清理多余仓位 (交易所 > state)
        if ex_long > state_long_qty + cfg['qty'] * 0.5:
            excess = ex_long - state_long_qty
            log(f"  [{name}] 🧹 清理多余LONG: {excess}张")
            _close_orphan(exchange, symbol, 'sell', 'LONG', excess)
        
        if ex_short > state_short_qty + cfg['qty'] * 0.5:
            excess = ex_short - state_short_qty
            log(f"  [{name}] 🧹 清理多余SHORT: {excess}张")
            _close_orphan(exchange, symbol, 'sell', 'SHORT', excess)
        
        # 交易所没有仓位但state有 (幽灵state)
        if state_long_count > 0 and ex_long < cfg['qty'] * 0.5:
            log(f"  [{name}] ⚠ state有{state_long_count}仓LONG但交易所无持仓, 清空state")
            state[cfg['state_key_long']] = []
            save_state_raw(cfg, state)
        
        if state_short_count > 0 and ex_short < cfg['qty'] * 0.5:
            log(f"  [{name}] ⚠ state有{state_short_count}仓SHORT但交易所无持仓, 清空state")
            state[cfg['state_key_short']] = []
            save_state_raw(cfg, state)

def _close_orphan(exchange, symbol, side, position_side, amount):
    """平仓孤儿仓位"""
    try:
        exchange.create_order(
            symbol=symbol,
            type='market',
            side='sell',
            amount=amount,
            params={'reduceOnly': True, 'positionSide': position_side}
        )
        log(f"  已平{position_side}孤儿仓 {amount}张")
    except Exception as e:
        log(f"  平仓失败: {e}")

def save_state_raw(cfg, state):
    """原子写入state"""
    sp = os.path.join(cfg['dir'], cfg['state_file'])
    tmp = sp + '.tmp'
    with open(tmp, 'w') as f:
        json.dump(state, f, indent=2)
        f.flush()
        os.fsync(f.fileno())
    os.rename(tmp, sp)

def check_data(exchange, name, cfg):
    """检查数据获取是否正常"""
    try:
        k = exchange.fetch_ohlcv(cfg['symbol'], '1h', limit=10)
        if len(k) == 0:
            log(f"  [{name}] ❌ 数据获取为空")
            return False
        return True
    except Exception as e:
        log(f"  [{name}] ❌ 数据获取失败: {e}")
        return False

def main():
    log("=" * 50)
    log("五策略健康自检启动")
    
    exchange = get_exchange()
    
    for name in ['BTC', 'HYPE', 'ZEC', 'NEAR', 'XLM']:
        cfg = STRATEGIES[name]
        
        # 1. 检查进程
        running, pid = is_process_running(cfg['dir'])
        if not running:
            log(f"[{name}] ❌ 进程不存在")
            restart_strategy(name, cfg)
        else:
            log(f"[{name}] ✅ 进程运行 PID={pid}")
        
        # 2. 检查数据
        check_data(exchange, name, cfg)
        
        # 3. 检查孤儿仓
        check_orphan(exchange, name, cfg)
    
    log("自检完成")
    log("=" * 50)

if __name__ == '__main__':
    main()
