#!/usr/bin/env python3
"""
BTC合约任务自检脚本 v4.0
- 每5分钟执行一次
- 检查进程、API、持仓、策略信号、通知队列
- 适配v4.0趋势回调：双向各1仓 + TP2.5%/SL1.5% + 50x/0.007BTC
"""
import ccxt, os, json, subprocess, time, requests as req
from datetime import datetime

TASK_DIR = '/root/btc-strategy-backup/btc-strategy-task'
STATE_FILE = f'{TASK_DIR}/databases/state.json'
NOTIFY_QUEUE = f'{TASK_DIR}/databases/notify_queue.json'
LOG_DIR = f'{TASK_DIR}/logs/health_check'
SYMBOL = 'BTC/USDT:USDT'
QTY = 0.007
LEV = 50
TP_PCT = 2.5 / 100
SL_PCT = 1.5 / 100
os.makedirs(LOG_DIR, exist_ok=True)

def log(msg): print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")

def get_exchange():
    from api_config import API_KEY, SECRET
    return ccxt.binance({'apiKey': API_KEY, 'secret': SECRET, 'options': {'defaultType': 'swap'}})

def get_data():
    result = []
    for tf, limit in [('5m', 100), ('1h', 200), ('4h', 200), ('1d', 200)]:
        try:
            url = f'https://fapi.binance.com/fapi/v1/klines?symbol=BTCUSDT&interval={tf}&limit={limit}'
            r = req.get(url, timeout=5)
            kls = r.json()
            result.append([[int(k[0]), float(k[1]), float(k[2]), float(k[3]), float(k[4]), float(k[5])] for k in kls])
        except:
            result.append([])
    return result

def calc_indicators(df_data):
    import pandas as pd, ta
    df = pd.DataFrame(df_data, columns=['t','o','h','l','c','v'])
    close = df['c']; high = df['h']; low = df['l']; volume = df['v']
    lv = len(df) - 1
    price = close.iloc[lv]
    sma20 = ta.trend.SMAIndicator(close, 20).sma_indicator().iloc[lv]
    rsi = ta.momentum.RSIIndicator(close, 14).rsi().iloc[lv]
    try:
        adx_ind = ta.trend.ADXIndicator(high, low, close, 14)
        adx = adx_ind.adx().iloc[lv]
        adx_pos = adx_ind.adx_pos().iloc[lv]
        adx_neg = adx_ind.adx_neg().iloc[lv]
    except:
        adx = 25; adx_pos = 25; adx_neg = 25
    avg_vol = volume.iloc[max(0,lv-19):lv+1].mean()
    vr = float(volume.iloc[lv]) / float(avg_vol) if avg_vol > 0 else 1
    return {'price': price, 'sma20': sma20, 'rsi': rsi,
            'adx': adx, 'adx_pos': adx_pos, 'adx_neg': adx_neg, 'vol_ratio': vr}

def check_signal(r5, r1, r4, rd):
    """v4.0 趋势回调信号: LONG顺势追多 / SHORT顺势摸顶"""
    price = r5['price']; rsi5m = r5['rsi']; adx1h = r1['adx']; adx4h = r4['adx']
    sma5m = r5['sma20']; sma4h = r4['sma20']; sma1d = rd['sma20']
    
    if adx1h <= 25:
        return None, f"1hADX={adx1h:.1f}≤25"
    if adx4h >= 40:
        return None, f"4hADX={adx4h:.1f}≥40"
    if not (sma5m*0.99 <= price <= sma5m*1.01):
        return None, f"偏离SMA20 ±{abs(price/sma5m-1)*100:.1f}%"
    
    h4_bull = price > sma4h
    d1_bull = price > sma1d
    
    if h4_bull and d1_bull and rsi5m > 40:
        return 'LONG', 'LONG顺势追多'
    if (not h4_bull) and (not d1_bull) and rsi5m < 60:
        return 'SHORT', 'SHORT顺势摸顶'
    
    dir_4h = '多' if h4_bull else '空'
    dir_1d = '多' if d1_bull else '空'
    return None, f"4h{dir_4h}/1d{dir_1d} RSI={rsi5m:.1f}"

def check_all():
    ok, fail = 0, 0
    fixes = []
    
    # === 1. 进程 ===
    try:
        r = subprocess.run(['ps', 'aux'], capture_output=True, text=True)
        pids = [l.split()[1] for l in r.stdout.split('\n') if 'auto_trade.py' in l and 'grep' not in l and 'python3' in l]
        if pids:
            log(f"✅ 进程 PID={pids[-1]}"); ok += 1
        else:
            log(f"❌ 进程未运行"); fail += 1; fixes.append('restart')
    except Exception as e:
        log(f"❌ 进程检查失败: {e}"); fail += 1

    # === 2. API数据 + 策略信号 ===
    try:
        k5m, k1h, k4h, k1d = get_data()
        r5 = calc_indicators(k5m); r1 = calc_indicators(k1h)
        r4 = calc_indicators(k4h); rd = calc_indicators(k1d)

        price = r5['price']; rsi = r5['rsi']; vr = r5['vol_ratio']
        a1h = r1['adx']; a4h = r4['adx']
        b4h = price > r4['sma20']; b1d = price > rd['sma20']
        pct_from_sma = (price - r5['sma20']) / r5['sma20'] * 100

        sig, info = check_signal(r5, r1, r4, rd)
        sig_str = f"🔥 {info}" if sig else f"⏸ {info}"
        
        log(f"✅ API ${price:,.0f} | RSI={rsi:.1f} SMA20偏差{pct_from_sma:+.1f}% | "
            f"4h{'📈多' if b4h else '📉空'} 1d{'📈多' if b1d else '📉空'} | "
            f"ADX1h={a1h:.1f} ADX4h={a4h:.1f} vol={vr:.1f}x | {sig_str}")
        ok += 1
    except Exception as e:
        log(f"❌ API: {e}"); fail += 1

    # === 3. 持仓同步 ===
    try:
        exchange = get_exchange()
        ex_pos = exchange.fetch_positions()
        ex_long = None; ex_short = None
        for p in ex_pos:
            if p.get('symbol') != SYMBOL: continue
            qty = float(p.get('contracts', 0))
            if qty <= 0: continue
            side = 'long' if p['side'] in ('long', 'LONG') else 'short'
            entry = float(p['entryPrice'])
            if side == 'long': ex_long = {'entry': entry, 'qty': qty}
            else: ex_short = {'entry': entry, 'qty': qty}

        state = {}
        if os.path.exists(STATE_FILE):
            with open(STATE_FILE) as f: state = json.load(f)

        st_long = state.get('long_pos')
        st_short = state.get('short_pos')

        changed = False
        # v4.0 state: {'entry': price, 'signal': reason, 'open_time': iso}
        if ex_long and (not st_long or abs(st_long.get('entry', 0) - ex_long['entry']) > 50):
            state['long_pos'] = {'entry': ex_long['entry'], 'signal': '手动同步', 'open_time': datetime.now().isoformat()}
            changed = True
        elif not ex_long and st_long:
            state['long_pos'] = None; changed = True
        if ex_short and (not st_short or abs(st_short.get('entry', 0) - ex_short['entry']) > 50):
            state['short_pos'] = {'entry': ex_short['entry'], 'signal': '手动同步', 'open_time': datetime.now().isoformat()}
            changed = True
        elif not ex_short and st_short:
            state['short_pos'] = None; changed = True

        if changed:
            with open(STATE_FILE, 'w') as f: json.dump(state, f)

        detail = []
        if ex_long: detail.append(f"LONG ${ex_long['entry']:.0f}({ex_long['qty']}BTC)")
        if ex_short: detail.append(f"SHORT ${ex_short['entry']:.0f}({ex_short['qty']}BTC)")
        log(f"✅ 持仓 {' | '.join(detail) if detail else '无持仓'}"); ok += 1
    except Exception as e:
        log(f"❌ 持仓同步: {e}"); fail += 1

    # === 4. SL/TP检查 ===
    try:
        exchange = get_exchange()
        state = json.load(open(STATE_FILE)) if os.path.exists(STATE_FILE) else {}
        for d_key, direction, ps in [('long_pos','LONG','LONG'), ('short_pos','SHORT','SHORT')]:
            pos = state.get(d_key)
            if not pos: continue
            entry = pos.get('entry', 0)
            if not entry: continue
            sl_target = round(entry*(1-SL_PCT), 1) if direction=='LONG' else round(entry*(1+SL_PCT), 1)
            tp_target = round(entry*(1+TP_PCT), 1) if direction=='LONG' else round(entry*(1-TP_PCT), 1)
            
            # 查持仓量
            positions = exchange.fetch_positions()
            qty = 0
            for p in positions:
                if p.get('symbol') == SYMBOL and float(p.get('contracts', 0)) > 0:
                    if (direction == 'LONG' and p.get('side') == 'long') or \
                       (direction == 'SHORT' and p.get('side') == 'short'):
                        qty = float(p['contracts'])
                        break
            if qty == 0: continue
            
            try:
                algos = exchange.fapiprivate_get_openalgoorders({'symbol': 'BTCUSDT'})
            except:
                algos = []
            has_sl = any(o.get('orderType')=='STOP_MARKET' and o.get('positionSide')==ps for o in algos)
            has_tp = any(o.get('orderType')=='TAKE_PROFIT_MARKET' and o.get('positionSide')==ps for o in algos)
            
            sl_status = '✅' if has_sl else '❌缺失'
            tp_status = '✅' if has_tp else '❌缺失'
            log(f"  {direction} ${entry:.0f} | SL${sl_target} {sl_status} | TP${tp_target} {tp_status}")
            
            if not has_sl or not has_tp:
                close_side = 'sell' if direction == 'LONG' else 'buy'
                try:
                    if not has_sl:
                        exchange.create_order(SYMBOL, 'STOP_MARKET', close_side, qty,
                            params={'stopPrice': sl_target, 'positionSide': ps})
                        log(f"   🔧 补挂SL ${sl_target}")
                    if not has_tp:
                        exchange.create_order(SYMBOL, 'TAKE_PROFIT_MARKET', close_side, qty,
                            params={'stopPrice': tp_target, 'positionSide': ps})
                        log(f"   🔧 补挂TP ${tp_target}")
                except Exception as e:
                    log(f"   ⚠️ 补挂失败: {e}")
        ok += 1
    except Exception as e:
        log(f"⚠️ SL/TP: {e}")

    # === 5. 通知队列 ===
    try:
        queue = []
        if os.path.exists(NOTIFY_QUEUE):
            with open(NOTIFY_QUEUE) as f:
                q = json.load(f)
                queue = q if isinstance(q, list) else []
        pending = sum(1 for x in queue if isinstance(x, dict) and not x.get('sent', False))
        if pending:
            log(f"⚠️ 通知: {pending}条待转发"); fail += 1
        else:
            log(f"✅ 通知队列正常"); ok += 1
    except:
        log(f"⚠️ 通知检查失败")

    # === 执行修复 ===
    for fix in fixes:
        if fix == 'restart':
            log('🔧 重启 auto_trade.py...')
            subprocess.run(['pkill', '-f', 'auto_trade.py'], capture_output=True)
            time.sleep(2)
            subprocess.Popen(f'cd {TASK_DIR} && python3 -u auto_trade.py > logs/auto_trade_v4.log 2>&1 &', shell=True)
            log('✅ 已重启')

    msg = f"🔍 自检: {ok}✅ {fail}❌"
    if fixes: msg += f" | 已修{len(fixes)}项"
    log(f"=== {msg} ===")

    report = {'time': datetime.now().isoformat(), 'ok': ok, 'fail': fail, 'fixes': fixes}
    check_log = f'{LOG_DIR}/check_log.json'
    logs = []
    if os.path.exists(check_log):
        try:
            with open(check_log) as f: logs = json.load(f)
        except: pass
    logs.append(report)
    with open(check_log, 'w') as f: json.dump(logs[-100:], f)

    return report

if __name__ == '__main__':
    check_all()
