#!/usr/bin/env python3
"""
BTC/USDT 永续合约 - 5秒实时监控
"""
import ccxt
import pandas as pd
import ta
from datetime import datetime

binance = ccxt.binance({'options': {'defaultType': 'swap'}})

def get_live_data():
    """获取实时数据"""
    try:
        klines_5m = binance.fetch_ohlcv('BTC/USDT:USDT', timeframe='5m', limit=50)
        klines_1h = binance.fetch_ohlcv('BTC/USDT:USDT', timeframe='1h', limit=100)
        klines_4h = binance.fetch_ohlcv('BTC/USDT:USDT', timeframe='4h', limit=100)
        ticker = binance.fetch_ticker('BTC/USDT:USDT')
        funding = binance.fetch_funding_rate('BTC/USDT:USDT')
        ob = binance.fetch_order_book('BTC/USDT:USDT', 5)
        return klines_5m, klines_1h, klines_4h, ticker, funding, ob
    except Exception:
        return None

def calc_bb_pctb(df):
    close = df['c']
    bb = ta.volatility.BollingerBands(close)
    lv = len(df) - 1
    price = close.iloc[lv]
    upper = bb.bollinger_hband().iloc[lv]
    lower = bb.bollinger_lband().iloc[lv]
    mid = bb.bollinger_mavg().iloc[lv]
    bandwidth = upper - lower
    pctb = (price - lower) / bandwidth if bandwidth != 0 else 0.5
    return price, upper, mid, lower, pctb

def calc_rsi(df):
    return float(ta.momentum.RSIIndicator(df['c']).rsi().iloc[-1])

def calc_macd(df):
    m = ta.trend.MACD(df['c'])
    lv = len(df) - 1
    macd = float(m.macd().iloc[lv])
    sig = float(m.macd_signal().iloc[lv])
    return macd, sig, macd > sig

def main():
    data = get_live_data()
    if not data:
        print(f"[{datetime.now().strftime('%H:%M:%S')}] FAIL to fetch data")
        return

    k5m, k1h, k4h, ticker, funding, ob = data
    df5m = pd.DataFrame(k5m, columns=['t','o','h','l','c','v'])
    df1h = pd.DataFrame(k1h, columns=['t','o','h','l','c','v'])
    df4h = pd.DataFrame(k4h, columns=['t','o','h','l','c','v'])

    p5m, u5m, m5m, l5m, pb5m = calc_bb_pctb(df5m)
    p1h, u1h, m1h, l1h, pb1h = calc_bb_pctb(df1h)
    p4h, u4h, m4h, l4h, pb4h = calc_bb_pctb(df4h)

    rsi5m = calc_rsi(df5m)
    rsi1h = calc_rsi(df1h)
    rsi4h = calc_rsi(df4h)

    macd5m, sig5m, bull5m = calc_macd(df5m)
    macd4h, sig4h, bull4h = calc_macd(df4h)

    ma7_5m = float(ta.trend.SMAIndicator(df5m['c'], 7).sma_indicator().iloc[-1])
    ma7_4h = float(ta.trend.SMAIndicator(df4h['c'], 7).sma_indicator().iloc[-1])
    price = p5m

    bid = ob['bids'][0][0]
    ask = ob['asks'][0][0]
    spread = ask - bid
    bid_vol = sum([b[1] for b in ob['bids'][:3]])
    ask_vol = sum([a[1] for a in ob['asks'][:3]])

    change_24h = ticker.get('percentage', 0)
    high_24h = ticker.get('high', 0)
    low_24h = ticker.get('low', 0)
    vol_24h = ticker.get('quoteVolume', 0)
    fund_rate = funding['fundingRate'] * 100

    # 状态判断
    def bb_s(pctb):
        if pctb > 1.0: return "S3", "S1"
        elif pctb < 0: return "S4", "S2"
        elif pctb > 0.85: return "W1", "S1"
        elif pctb < 0.2: return "S2", "W2"
        else: return "N", "N"

    def rsi_s(rsi):
        if rsi > 75: return "R4"
        elif rsi > 65: return "R3"
        elif rsi < 25: return "R2"
        elif rsi < 40: return "R1"
        else: return "N"

    def dir_icon(bull_macd, above_ma):
        if bull_macd and above_ma: return "UP"
        elif not bull_macd and not above_ma: return "DN"
        else: return "--"

    bb5m_s, _ = bb_s(pb5m)
    bb1h_s, _ = bb_s(pb1h)
    bb4h_s, _ = bb_s(pb4h)

    # 信号判断
    long_sig = (pb5m < 0.2 and bull4h) or (pb5m < 0.1)
    short_sig = (pb4h and not bull4h and pb5m > 0.85) or (pb5m > 1.0)
    sig_text = "LONG" if long_sig else ("SHORT" if short_sig else "WATCH")

    now = datetime.now().strftime('%H:%M:%S')
    print(f"""
╔═══════════════════════════════════════════════════════╗
║  BTC/USDT SWAP  LIVE  ({now})               ║
╠═══════════════════════════════════════════════════════╣
║  PRICE: {price:>11,.2f}   24h: {change_24h:+.2f}%   (H {high_24h:,.0f}/L {low_24h:,.0f}) ║
║  VOL:  {vol_24h:>14,.0f} USDT                      ║
╠═══════════════════════════════════════════════════════╣
║  BB(5m)  ${l5m:>9,.0f} ~ ${u5m:>9,.0f}  %b={pb5m:.3f} [{bb5m_s}]     ║
║  BB(1h)  ${l1h:>9,.0f} ~ ${u1h:>9,.0f}  %b={pb1h:.3f} [{bb1h_s}]     ║
║  BB(4h)  ${l4h:>9,.0f} ~ ${u4h:>9,.0f}  %b={pb4h:.3f} [{bb4h_s}]     ║
╠═══════════════════════════════════════════════════════╣
║  TF    DIR    RSI     MACD      %b    MA7      ║
║  5m   {dir_icon(bull5m, price>ma7_5m):<4}   {rsi5m:>5.1f}{rsi_s(rsi5m):<3}  {macd5m:>+7.1f}  {pb5m:.3f}  ${ma7_5m:>9,.0f} ║
║  1h   {dir_icon(macd5m>sig5m, price>p1h):<4}   {rsi1h:>5.1f}{rsi_s(rsi1h):<3}  {macd5m:>+7.1f}  {pb1h:.3f}  ${p1h:>9,.0f} ║
║  4h   {dir_icon(bull4h, price>ma7_4h):<4}   {rsi4h:>5.1f}{rsi_s(rsi4h):<3}  {macd4h:>+7.1f}  {pb4h:.3f}  ${ma7_4h:>9,.0f} ║
╠═══════════════════════════════════════════════════════╣
║  BOOK  bid {bid:>10,.2f}  ask {ask:>10,.2f}  spread {spread:.2f}   ║
║        buy {bid_vol:.4f} BTC  sell {ask_vol:.4f} BTC            ║
║  FUND {fund_rate:+.4f}%    SIGNAL [{sig_text:<5}]                 ║
╚═══════════════════════════════════════════════════════╝
""")

if __name__ == "__main__":
    print("BTC 10s MONITOR... Ctrl+C to stop")
    try:
        while True:
            main()
            import time
            time.sleep(10)
    except KeyboardInterrupt:
        print("\nStopped")
