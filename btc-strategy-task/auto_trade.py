#!/usr/bin/env python3
"""
BTC合约 自动交易策略
- 10秒监控 + 多周期指标分析
- 自定义止盈止损
- 开仓理由记录 + 微信通知
"""
import ccxt
import pandas as pd
import ta
import time
import json
import os
import subprocess
from datetime import datetime

# ========== API配置 ==========
API_KEY = "CUPwmVULosVO24NBKmoaMm0pvga2msasOa4nBhvPvybrGdA2RcXBYA4aRtGMZjWH"
SECRET = "Ozht5MjazUu4JKhSLqx4ASmTBH4wlUMdbABOblxXGyhIuof1jhrzUEr9JkWHpUHM"

binance = ccxt.binance({
    'apiKey': API_KEY,
    'secret': SECRET,
    'options': {'defaultType': 'swap', 'defaultPositionSide': 'LONG', 'marginMode': 'cross'}
})

SYMBOL = 'BTC/USDT:USDT'
QTY = 0.002
LEVERAGE = 20
STATE_FILE = '/root/.openclaw/workspace/btc-strategy-task/databases/state.json'
ALERT_FILE = '/root/.openclaw/workspace/btc-strategy-task/databases/last_alert.json'

# ========== 工具 ==========
def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")

def save_state(state):
    with open(STATE_FILE, 'w') as f:
        json.dump(state, f)

def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE) as f:
            return json.load(f)
    return {'in_position': False}

def notify_alert(msg):
    """写入告警文件，供agent推送微信"""
    with open(ALERT_FILE, 'w') as f:
        json.dump({'time': datetime.now().isoformat(), 'msg': msg}, f)

def send_wechat_msg(msg):
    """直接发送微信消息"""
    try:
        import urllib.request
        # 写入触发文件让agent发送
        with open('/root/.openclaw/workspace/btc-strategy-task/databases/pending_wechat.txt', 'w') as f:
            f.write(msg)
    except:
        pass

def get_data():
    k5m = binance.fetch_ohlcv(SYMBOL, timeframe='5m', limit=100)
    k1h = binance.fetch_ohlcv(SYMBOL, timeframe='1h', limit=200)
    k4h = binance.fetch_ohlcv(SYMBOL, timeframe='4h', limit=200)
    k1d = binance.fetch_ohlcv(SYMBOL, timeframe='1d', limit=200)
    return k5m, k1h, k4h, k1d

def calc(df):
    close = df['c']
    high = df['h']
    low = df['l']
    lv = len(df) - 1

    ma7 = ta.trend.SMAIndicator(close, 7).sma_indicator().iloc[lv]
    ma25 = ta.trend.SMAIndicator(close, 25).sma_indicator().iloc[lv]
    macd_ind = ta.trend.MACD(close)
    macd = macd_ind.macd().iloc[lv]
    macd_sig = macd_ind.macd_signal().iloc[lv]
    rsi = ta.momentum.RSIIndicator(close).rsi().iloc[lv]
    bb = ta.volatility.BollingerBands(close)
    bb_u = bb.bollinger_hband().iloc[lv]
    bb_l = bb.bollinger_lband().iloc[lv]
    bb_m = bb.bollinger_mavg().iloc[lv]
    atr = ta.volatility.AverageTrueRange(high, low, close).average_true_range().iloc[lv]
    price = close.iloc[lv]
    pctb = (price - bb_l) / (bb_u - bb_l) if (bb_u - bb_l) != 0 else 0.5

    return {
        'price': price, 'ma7': ma7, 'ma25': ma25,
        'macd': macd, 'macd_sig': macd_sig, 'rsi': rsi,
        'bb_u': bb_u, 'bb_l': bb_l, 'bb_m': bb_m,
        'atr': atr, 'pctb': pctb,
        'bullish': price > ma7 and macd > macd_sig,
        'bearish': price < ma7 and macd < macd_sig
    }

def check_entry(data):
    """
    开仓信号分析 + 理由说明
    """
    r5m = data['5m']
    r1h = data['1h']
    r4h = data['4h']
    rd  = data['1d']

    price = r5m['price']
    atr = r1h['atr']
    pctb = r5m['pctb']
    rsi5m = r5m['rsi']
    rsi1h = r1h['rsi']

    reasons = []

    # === 做多分析 ===
    if not r4h['bullish'] and not rd['bullish']:
        reasons.append(f"4h均线{'多头' if r4h['bullish'] else '空头'} ❌")
        reasons.append(f"1d均线{'多头' if rd['bullish'] else '空头'} ❌")

        if pctb < 0.2:
            # 计算偏离
            bb_l = r5m['bb_l']
            dist = (price - bb_l) / price * 100
            reasons.append(f"5m %b={pctb:.3f} < 0.2 超出布林下轨偏离{dist:.1f}% ✅")
            reasons.append(f"5m RSI={rsi5m:.1f} {'偏低' if rsi5m<40 else '正常'}")

            sl = price - 2 * atr
            tp1 = price + 0.01 * price
            tp2 = price + 0.02 * price

            entry_reason = (
                f"【做多信号】大周期空头+5m超卖反弹\n"
                f"理由: 4h+1d均线空头,价格跌至布林下轨偏离{pctb:.1%}\n"
                f"入场: ${price:,.2f}\n"
                f"止损: ${sl:,.2f} (-{2*atr/price*100:.1f}%, 2×ATR)\n"
                f"止盈1: ${tp1:,.2f} (+{1.5*atr/price*100:.1f}%, 1.5×ATR)\n"
                f"止盈2: ${tp2:,.2f} (+{3*atr/price*100:.1f}%, 3×ATR)"
            )
            return 'long', entry_reason, price, atr

    # 大周期多头 + 回调做多
    if r4h['bullish'] and rd['bullish'] and pctb < 0.2:
        bb_l = r5m['bb_l']
        dist = (price - bb_l) / price * 100
        reasons.append(f"4h均线多头 ✅ | 1d均线多头 ✅")

        if rsi5m > 35 and rsi5m < 60:
            reasons.append(f"5m RSI={rsi5m:.1f} 回调完毕")

            sl = price - 2 * atr
            tp1 = price + 0.01 * price
            tp2 = price + 0.02 * price

            entry_reason = (
                f"【做多信号】大周期多头+5m回调支撑\n"
                f"理由: 4h+1d均线多头,价格回踩布林下轨偏离{pctb:.1%}\n"
                f"5m RSI={rsi5m:.1f} 回调到位\n"
                f"入场: ${price:,.2f}\n"
                f"止损: ${sl:,.2f} (-{2*atr/price*100:.1f}%, 2×ATR)\n"
                f"止盈1: ${tp1:,.2f} (+{1.5*atr/price*100:.1f}%, 1.5×ATR)\n"
                f"止盈2: ${tp2:,.2f} (+{3*atr/price*100:.1f}%, 3×ATR)"
            )
            return 'long', entry_reason, price, atr

    # === 做空分析 ===
    if r4h['bullish'] and rd['bullish'] and pctb > 0.85:
        bb_u = r5m['bb_u']
        dist = (bb_u - price) / price * 100
        reasons.append(f"4h均线多头 ✅ | 1d均线多头 ✅")
        reasons.append(f"5m %b={pctb:.3f} > 0.85 触及布林上轨偏离{dist:.1f}% ✅")
        reasons.append(f"5m RSI={rsi5m:.1f} {'偏高' if rsi5m>65 else '正常'}")

        sl = price + 2 * atr
        tp1 = price - 0.01 * price
        tp2 = price - 0.02 * price

        entry_reason = (
            f"【做空信号】大周期多头+5m超买\n"
            f"理由: 4h+1d均线多头,价格触及布林上轨偏离{pctb:.1%}\n"
            f"5m RSI={rsi5m:.1f}\n"
            f"入场: ${price:,.2f}\n"
            f"止损: ${sl:,.2f} (+{2*atr/price*100:.1f}%, 2×ATR)\n"
            f"止盈1: ${tp1:,.2f} (-{1.5*atr/price*100:.1f}%, 1.5×ATR)\n"
            f"止盈2: ${tp2:,.2f} (-{3*atr/price*100:.1f}%, 3×ATR)"
        )
        return 'short', entry_reason, price, atr

    if not r4h['bullish'] and not rd['bullish'] and pctb > 0.85:
        bb_u = r5m['bb_u']
        reasons.append(f"4h均线空头 ❌ | 1d均线空头 ❌")
        reasons.append(f"5m %b={pctb:.3f} > 0.85 触及布林上轨 ✅")

        sl = price + 2 * atr
        tp1 = price - 0.01 * price
        tp2 = price - 0.02 * price

        entry_reason = (
            f"【做空信号】大周期空头+5m反弹压力\n"
            f"理由: 4h+1d均线空头,价格反弹至布林上轨偏离{pctb:.1%}\n"
            f"入场: ${price:,.2f}\n"
            f"止损: ${sl:,.2f} (+{2*atr/price*100:.1f}%, 2×ATR)\n"
            f"止盈1: ${tp1:,.2f} (-{1.5*atr/price*100:.1f}%, 1.5×ATR)\n"
            f"止盈2: ${tp2:,.2f} (-{3*atr/price*100:.1f}%, 3×ATR)"
        )
        return 'short', entry_reason, price, atr

    # 观望
    observe = f"观望 | 4h{'多头' if r4h['bullish'] else '空头'} | 5m %b={pctb:.3f} | RSI={rsi5m:.1f}"
    return None, observe, price, atr

def open_position(direction, entry_price, atr, reason, qty):
    """开仓 + 挂止盈止损"""
    positionSide = 'LONG' if direction == 'long' else 'SHORT'

    binance.set_leverage(LEVERAGE, SYMBOL)

    if direction == 'long':
        order = binance.create_order(SYMBOL, 'market', 'buy', qty, params={'positionSide': positionSide})
    else:
        order = binance.create_order(SYMBOL, 'market', 'sell', qty, params={'positionSide': positionSide})

    avg_price = order.get('average', entry_price)

    # 止损 - 条件委托（STOP_MARKET，市价触发平仓）
    sl_price = round(avg_price * (0.98 if direction == 'long' else 1.02), 1)
    sl_order = binance.create_order(
        SYMBOL, 'STOP_MARKET',
        'sell' if direction == 'long' else 'buy',
        qty,
        params={'stopPrice': sl_price, 'positionSide': positionSide, 'newOrderRespType': 'ACK'}
    )

    # 止盈 - 条件委托（TAKE_PROFIT_MARKET，市价触发平仓）
    tp_price = round(avg_price * (1.03 if direction == 'long' else 0.97), 1)
    tp_order = binance.create_order(
        SYMBOL, 'TAKE_PROFIT_MARKET',
        'sell' if direction == 'long' else 'buy',
        qty,
        params={'stopPrice': tp_price, 'positionSide': positionSide, 'newOrderRespType': 'ACK'}
    )

    state = {
        'in_position': True,
        'direction': direction,
        'entry_price': avg_price,
        'stop_loss': sl_price,
        'tp': tp_price,
        'qty': qty,
        'atr': atr,
        'reason': reason,
        'open_time': datetime.now().isoformat(),
    }
    save_state(state)

    # 发送微信通知
    wechat_msg = (
        f"🚨 BTC开仓通知\n"
        f"━━━━━━━━━━━━━━━━\n"
        f"方向: {'🟢 做多' if direction == 'long' else '🔴 做空'}\n"
        f"杠杆: {LEVERAGE}x\n"
        f"数量: {qty} BTC\n"
        f"开仓价: ${avg_price:,.2f}\n"
        f"━━━━━━━━━━━━━━━━\n"
        f"止损: ${sl_price:,.2f} (-{abs(sl_price-avg_price)/avg_price*100:.1f}%)\n"
        f"止盈: ${tp_price:,.2f} (+{abs(tp_price-avg_price)/avg_price*100:.1f}%)\n"
        f"━━━━━━━━━━━━━━━━\n"
        f"📋 开仓理由:\n{reason}\n"
        f"━━━━━━━━━━━━━━━━\n"
        f"⏰ {datetime.now().strftime('%H:%M:%S')}"
    )
    # 直接写入待发送文件（守护进程检测到此文件后推送微信）
    try:
        with open('/root/.openclaw/workspace/btc-strategy-task/databases/pending_wechat.txt', 'w') as f:
            f.write(wechat_msg)
        log(f"🚨 微信通知已写入待发送队列")
    except Exception as e:
        log(f"⚠️ 通知写入失败: {e}")
    notify_alert(wechat_msg)

    return state

def close_position():
    """平仓"""
    pos = binance.fetch_positions()
    for p in pos:
        if p.get('symbol') == SYMBOL and float(p.get('contracts', 0)) > 0:
            qty = float(p['contracts'])
            side = p['side']
            positionSide = 'LONG' if side == 'long' else 'SHORT'

            close = binance.create_order(
                SYMBOL, 'market',
                'sell' if side == 'long' else 'buy',
                qty,
                params={'positionSide': positionSide}
            )

            entry = float(p.get('entryPrice', 0))
            close_price = close.get('average', 0)
            pnl = (close_price - entry) * qty if side == 'long' else (entry - close_price) * qty

            log(f"✅ 平仓完成! 盈亏: ${pnl:+.4f}")

            save_state({'in_position': False, 'last_close_time': time.time()})

            wechat_msg = (
                f"✅ BTC平仓通知\n"
                f"━━━━━━━━━━━━━━━━\n"
                f"方向: {side.upper()}\n"
                f"平仓价: ${close_price:,.2f}\n"
                f"盈亏: ${pnl:+.4f}\n"
                f"⏰ {datetime.now().strftime('%H:%M:%S')}"
            )
            notify_alert(wechat_msg)
            send_wechat_msg(wechat_msg)
            return True
    return False


def check_and_fix_orders():
    """
    每60秒检查持仓对应的止盈止损单
    发现异常（丢失/被撤销）自动重新挂单
    """
    try:
        pos = binance.fetch_positions()
        has_pos = any(p.get('symbol') == SYMBOL and float(p.get('contracts', 0)) > 0 for p in pos)
        
        if not has_pos:
            return

        for p in pos:
            if p.get('symbol') != SYMBOL or float(p.get('contracts', 0)) <= 0:
                continue

            entry = float(p['entryPrice'])
            qty = float(p['contracts'])
            side = p['side']
            positionSide = 'LONG' if side == 'long' else 'SHORT'
            close_side = 'sell' if side == 'long' else 'buy'

            if side == 'short':
                sl = round(entry * 1.02, 1)
                tp1 = round(entry * 0.98, 1)
                tp2 = round(entry * 0.96, 1)
                tp3 = round(entry * 0.94, 1)
            else:
                sl = round(entry * 0.98, 1)
                tp1 = round(entry * 1.02, 1)
                tp2 = round(entry * 1.04, 1)
                tp3 = round(entry * 1.06, 1)

            try:
                open_orders = binance.fetch_open_orders(SYMBOL)
                open_prices = set()
                for o in open_orders:
                    # 限价单按价格检测，条件单按stopPrice检测
                    p = o.get('price')
                    sp = o.get('stopPrice')
                    if p:
                        open_prices.add(float(p))
                    if sp:
                        open_prices.add(float(sp))
            except:
                open_prices = set()

            # 计算各订单数量（最低0.001）
            tp1_qty = max(0.001, round(qty * 0.33, 3))
            tp2_qty = max(0.001, round(qty * 0.33, 3))
            tp3_qty = max(0.001, round(qty * 0.34, 3))

            # SL/TP对应的价格和数量
            order_targets = [
                (sl, qty, '止损', 'STOP'),
                (tp1, tp1_qty, '止盈1', 'TAKE_PROFIT'),
                (tp2, tp2_qty, '止盈2', 'TAKE_PROFIT'),
                (tp3, tp3_qty, '止盈3', 'TAKE_PROFIT'),
            ]

            missing = []
            for target_price, target_qty, name, order_type in order_targets:
                if target_price not in open_prices:
                    missing.append((target_price, target_qty, name, order_type))

            if missing:
                log(f"⚠️ 检测到缺失挂单: {[m[0] for m in missing]}")
                for target_price, target_qty, name, order_type in missing:
                    try:
                        o = binance.create_order(
                            SYMBOL, order_type,
                            close_side, target_qty,
                            price=target_price,
                            params={'stopPrice': target_price, 'positionSide': positionSide}
                        )
                        log(f"  ✅ 补挂{name} ${target_price:,.2f} x {target_qty}")
                    except Exception as e:
                        log(f"  ❌ 补挂{name}失败: {e}")
            else:
                log(f"✅ 止盈止损单检查正常 (4/4 全部在挂)")
    except Exception as e:
        log(f"⚠️ 检查修复异常: {e}")


def print_status(data, state):
    r5m = data['5m']
    r1h = data['1h']
    r4h = data['4h']
    rd  = data['1d']
    price = r5m['price']
    pctb = r5m['pctb']
    rsi = r5m['rsi']
    bb_s = "🔴超买" if pctb > 0.85 else "🟢超卖" if pctb < 0.2 else "⚖️正常"
    rsi_s = "🔴" if rsi > 70 else "🟢" if rsi < 30 else "⚖️"

    now = datetime.now().strftime('%H:%M:%S')
    print(f"""
╔══════════════════════════════════════════════════════════════╗
║  BTC AUTO-TRADE  {now}                        ║
╠══════════════════════════════════════════════════════════════╣
║  💰 {price:>12,.2f}  |  ATR: {r1h['atr']:>6,.0f}  |  %b: {pctb:.3f} {bb_s}       ║
╠══════════════════════════════════════════════════════════════╣
║  4h: {'📈' if r4h['bullish'] else '📉'}  |  1d: {'📈' if rd['bullish'] else '📉'}  |  RSI: {rsi_s}{rsi:.1f}        ║""")

    if state.get('in_position'):
        entry = state.get('entry_price', 0)
        d = state.get('direction', '')
        pnl_pct = (price - entry) / entry * 100 if d == 'long' else (entry - price) / entry * 100
        pnl_icon = "📈" if pnl_pct > 0 else "📉"
        print(f"╠══════════════════════════════════════════════════════════════╣")
        print(f"║  📊 持仓: {d.upper()} @ ${entry:,.0f}  |  {pnl_icon}{pnl_pct:+.2f}%              ║")
        print(f"║  📌 SL: ${state.get('stop_loss',0):,.0f}  TP: ${state.get('tp',0):,.0f}    ║")
        print(f"╠══════════════════════════════════════════════════════════════╣")
        print(f"║  🎯 {state.get('reason','')[:52]}║")
    else:
        _, observe, _, _ = check_entry(data)
        print(f"╠══════════════════════════════════════════════════════════════╣")
        print(f"║  🎯 {observe[:52]}                          ║")
        print(f"╠══════════════════════════════════════════════════════════════╣")
        print(f"║  ⚪ 观望中                                              ║")

    print(f"╚══════════════════════════════════════════════════════════════╝")

# ========== 主循环 ==========
def main():
    log("🚀 BTC自动交易启动 | 10秒周期 | 20x | 0.002 BTC")
    log(f"做多: 大周期空->5m超卖(pctb<0.2) | 做空: 大周期多->5m超买(pctb>0.85)")

    state = load_state()
    if state.get('in_position'):
        log(f"⚠️ 检测到持仓: {state.get('direction')} @ ${state.get('entry_price',0):,.2f}")

    cycle = 0
    while True:
        try:
            cycle += 1
            k5m, k1h, k4h, k1d = get_data()
            df5m = pd.DataFrame(k5m, columns=['t','o','h','l','c','v'])
            df1h = pd.DataFrame(k1h, columns=['t','o','h','l','c','v'])
            df4h = pd.DataFrame(k4h, columns=['t','o','h','l','c','v'])
            df1d = pd.DataFrame(k1d, columns=['t','o','h','l','c','v'])

            data = {
                '5m': calc(df5m),
                '1h': calc(df1h),
                '4h': calc(df4h),
                '1d': calc(df1d)
            }

            state = load_state()

            # 检查持仓状态
            pos = binance.fetch_positions()
            has_pos = any(p.get('symbol') == SYMBOL and float(p.get('contracts', 0)) > 0 for p in pos)

            if not has_pos and state.get('in_position'):
                log("⚠️ 持仓已平，重置状态")
                save_state({'in_position': False, 'last_close_time': time.time()})
                state = {'in_position': False}

            # 打印状态
            print_status(data, state)

            # 每60秒(6轮)检查一次止盈止损单（已禁用，条件委托易触发Binance限制）
            # if cycle % 6 == 0:
            #     log(f"--- 60秒持仓检查 ---")
            #     check_and_fix_orders()

            # 无持仓 -> 检查开仓信号（平仓后5分钟冷却）
            if not has_pos:
                last_close = state.get('last_close_time', 0)
                if time.time() - last_close < 300:
                    remaining = int(300 - (time.time() - last_close))
                    if cycle % 6 == 0:  # 每分钟提示一次
                        log(f"⏳ 冷却中，还需 {remaining} 秒")
                else:
                    sig, reason, price, atr = check_entry(data)

                    if sig:
                        log(f"🚨 触发信号! {sig} | {reason.split(chr(10))[0]}")
                        try:
                            open_position(sig, price, atr, reason, QTY)
                        except Exception as e:
                            log(f"❌ 开仓失败: {e}")

            time.sleep(10)

        except KeyboardInterrupt:
            log("🛑 停止")
            state = load_state()
            if state.get('in_position'):
                if input("仍有持仓，是否平仓？(Y/n): ") != 'n':
                    close_position()
            break
        except Exception as e:
            log(f"❌ 异常: {e}")
            import traceback; traceback.print_exc()
            time.sleep(10)

if __name__ == "__main__":
    main()
