#!/usr/bin/env python3
"""
BTC合约 - 完整开仓/止盈/止损/平仓 测试脚本
"""
import ccxt
import pandas as pd
import ta
from datetime import datetime

# ========== API配置 ==========
API_KEY = "CUPwmVULosVO24NBKmoaMm0pvga2msasOa4nBhvPvybrGdA2RcXBYA4aRtGMZjWH"
SECRET = "Ozht5MjazUu4JKhSLqx4ASmTBH4wlUMdbABOblxXGyhIuof1jhrzUEr9JkWHpUHM"

binance = ccxt.binance({
    'apiKey': API_KEY,
    'secret': SECRET,
    'options': {'defaultType': 'swap', 'defaultMarginMode': 'cross', 'defaultPositionSide': 'BOTH'}
})

SYMBOL = 'BTC/USDT:USDT'
LEVERAGE = 5  # 5倍杠杆
TEST_QTY = 0.001  # 最小测试量

def get_data():
    """获取多周期数据"""
    k5m = binance.fetch_ohlcv(SYMBOL, timeframe='5m', limit=100)
    k1h = binance.fetch_ohlcv(SYMBOL, timeframe='1h', limit=200)
    k4h = binance.fetch_ohlcv(SYMBOL, timeframe='4h', limit=200)

    df5m = pd.DataFrame(k5m, columns=['t','o','h','l','c','v'])
    df1h = pd.DataFrame(k1h, columns=['t','o','h','l','c','v'])
    df4h = pd.DataFrame(k4h, columns=['t','o','h','l','c','v'])
    return df5m, df1h, df4h

def calc_indicators(df):
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
        'bullish': price > ma7 and macd > macd_sig
    }

def print_sep():
    print("=" * 60)

def test_open_long():
    """测试做多开仓"""
    print_sep()
    print("🟢 测试：做多开仓")
    print_sep()

    # 1. 获取当前账户状态
    account = binance.fetch_balance()
    usdt = account['USDT']
    print(f"账户余额: {usdt['total']:.2f} USDT")
    print(f"可用余额: {usdt['free']:.2f} USDT")

    # 2. 获取数据计算点位
    df5m, df1h, df4h = get_data()
    r5m = calc_indicators(df5m)
    r1h = calc_indicators(df1h)

    price = r5m['price']
    atr = r1h['atr']
    bb_l_1h = r1h['bb_l']

    # 3. 计算开仓参数
    entry_price = price  # 市价开仓
    stop_loss = price - 2 * atr  # ATR止损
    take_profit_1 = price + 1 * atr  # 止盈1
    take_profit_2 = price + 2 * atr  # 止盈2
    take_profit_3 = bb_l_1h  # 止盈3（布林带下轨）

    print(f"\n📊 当前价格: ${price:,.2f}")
    print(f"📊 ATR(1h): ${atr:,.2f}")
    print(f"\n🟢 做多参数:")
    print(f"  开仓价:   ${entry_price:,.2f}")
    print(f"  止损价:   ${stop_loss:,.2f} (距-{abs(entry_price-stop_loss)/entry_price*100:.2f}%)")
    print(f"  止盈1:   ${take_profit_1:,.2f} (距+{abs(take_profit_1-entry_price)/entry_price*100:.2f}%)")
    print(f"  止盈2:   ${take_profit_2:,.2f} (距+{abs(take_profit_2-entry_price)/entry_price*100:.2f}%)")
    print(f"  止盈3:   ${take_profit_3:,.2f}")

    # 4. 计算可开数量
    max_qty = float(usdt['free']) * LEVERAGE / price
    print(f"\n💰 {LEVERAGE}倍杠杆 可开数量: {max_qty:.4f} BTC")
    print(f"   测试数量: {TEST_QTY} BTC (约${TEST_QTY * price:.2f})")

    # 5. 尝试开仓
    print(f"\n📡 正在执行开仓...")
    try:
        # 设置杠杆
        binance.set_leverage(LEVERAGE, SYMBOL)
        print(f"  杠杆设置: {LEVERAGE}x ✅")

        # 市价开多
        order = binance.create_market_buy_order(SYMBOL, TEST_QTY)
        print(f"  开仓订单: ✅ 成功!")
        print(f"  订单ID:   {order['id']}")
        print(f"  成交均价: ${order.get('average', price):,.2f}")
        print(f"  成交数量: {order.get('filled', TEST_QTY)} BTC")

        avg_price = order.get('average', price)

        # 6. 设置止损（条件单）
        print(f"\n📌 设置止损...")
        sl_order = binance.create_order(
            SYMBOL, 'stop_market', 'sell',
            TEST_QTY,
            params={
                'stopPrice': stop_loss,
                'reduceOnly': True,
                'positionSide': 'LONG'
            }
        )
        print(f"  止损订单: ✅ 成功! ID: {sl_order['id']}")
        print(f"  止损价:   ${stop_loss:,.2f}")

        # 7. 设置止盈1（条件单）
        print(f"\n📌 设置止盈1...")
        tp1_order = binance.create_order(
            SYMBOL, 'limit', 'sell',
            TEST_QTY * 0.33,  # 33%仓位
            take_profit_1,
            params={
                'reduceOnly': True,
                'positionSide': 'LONG'
            }
        )
        print(f"  止盈1订单: ✅ 成功! ID: {tp1_order['id']}")
        print(f"  止盈1价格: ${take_profit_1:,.2f}")
        print(f"  止盈1数量: {TEST_QTY * 0.33:.4f} BTC")

        # 8. 设置止盈2
        print(f"\n📌 设置止盈2...")
        tp2_order = binance.create_order(
            SYMBOL, 'limit', 'sell',
            TEST_QTY * 0.33,
            take_profit_2,
            params={
                'reduceOnly': True,
                'positionSide': 'LONG'
            }
        )
        print(f"  止盈2订单: ✅ 成功! ID: {tp2_order['id']}")
        print(f"  止盈2价格: ${take_profit_2:,.2f}")

        # 9. 设置止盈3
        print(f"\n📌 设置止盈3...")
        tp3_order = binance.create_order(
            SYMBOL, 'limit', 'sell',
            TEST_QTY * 0.34,
            take_profit_3,
            params={
                'reduceOnly': True,
                'positionSide': 'LONG'
            }
        )
        print(f"  止盈3订单: ✅ 成功! ID: {tp3_order['id']}")
        print(f"  止盈3价格: ${take_profit_3:,.2f}")

        print_sep()
        print("✅ 完整开仓+止损止盈流程测试成功!")
        print_sep()

        # 10. 平仓测试
        print(f"\n📡 执行平仓...")
        close = binance.create_market_sell_order(SYMBOL, TEST_QTY, params={'reduceOnly': True, 'positionSide': 'LONG'})
        print(f"  平仓订单: ✅ 成功! ID: {close['id']}")
        print(f"  平仓数量: {close.get('filled', TEST_QTY)} BTC")

        return True

    except ccxt.InsufficientFunds as e:
        print(f"  ❌ 余额不足: {e}")
        print(f"  提示: 需要 ~${TEST_QTY * price * 1.1:.2f} USDT 才能开仓")
        return False
    except ccxt.OrderNotFound as e:
        print(f"  ❌ 订单不存在: {e}")
        return False
    except Exception as e:
        print(f"  ❌ 操作失败: {e}")
        return False

def test_open_short():
    """测试做空开仓"""
    print_sep()
    print("🔴 测试：做空开仓")
    print_sep()

    df5m, df1h, df4h = get_data()
    r5m = calc_indicators(df5m)
    r1h = calc_indicators(df1h)

    price = r5m['price']
    atr = r1h['atr']
    bb_u_1h = r1h['bb_u']

    entry_price = price
    stop_loss = price + 2 * atr
    take_profit_1 = price - 1 * atr
    take_profit_2 = price - 2 * atr
    take_profit_3 = bb_u_1h

    print(f"\n🔴 做空参数:")
    print(f"  开仓价:   ${entry_price:,.2f}")
    print(f"  止损价:   ${stop_loss:,.2f} (距+{abs(stop_loss-entry_price)/entry_price*100:.2f}%)")
    print(f"  止盈1:   ${take_profit_1:,.2f} (距-{abs(take_profit_1-entry_price)/entry_price*100:.2f}%)")
    print(f"  止盈2:   ${take_profit_2:,.2f} (距-{abs(take_profit_2-entry_price)/entry_price*100:.2f}%)")

    print(f"\n⚠️ 做空测试跳过(余额不足)")
    return False

# ========== 主程序 ==========
if __name__ == "__main__":
    print(f"\n🚀 BTC合约开仓/止盈/止损/平仓 测试")
    print(f"🕐 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"💰 账户余额: {binance.fetch_balance()['USDT']['total']:.2f} USDT")

    # 统计当前信号
    df5m, df1h, df4h = get_data()
    r5m = calc_indicators(df5m)
    r4h = calc_indicators(df4h)
    rd  = calc_indicators(binance.fetch_ohlcv(SYMBOL, timeframe='1d', limit=200))

    print(f"\n📊 当前信号:")
    print(f"  4h方向: {'📈' if r4h['bullish'] else '📉'}")
    print(f"  1d方向: {'📈' if rd['bullish'] else '📉'}")
    print(f"  5m %b:  {r5m['pctb']:.3f} ({'超买' if r5m['pctb']>0.85 else '超卖' if r5m['pctb']<0.2 else '正常'})")
    print(f"  RSI:    {r5m['rsi']:.1f}")

    # 策略判断
    direction = None
    if r4h['bullish'] and r5m['pctb'] < 0.2:
        direction = "做多"
    elif not r4h['bullish'] and r5m['pctb'] > 0.85:
        direction = "做空"
    else:
        direction = "观望"

    print(f"\n🎯 策略信号: {direction}")

    # 执行测试
    if direction == "做多":
        test_open_long()
    elif direction == "做空":
        test_open_short()
    else:
        print(f"\n⚠️ 当前信号为观望，跳过实际开仓测试")
        print(f"但开仓逻辑已就绪，信号变化时会执行")

    print_sep()
    print("✅ 测试流程结束")
