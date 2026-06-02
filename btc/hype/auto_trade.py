#!/usr/bin/env python3
"""
HYPE v4.0 EMA5/10 1h交叉策略 — Binance合约（模板: BTC v4.0）
入场: 1h闭K信号 → 下一根开盘入场
平仓: 实时价触发TP/SL

策略参数:
  方向: 1h EMA5/EMA10 纯方向锚定 (lv-1闭K)
  条件: ①EMA方向 ②ADX1h>20 ③ADX4h<50 ④RSI区间 ⑤量比>3.0
  仓位: 3仓/边 (longpos/shortpos数组)
  TP/SL: +2.0%/-5.0%
"""

import ccxt
import json
import os
import time
from datetime import datetime, timezone

# ========== API ==========
from api_config import READ_API_KEY, READ_SECRET, TRADE_API_KEY, TRADE_SECRET

exchange = ccxt.binance({
    'apiKey': TRADE_API_KEY,
    'secret': TRADE_SECRET,
    'options': {'defaultType': 'swap'},
    'enableRateLimit': True,
})

SYMBOL = 'HYPE/USDT:USDT'
QTY = 20          # HYPE合约 minQty=0.01, 20张=0.2 HYPE
LEVERAGE = 20

BASE_DIR = '/root/liucangyang_hype'
STATE_FILE = f'{BASE_DIR}/databases/state_hype.json'
PAUSE_FILE = f'{BASE_DIR}/databases/hype_pause.flag'
NOTIFY_QUEUE = f'{BASE_DIR}/databases/notify_queue.json'
WORK_LOG = f'{BASE_DIR}/logs/hype_work_log.txt'

# ========== 策略参数 ==========
TP_PCT = 0.02
SL_PCT = 0.05
MAX_POS = 3

ADX_1H_MIN = 20
ADX_4H_MAX = 50
RSI_LONG_MIN = 40
RSI_SHORT_MAX = 60
VOL_RATIO_MIN = 3.0

# ========== 日志 ==========
def log(msg):
    stamp = datetime.now().strftime('%H:%M:%S')
    print(f"[{stamp}] {msg}")

def work_log(event, detail):
    ts = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    with open(WORK_LOG, 'a') as f:
        f.write(f"[{ts}] [{event}] {detail}\n")

def notify(msg):
    try:
        items = []
        if os.path.exists(NOTIFY_QUEUE):
            with open(NOTIFY_QUEUE) as f:
                items = json.load(f)
        items.append({'msg': msg, 'sent': False})
        with open(NOTIFY_QUEUE, 'w') as f:
            json.dump(items, f, ensure_ascii=False)
    except:
        pass

# ========== 状态管理 ==========
def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE) as f:
            return json.load(f)
    return {'longpos': [], 'shortpos': [], 'lastexitkl_time': 0, 'lastentrykl_time': 0}

def save_state(s):
    tmp = STATE_FILE + '.tmp'
    with open(tmp, 'w') as f:
        json.dump(s, f, indent=2)
        f.flush()
        os.fsync(f.fileno())
    os.rename(tmp, STATE_FILE)

# ========== 指标计算 (Wilder平滑) ==========
def ema(series, period):
    """EMA: α=2/(period+1), SMA初始化"""
    if not series: return []
    k = 2.0 / (period + 1)
    r = [series[0]]
    for v in series[1:]:
        r.append(r[-1] + k * (v - r[-1]))
    return r

def rsi(series, period=14):
    """Wilder RSI"""
    n = len(series)
    if n < period + 1:
        return [50.0] * n
    r = [50.0] * period
    gain = sum(max(series[i]-series[i-1],0) for i in range(1,period+1)) / period
    loss = sum(abs(min(series[i]-series[i-1],0)) for i in range(1,period+1)) / period
    for i in range(period, n):
        r.append(100.0 - 100.0/(1.0+gain/loss) if loss>0 else 100.0)
        if i+1 < n:
            diff = series[i+1] - series[i]
            gain = (gain*(period-1) + max(diff,0)) / period
            loss = (loss*(period-1) + abs(min(diff,0))) / period
    return r

def adx(highs, lows, closes, period=14):
    """Wilder ADX"""
    n = len(highs)
    if n < period*2:
        return [0.0]*n
    tr, pdm, mdm = [0.0]*n, [0.0]*n, [0.0]*n
    for i in range(1, n):
        tr[i] = max(highs[i]-lows[i], abs(highs[i]-closes[i-1]), abs(lows[i]-closes[i-1]))
        hh, ll = highs[i]-highs[i-1], lows[i-1]-lows[i]
        pdm[i] = hh if (hh>ll and hh>0) else 0.0
        mdm[i] = ll if (ll>hh and ll>0) else 0.0
    atr, pde, mde, dx = [0.0]*n, [0.0]*n, [0.0]*n, [0.0]*n
    atr[period] = sum(tr[1:period+1])
    pde[period] = sum(pdm[1:period+1])
    mde[period] = sum(mdm[1:period+1])
    for i in range(period+1, n):
        atr[i] = atr[i-1] - atr[i-1]/period + tr[i]
        pde[i] = pde[i-1] - pde[i-1]/period + pdm[i]
        mde[i] = mde[i-1] - mde[i-1]/period + mdm[i]
    for i in range(period, n):
        if atr[i]==0: dx[i]=0.0; continue
        pdi = 100*pde[i]/atr[i]; mdi = 100*mde[i]/atr[i]
        den = pdi+mdi; dx[i] = 100*abs(pdi-mdi)/den if den else 0.0
    adx_s = [0.0]*n
    adx_s[period*2-1] = sum(dx[period:period*2])/period
    for i in range(period*2, n):
        adx_s[i] = (adx_s[i-1]*(period-1)+dx[i])/period
    return adx_s

def vol_ratio(vols, period=20):
    """量比=vol[i]/mean(vol[i-period...i])"""
    r = [1.0]*period
    w = vols[:period]
    for i in range(period, len(vols)):
        avg = sum(w)/period
        r.append(vols[i]/avg if avg>0 else 1.0)
        w.pop(0); w.append(vols[i])
    return r

# ========== 数据获取 ==========
def fetch_klines(interval, limit=200):
    return exchange.fetch_ohlcv(SYMBOL, interval, limit=limit)

def extract(k):
    return {
        't': k[0], 'o': float(k[1]), 'h': float(k[2]),
        'l': float(k[3]), 'c': float(k[4]), 'v': float(k[5])
    }

# ========== 核心逻辑 ==========
def check_signal(kl_1h, kl_4h):
    """
    偏移: EMA方向 lv-1 | ADX1h 闭K | ADX4h 前一完整4h闭K
          RSI 闭K | 量比 lv-1
    """
    n = len(kl_1h)
    if n < 100:
        return None

    closes = [k['c'] for k in kl_1h]
    highs  = [k['h'] for k in kl_1h]
    lows   = [k['l'] for k in kl_1h]
    vols   = [k['v'] for k in kl_1h]

    ema5  = ema(closes, 5)
    ema10 = ema(closes, 10)
    rsi_v = rsi(closes, 14)
    adx1  = adx(highs, lows, closes, 14)
    vr    = vol_ratio(vols, 20)

    t_4h = [k['t'] for k in kl_4h]
    c4h  = [k['c'] for k in kl_4h]
    h4h  = [k['h'] for k in kl_4h]
    l4h  = [k['l'] for k in kl_4h]
    adx4 = adx(h4h, l4h, c4h, 14)

    t_signal = kl_1h[-2]['t']
    adx4_val = 0
    for i in range(len(t_4h)-1, -1, -1):
        if t_4h[i] + 4*3600*1000 <= t_signal:
            adx4_val = adx4[i] if i < len(adx4) else 0
            break

    pi = n - 2
    ema_dir_long  = ema5[pi] > ema10[pi]
    ema_dir_short = ema5[pi] < ema10[pi]

    cond_1h_adx = adx1[pi] > ADX_1H_MIN
    cond_4h_adx = adx4_val < ADX_4H_MAX
    cond_vol    = vr[pi-1] > VOL_RATIO_MIN if pi-1 >= 0 else False

    if ema_dir_long and cond_1h_adx and cond_4h_adx and rsi_v[pi] > RSI_LONG_MIN and cond_vol:
        return 'long'
    elif ema_dir_short and cond_1h_adx and cond_4h_adx and rsi_v[pi] < RSI_SHORT_MAX and cond_vol:
        return 'short'
    return None

def manage_positions(state):
    """扫描持仓，实时价触发TP/SL平仓"""
    try:
        ticker = exchange.fetch_ticker(SYMBOL)
        price = ticker['last']
    except:
        log("获取实时价失败")
        return False

    exit_kl = int(time.time() // 3600)

    # LONG平仓
    surviving = []
    for pos in state.get('longpos', []):
        entry = pos['entry']
        pnl = (price - entry) / entry
        if pnl >= TP_PCT:
            if close_position('LONG', pos, price, '止盈'):
                state['lastexitkl_time'] = exit_kl
                continue
        if pnl <= -SL_PCT:
            if close_position('LONG', pos, price, '止损'):
                state['lastexitkl_time'] = exit_kl
                continue
        surviving.append(pos)
    state['longpos'] = surviving

    # SHORT平仓
    surviving = []
    for pos in state.get('shortpos', []):
        entry = pos['entry']
        pnl = (entry - price) / entry
        if pnl >= TP_PCT:
            if close_position('SHORT', pos, price, '止盈'):
                state['lastexitkl_time'] = exit_kl
                continue
        if pnl <= -SL_PCT:
            if close_position('SHORT', pos, price, '止损'):
                state['lastexitkl_time'] = exit_kl
                continue
        surviving.append(pos)
    state['shortpos'] = surviving

    return True

def close_position(side, pos, price, reason):
    """市价平仓"""
    try:
        exchange.create_order(
            symbol=SYMBOL,
            type='market',
            side='sell',
            amount=QTY,
            params={'reduceOnly': True, 'positionSide': 'LONG' if side == 'LONG' else 'SHORT'}
        )
        entry = pos['entry']
        pnl = (price-entry)/entry if side == 'LONG' else (entry-price)/entry
        msg = f"HYPE {side}平仓 {reason}: entry={entry:.4f} exit={price:.4f} PnL={pnl*100:+.2f}%"
        log(msg)
        work_log(reason, msg)
        notify(msg)
        return True
    except Exception as e:
        log(f"平仓失败: {e}")
        return False

def open_position(side, price):
    """市价开仓"""
    try:
        ps = 'LONG' if side == 'LONG' else 'SHORT'
        order = exchange.create_order(
            symbol=SYMBOL,
            type='market',
            side='buy' if side == 'LONG' else 'sell',
            amount=QTY,
            params={'positionSide': ps}
        )
        fill_price = float(order.get('price', price) or price)
        ts = datetime.now(timezone.utc).isoformat()

        state = load_state()
        new_pos = {
            'entry': fill_price,
            'signal': f'EMA5/10{"金叉" if side=="LONG" else "死叉"}',
            'opentime': ts
        }
        if side == 'LONG':
            state['longpos'].append(new_pos)
        else:
            state['shortpos'].append(new_pos)
        state['lastentrykl_time'] = int(time.time() // 3600)
        save_state(state)

        msg = f"HYPE {side}开仓: entry={fill_price:.4f} qty={QTY}"
        log(msg)
        work_log('开仓', msg)
        notify(msg)
        return True
    except Exception as e:
        log(f"开仓失败: {e}")
        work_log('开仓失败', str(e))
        return False

def check_position_lock():
    """交易所仓位保护: 同边≥MAX_POS*QTY则拒绝"""
    try:
        pos = exchange.fetch_positions([SYMBOL])
        for p in pos:
            amt = abs(float(p.get('contracts', 0) or 0))
            if p.get('side', '') == 'long' and amt >= MAX_POS * QTY:
                return True
            if p.get('side', '') == 'short' and amt >= MAX_POS * QTY:
                return True
    except:
        pass
    return False

# ========== 设置杠杆 ==========
def setup():
    try:
        exchange.set_leverage(LEVERAGE, SYMBOL)
        exchange.set_margin_mode('isolated', SYMBOL)
        log(f"杠杆 {LEVERAGE}x 逐仓 已设置")
    except Exception as e:
        log(f"杠杆设置: {e}")

# ========== 主循环 ==========
def main():
    log("="*50)
    log("HYPE v4.0 EMA5/10策略启动")
    log(f"QTY={QTY} | LEV={LEVERAGE}x | TP={TP_PCT*100}% | SL={SL_PCT*100}%")
    log(f"ADX1h>{ADX_1H_MIN} | ADX4h<{ADX_4H_MAX} | RSI_LONG>{RSI_LONG_MIN} | RSI_SHORT<{RSI_SHORT_MAX}")
    log(f"量比>{VOL_RATIO_MIN}x | 仓位: {MAX_POS}仓/边")
    log("="*50)
    notify("HYPE v4.0 EMA5/10策略已启动")

    setup()

    while True:
        start = time.time()

        try:
            if os.path.exists(PAUSE_FILE):
                time.sleep(5)
                continue

            kl_1h = [extract(k) for k in fetch_klines('1h', 200)]
            kl_4h = [extract(k) for k in fetch_klines('4h', 200)]

            if len(kl_1h) < 100 or len(kl_4h) < 50:
                log(f"数据不足: 1h={len(kl_1h)} 4h={len(kl_4h)}")
                time.sleep(10)
                continue

            state = load_state()
            if 'lastexitkl_time' not in state:
                state['lastexitkl_time'] = 0
            if 'lastentrykl_time' not in state:
                state['lastentrykl_time'] = 0
            if 'longpos' not in state:
                state['longpos'] = []
            if 'shortpos' not in state:
                state['shortpos'] = []

            # 平仓管理
            manage_positions(state)
            save_state(state)

            # 仓位锁
            if check_position_lock():
                time.sleep(1)
                continue

            now_kl = int(time.time() // 3600)
            # 同K线平仓后冷却
            if state['lastexitkl_time'] == now_kl:
                time.sleep(1)
                continue
            # 同K线仅开一次
            if state['lastentrykl_time'] == now_kl:
                time.sleep(1)
                continue

            signal = check_signal(kl_1h, kl_4h)

            if signal == 'long' and len(state['longpos']) < MAX_POS:
                ticker = exchange.fetch_ticker(SYMBOL)
                open_position('LONG', ticker['last'])

            elif signal == 'short' and len(state['shortpos']) < MAX_POS:
                ticker = exchange.fetch_ticker(SYMBOL)
                open_position('SHORT', ticker['last'])

        except Exception as e:
            log(f"循环异常: {e}")
            work_log('异常', str(e))

        elapsed = time.time() - start
        if elapsed < 1:
            time.sleep(1 - elapsed)

if __name__ == '__main__':
    main()
