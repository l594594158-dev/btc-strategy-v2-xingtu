#!/usr/bin/env python3
"""
仓位同步策略 — Gate监控账户 → 币安交易账户
=============================================
1. 每秒扫描Gate仓位变动
2. Gate开仓 → 币安同向开仓 (名义价值10%)
3. Gate平仓 → 币安立即平仓
4. 日志记录所有变动
"""

import ccxt
import time
import json
import os
import math
from datetime import datetime

# ========== 监控账户 (Gate) ==========
GATE_API_KEY = "17cd51c6bacc6de57bea112fc49901b4"
GATE_SECRET = "e4d88c9cdb83f7d6544315ea650dc46f52f19d9a09980e80b03741c46d15b928"

# ========== 交易账户 (币安合约) ==========
BINANCE_API_KEY = "IlPevOWyWpnC2FgpcRlk7kQX24AjjBh6hhD0l5ki5g43AebJy1GwNPH4D3fzZcI9"
BINANCE_SECRET = "cdw4Owv1y7llmXZqwHXSTW0pSDEI68EEP0FCMa09bi5r24YenCV4n6vnRzjQpF1I"

# ========== 配置 ==========
POLL_INTERVAL = 1          # 扫描间隔(秒)
COPY_RATIO = 1.0           # 跟单比例: 100%
BASE_DIR = "/root/liucangyang/position_sync"
STATE_FILE = f"{BASE_DIR}/state.json"
WORK_LOG = f"{BASE_DIR}/logs/work_log.txt"

# ========== 交易所实例 ==========
gate = ccxt.gate({
    'apiKey': GATE_API_KEY,
    'secret': GATE_SECRET,
    'options': {
        'defaultType': 'swap',
        'defaultSettle': 'usdt',
    },
    'enableRateLimit': True,
})

binance = ccxt.binance({
    'apiKey': BINANCE_API_KEY,
    'secret': BINANCE_SECRET,
    'options': {'defaultType': 'swap'},
    'enableRateLimit': True,
})

# Gate→Binance 合约symbol映射
GATE_TO_BINANCE = {
    'BTC/USDT:USDT': 'BTC/USDT:USDT',
    'ETH/USDT:USDT': 'ETH/USDT:USDT',
    'SOL/USDT:USDT': 'SOL/USDT:USDT',
    'HYPE/USDT:USDT': 'HYPE/USDT:USDT',
    'ZEC/USDT:USDT': 'ZEC/USDT:USDT',
    'NEAR/USDT:USDT': 'NEAR/USDT:USDT',
    'XLM/USDT:USDT': 'XLM/USDT:USDT',
    'DOGE/USDT:USDT': 'DOGE/USDT:USDT',
    'SUI/USDT:USDT': 'SUI/USDT:USDT',
    'APT/USDT:USDT': 'APT/USDT:USDT',
    'LTC/USDT:USDT': 'LTC/USDT:USDT',
    'LINK/USDT:USDT': 'LINK/USDT:USDT',
    'AVAX/USDT:USDT': 'AVAX/USDT:USDT',
    'ARB/USDT:USDT': 'ARB/USDT:USDT',
    'OP/USDT:USDT': 'OP/USDT:USDT',
}


# ========== 日志 ==========
def log(msg):
    ts = datetime.now().strftime('%H:%M:%S')
    print(f"[{ts}] {msg}")

def work_log(event, detail):
    ts = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    os.makedirs(os.path.dirname(WORK_LOG), exist_ok=True)
    with open(WORK_LOG, 'a') as f:
        f.write(f"[{ts}] [{event}] {detail}\n")
    log(f"📝 {event}: {detail}")


# ========== 状态管理 ==========
def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE) as f:
            return json.load(f)
    return {}

def save_state(s):
    tmp = STATE_FILE + '.tmp'
    with open(tmp, 'w') as f:
        json.dump(s, f, indent=2)
        f.flush()
        os.fsync(f.fileno())
    os.rename(tmp, STATE_FILE)


# ========== Gate仓位查询 ==========
def fetch_gate_positions():
    """获取Gate合约当前持仓"""
    pos_map = {}
    try:
        positions = gate.fetch_positions()
        for p in positions:
            contracts = float(p.get('contracts', 0) or 0)
            if contracts <= 0:
                continue
            sym = p.get('symbol', '')
            if sym not in GATE_TO_BINANCE:
                continue
            side = 'LONG' if p.get('side') == 'long' else 'SHORT'
            # 直接用Gate返回的名义价值(USDT)
            notional = float(p.get('notional', 0) or 0)
            entry = float(p.get('entryPrice', 0) or 0)
            contracts = float(p.get('contracts', 0) or 0)
            pos_map[sym] = {
                'side': side,
                'qty': contracts,
                'entry': entry,
                'notional': notional,
            }
    except Exception as e:
        err_msg = str(e)
        if not globals().get("_gate_err_ts", 0) or time.time() - globals()["_gate_err_ts"] > 30:
            globals()["_gate_err_ts"] = time.time()
            log(f"⚠️ Gate仓位查询失败: {err_msg[:120]}")
    return pos_map


# ========== 币安仓位查询 ==========
def fetch_binance_positions():
    """获取币安合约当前持仓"""
    pos_map = {}
    try:
        positions = binance.fetch_positions()
        for p in positions:
            contracts = float(p.get('contracts', 0) or 0)
            if contracts <= 0:
                continue
            sym = p.get('symbol', '')
            side = 'LONG' if p.get('side') == 'long' else 'SHORT'
            pos_map[sym] = {
                'side': side,
                'qty': contracts,
                'entry': float(p.get('entryPrice', 0) or 0),
            }
    except Exception as e:
        err_msg = str(e)
        if not globals().get("_binance_err_ts", 0) or time.time() - globals()["_binance_err_ts"] > 30:
            globals()["_binance_err_ts"] = time.time()
            log(f"⚠️ 币安仓位查询失败: {err_msg[:120]}")
    return pos_map


# ========== 币安执行 ==========
def binance_open(symbol, side, target_qty):
    """币安开仓"""
    try:
        qty = float(target_qty)
        if qty <= 0:
            return False

        ps = 'LONG' if side == 'LONG' else 'SHORT'
        order_side = 'buy' if side == 'LONG' else 'sell'

        log(f"🟢 开仓 {symbol} {side} qty={qty}张")

        order = binance.create_order(
            symbol=symbol,
            type='market',
            side=order_side,
            amount=qty,
            params={'positionSide': ps}
        )
        fill = float(order.get('average', 0) or 0)
        work_log('开仓', f"{symbol} {side} qty={qty} fill=${fill:.4f}")
        return True

    except Exception as e:
        log(f"❌ 开仓失败 {symbol} {side}: {e}")
        work_log('开仓失败', f"{symbol} {side}: {e}")
        return False


def binance_close(symbol, side, qty):
    """币安宁仓"""
    try:
        ps = 'LONG' if side == 'LONG' else 'SHORT'
        close_side = 'sell' if side == 'LONG' else 'buy'
        qty = float(qty)
        if qty <= 0:
            return False

        log(f"🔴 平仓 {symbol} {side} qty={qty}")

        order = binance.create_order(
            symbol=symbol,
            type='market',
            side=close_side,
            amount=qty,
            params={'positionSide': ps}
        )
        fill = float(order.get('average', 0) or 0)
        work_log('平仓', f"{symbol} {side} qty={qty} fill=${fill:.4f}")
        return True

    except Exception as e:
        log(f"❌ 平仓失败 {symbol} {side}: {e}")
        work_log('平仓失败', f"{symbol} {side}: {e}")
        return False


# ========== 仓位差异对比（绝对同步模式）==========
def sync_positions(gate_positions, binance_positions, state):
    """
    绝对同步: 按Gate当前仓位 → 币安完全镜像(名义价值10%)
    - 每种币按(symbol, side)唯一建仓
    - 全平→全平; 减仓→等比减仓; 加仓→补仓
    """
    changed = False
    recorded = state.get('gate_positions', {})
    initialized = state.get('initialized', False)

    # 构建Gate现有仓位索引
    gate_index = {}  # {bin_sym: [(side, gate_sym, gpos)]}
    for gate_sym, gpos in gate_positions.items():
        bin_sym = GATE_TO_BINANCE.get(gate_sym)
        if not bin_sym:
            continue
        if bin_sym not in gate_index:
            gate_index[bin_sym] = []
        gate_index[bin_sym].append((gpos['side'], gate_sym, gpos))

    # 遍历Gate仓位 → 同步到币安
    for bin_sym, entries in gate_index.items():
        for side, gate_sym, gpos in entries:
            gkey = f"{gate_sym}:{side}"
            prev = recorded.get(gkey, {})
            prev_qty = prev.get('qty', 0) if initialized else gpos['qty']

            # 目标名义价值 = Gate名义价值 × 10%
            target_notional = gpos['notional'] * COPY_RATIO
            
            # 币安合约参数
            try:
                ticker = binance.fetch_ticker(bin_sym)
                binance_price = ticker.get('last', 0)
            except:
                binance_price = 0
            try:
                market = binance.market(bin_sym)
                bc_size = market.get('contractSize', 1) or 1
                min_amount = market.get('limits', {}).get('amount', {}).get('min', 1) or 1
                precision = market.get('precision', {}).get('amount', 4) or 4
            except:
                bc_size = 1
                min_amount = 1
                precision = 4
            
            bc_notional = bc_size * binance_price if binance_price > 0 else 1
            
            # 目标张数 = 目标名义价值 ÷ (币安最新价 × 合约面值)
            if bc_notional > 0:
                target_qty_raw = target_notional / bc_notional
            else:
                target_qty_raw = 0
            
            # 按币安精度取整
            precision = market.get('precision', {}).get('amount', 4) or 4
            if isinstance(precision, float) or precision < 1:
                # 小数精度(如BTC=0.001): 取到对应小数位
                ndigits = abs(int(math.log10(precision))) if precision > 0 else 3
                target_qty = round(target_qty_raw, ndigits)
            else:
                target_qty = int(target_qty_raw + 0.5)
            
            # 小于最小开仓数量则设为0跳过
            if target_qty > 0 and target_qty < min_amount:
                target_qty = 0

            # 获取币安当前该方向持仓（float，支持小数张数）
            bpos = binance_positions.get(bin_sym)
            current_binance_qty = 0.0
            if bpos and bpos['side'] == side:
                current_binance_qty = float(bpos['qty'])

            if not initialized:
                # 初始化阶段：只记录快照
                recorded[gkey] = {
                    'qty': gpos['qty'], 'side': side,
                    'entry': gpos['entry'], 'notional': gpos['notional'],
                    'target_binance_qty': target_qty,
                    'last_update': datetime.now().strftime('%H:%M:%S'),
                }
                changed = True
                continue

            # 检测Gate仓位变化
            if gpos['qty'] != prev_qty:
                log(f"📊 Gate {gate_sym} {side}: {prev_qty:.1f}→{gpos['qty']:.1f}张")
                # 仓位变化时重置失败标记
                if 'last_sync_fail' in prev:
                    del prev['last_sync_fail']

            # 决策: Gate有仓位 → 币安同步到target_qty
            if gpos['qty'] > 0:
                if current_binance_qty == target_qty:
                    pass  # 数量一致，跳过
                elif current_binance_qty < target_qty:
                    # 需要补仓（只在Gate仓位首次变动时操作，避免无限重试）
                    delta = target_qty - current_binance_qty
                    last_fail = prev.get('last_sync_fail', False)
                    if not last_fail:
                        log(f"🟢 补仓 {bin_sym} {side} +{delta}张 → 目标{target_qty}张")
                        success = binance_open(bin_sym, side, delta)
                        if not success:
                            recorded[gkey] = dict(prev, **{'last_sync_fail': True, 'qty': gpos['qty'], 'side': side,
                                'entry': gpos['entry'], 'notional': gpos['notional'], 'target_binance_qty': target_qty,
                                'last_update': datetime.now().strftime('%H:%M:%S')})
                            state['gate_positions'] = recorded
                            save_state(state)
                            continue  # 跳过正常更新，已手写了
                        changed = True
                elif current_binance_qty > target_qty:
                    # 需要减仓
                    delta = current_binance_qty - target_qty
                    log(f"🔴 减仓 {bin_sym} {side} -{delta}张 → 目标{target_qty}张")
                    binance_close(bin_sym, side, delta)
                    changed = True
            else:
                # Gate无仓位或平完了
                if current_binance_qty > 0:
                    log(f"🔴 全平 {bin_sym} {side} {current_binance_qty}张 (Gate已平仓)")
                    binance_close(bin_sym, side, current_binance_qty)
                    changed = True

            # 更新快照
            recorded[gkey] = {
                'qty': gpos['qty'], 'side': side,
                'entry': gpos['entry'], 'notional': gpos['notional'],
                'target_binance_qty': target_qty,
                'last_update': datetime.now().strftime('%H:%M:%S'),
                'last_sync_fail': recorded.get(gkey, {}).get('last_sync_fail', False),
            }

    # 检查Gate已平完但recorded还有的
    current_keys = {f"{gate_sym}:{side}" for bin_sym, entries in gate_index.items() for side, gate_sym, _ in entries}
    for gkey in list(recorded.keys()):
        if gkey not in current_keys and initialized:
            gate_sym, side = gkey.rsplit(':', 1)
            bin_sym = GATE_TO_BINANCE.get(gate_sym)
            if bin_sym:
                bpos = binance_positions.get(bin_sym)
                if bpos and bpos['side'] == side:
                    log(f"🔴 全平 {bin_sym} {side} {bpos['qty']}张 (Gate仓位消失)")
                    binance_close(bin_sym, side, bpos['qty'])
                    changed = True
            del recorded[gkey]
            changed = True

    if changed:
        state['gate_positions'] = recorded
        save_state(state)

    return changed


# ========== 主循环 ==========
def main():
    log("=" * 50)
    log("🚀 仓位同步策略启动")
    log(f"监控账户: Gate.io")
    log(f"交易账户: Binance合约")
    log(f"跟单比例: {COPY_RATIO*100}%")
    log(f"扫描间隔: {POLL_INTERVAL}s")
    log("=" * 50)

    # 预加载market信息
    try:
        binance.load_markets()
        log(f"📋 币安市场信息已加载")
    except:
        pass

    state = load_state()
    if 'gate_positions' not in state:
        state['gate_positions'] = {}
    if 'initialized' not in state:
        state['initialized'] = False

    # 初始化: 先读一遍当前仓位建立快照
    gate_pos = fetch_gate_positions()
    for sym, pos in gate_pos.items():
        gkey = f"{sym}:{pos['side']}"
        state['gate_positions'][gkey] = {
            'qty': pos['qty'],
            'side': pos['side'],
            'entry': pos['entry'],
            'notional': pos['notional'],
            'last_update': datetime.now().strftime('%H:%M:%S'),
        }
    
    # 首次启动标记: 建好快照后才开始跟单同步
    if not state['initialized']:
        state['initialized'] = True
        log(f"📊 初始化快照完成: {len(state['gate_positions'])}个Gate仓位 (后续变动将触发同步)")
    save_state(state)

    for k, v in state['gate_positions'].items():
        log(f"  📋 {k}: qty={v['qty']:.4f} notional=${v.get('notional', 0):.2f}")

    while True:
        start = time.time()

        try:
            gate_pos = fetch_gate_positions()
            binance_pos = fetch_binance_positions()
            state = load_state()
            if 'gate_positions' not in state:
                state['gate_positions'] = {}
            if 'initialized' not in state:
                state['initialized'] = False

            synced = sync_positions(gate_pos, binance_pos, state)

        except KeyboardInterrupt:
            log("🛑 停止")
            break
        except Exception as e:
            if not globals().get("_last_err_ts", 0) or time.time() - globals()["_last_err_ts"] > 30:
                globals()["_last_err_ts"] = time.time()
                log(f"❌ 循环异常: {e}")
            import traceback
            traceback.print_exc()

        elapsed = time.time() - start
        if elapsed < POLL_INTERVAL:
            time.sleep(POLL_INTERVAL - elapsed)


if __name__ == '__main__':
    main()
