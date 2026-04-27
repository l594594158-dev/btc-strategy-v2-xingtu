#!/usr/bin/env python3
"""
BTC/USDT 永续合约 量化策略
基于多周期共振 + 布林带超买超卖 + MACD + RSI + ATR止损

策略逻辑：
  方向确认: 4h + 1d 均线 + MACD
  入场信号: 1h 方向 + 5m 超卖/超买极端位
  验证:     1m 突破确认 或 成交量配合
  止损:     2×ATR(1h)
  止盈:     分批在布林带支撑/压力位
"""

import json
import os
import time
import ccxt
import pandas as pd
import ta
from datetime import datetime

# ========== 配置 ==========
BINANCE_API_KEY = "XMZDMoFhaduPEhfXup7JF5afnIHjCNmAzSwCNJB0zwek415IsbfkU3TJh70ulA2G"
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(BASE_DIR, "config.json")
DB_FILE = os.path.join(BASE_DIR, "databases", "signals.json")
REPORT_FILE = os.path.join(BASE_DIR, "signals_report.md")
os.makedirs(os.path.join(BASE_DIR, "databases"), exist_ok=True)

# ========== 交易所初始化 ==========
binance = ccxt.binance({'options': {'defaultType': 'swap'}})

# ========== 工具函数 ==========
def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")

def save_json(path, data):
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def load_json(path):
    if os.path.exists(path):
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {"signals": [], "positions": [], "stats": {"total": 0, "profit": 0, "loss": 0}}

# ========== 技术指标计算 ==========
def calc_indicators(klines):
    """计算完整技术指标"""
    df = pd.DataFrame(klines, columns=['t','o','h','l','c','v'])
    close = df['c']
    high = df['h']
    low = df['l']
    lv = len(df) - 1

    ma7 = ta.trend.SMAIndicator(close, 7).sma_indicator().iloc[lv]
    ma25 = ta.trend.SMAIndicator(close, 25).sma_indicator().iloc[lv]
    ma99 = ta.trend.SMAIndicator(close, 99).sma_indicator().iloc[lv]

    macd_ind = ta.trend.MACD(close)
    macd = macd_ind.macd().iloc[lv]
    macd_sig = macd_ind.macd_signal().iloc[lv]
    macd_hist = macd - macd_sig

    rsi = float(ta.momentum.RSIIndicator(close).rsi().iloc[lv])

    bb = ta.volatility.BollingerBands(close)
    bb_u = bb.bollinger_hband().iloc[lv]
    bb_m = bb.bollinger_mavg().iloc[lv]
    bb_l = bb.bollinger_lband().iloc[lv]

    atr = ta.volatility.AverageTrueRange(high, low, close).average_true_range().iloc[lv]

    price = close.iloc[lv]
    pct_b = (price - bb_l) / (bb_u - bb_l) if (bb_u - bb_l) != 0 else 0.5

    return {
        'price': price,
        'ma7': ma7, 'ma25': ma25, 'ma99': ma99,
        'macd': macd, 'macd_sig': macd_sig, 'macd_hist': macd_hist,
        'rsi': rsi,
        'bb_u': bb_u, 'bb_m': bb_m, 'bb_l': bb_l,
        'atr': atr, 'pct_b': pct_b,
        'above_ma7': price > ma7,
        'above_ma25': price > ma25,
        'macd_bull': macd > macd_sig,
        'bullish': price > ma7 and macd > macd_sig,  # 多头排列
        'bearish': price < ma7 and macd < macd_sig,   # 空头排列
        'df': df
    }

def get_volume_ratio(df, period=20):
    """成交量倍数"""
    vols = df['v'].tail(period)
    avg = vols.mean()
    current = df['v'].iloc[-1]
    return current / avg if avg > 0 else 1

# ========== 获取多周期数据 ==========
def fetch_all_timeframes():
    """获取所有时间周期K线"""
    tf_map = {
        '1m': ('1m', 100),
        '5m': ('5m', 100),
        '15m': ('15m', 100),
        '1h': ('1h', 200),
        '4h': ('4h', 200),
        '1d': ('1d', 200),
    }
    data = {}
    for name, (tf, limit) in tf_map.items():
        try:
            klines = binance.fetch_ohlcv('BTC/USDT:USDT', timeframe=tf, limit=limit)
            data[tf] = calc_indicators(klines)
        except Exception as e:
            log(f"⚠️ 获取{tf}数据失败: {e}")
    return data

# ========== 信号评估 ==========
def eval_signal(data):
    """
    评估做多/做空信号强度
    返回: (做多信号, 做空信号, 信号详情)
    """
    r1m = data.get('1m', {})
    r5m = data.get('5m', {})
    r15m = data.get('15m', {})
    r1h = data.get('1h', {})
    r4h = data.get('4h', {})
    rd  = data.get('1d', {})

    long_score = 0
    short_score = 0
    details = []

    # ---- 大周期方向 (权重最高) ----
    if r4h.get('bullish') and rd.get('bullish'):
        long_score += 3
        details.append("✅ 4h+1d多头共振")
    elif r4h.get('bearish') and rd.get('bearish'):
        short_score += 3
        details.append("✅ 4h+1d空头共振")

    if r4h.get('bullish'):
        long_score += 1
        details.append("✅ 4h均线多头")
    elif r4h.get('bearish'):
        short_score += 1
        details.append("✅ 4h均线空头")

    if rd.get('bullish'):
        long_score += 1
        details.append("✅ 1d均线多头")
    elif rd.get('bearish'):
        short_score += 1
        details.append("✅ 1d均线空头")

    # ---- 中周期确认 ----
    if r1h.get('macd_bull') and r1h.get('above_ma7'):
        long_score += 1
        details.append("✅ 1h MACD金叉+均线多头")
    if r1h.get('macd_bull') == False and r1h.get('above_ma7') == False:
        short_score += 1
        details.append("✅ 1h MACD死叉+均线空头")

    # ---- 超卖/超买信号 ----
    # 做多: 5m/15m 超卖 (%b < 0.15，更严格)
    if r5m.get('pct_b', 0.5) < 0.15:
        long_score += 2
        details.append(f"✅ 5m超卖(%b={r5m['pct_b']:.3f})")
    elif r5m.get('pct_b', 0.5) > 0.90:
        short_score += 1
        details.append(f"⚠️ 5m偏高(%b={r5m['pct_b']:.3f})")

    if r15m.get('pct_b', 0.5) < 0.15:
        long_score += 1
        details.append(f"✅ 15m超卖(%b={r15m['pct_b']:.3f})")
    elif r15m.get('pct_b', 0.5) > 0.90:
        short_score += 1
        details.append(f"⚠️ 15m偏高(%b={r15m['pct_b']:.3f})")

    # 做空: 5m/15m 超买 (%b > 0.90，更严格)
    if r5m.get('pct_b', 0.5) > 0.90:
        short_score += 2
        details.append(f"✅ 5m超买(%b={r5m['pct_b']:.3f})")
    if r15m.get('pct_b', 0.5) > 0.90:
        short_score += 1
        details.append(f"✅ 15m超买(%b={r15m['pct_b']:.3f})")

    # ---- RSI ----
    rsi_1h = r1h.get('rsi', 50)
    rsi_5m = r5m.get('rsi', 50)

    # 做多: RSI在40~60正常区，回调整理完毕
    if 35 < rsi_1h < 60:
        long_score += 1
        details.append(f"✅ 1h RSI正常({rsi_1h:.1f})")
    # 做空: RSI > 65 超买区域
    if rsi_1h > 65:
        short_score += 1
        details.append(f"⚠️ 1h RSI偏高({rsi_1h:.1f})")
    if rsi_5m > 70:
        short_score += 1
        details.append(f"⚠️ 5m RSI超买({rsi_5m:.1f})")

    # ---- 1m 快速突破确认 ----
    # 做多: 1m从超卖区域反弹
    if r1m.get('pct_b', 0.5) < 0.15 and r1m.get('above_ma7') == False:
        long_score += 1
        details.append(f"✅ 1m严重超卖")
    # 做空: 1m突破布林带上轨（脉冲式冲高）
    if r1m.get('pct_b', 0.5) > 1.0:
        short_score += 2
        details.append(f"🚨 1m突破上轨(超买)")

    return {
        'long_score': long_score,
        'short_score': short_score,
        'details': details,
        'data': data
    }

# ========== 入场/出场计算 ==========
def calc_entry_exit(eval_result):
    """计算入场点位、止损、止盈"""
    data = eval_result['data']
    r1h = data.get('1h', {})
    r5m = data.get('5m', {})
    r4h = data.get('4h', {})

    price = r5m.get('price', r1h.get('price', 0))
    atr = r1h.get('atr', 500)
    bb_u_1h = r1h.get('bb_u', 0)
    bb_l_1h = r1h.get('bb_l', 0)
    bb_u_5m = r5m.get('bb_u', 0)
    bb_l_5m = r5m.get('bb_l', 0)

    long_entry = {
        'price': None,
        'stop_loss': price - 2 * atr,
        'tp1': bb_m_1h if (bb_m_1h := r1h.get('bb_m', 0)) else price + atr,
        'tp2': bb_l_1h,
        'tp3': bb_l_5m,
        'reason': '5m超卖反弹'
    }

    short_entry = {
        'price': None,
        'stop_loss': price + 2 * atr,
        'tp1': bb_m_1h if (bb_m_1h := r1h.get('bb_m', 0)) else price - atr,
        'tp2': bb_u_1h,
        'tp3': bb_u_5m,
        'reason': '5m超买或1m突破上轨'
    }

    # 动态入场价位
    if r5m.get('pct_b', 0.5) < 0.15:
        long_entry['price'] = price
    if r5m.get('pct_b', 0.5) > 0.90:
        short_entry['price'] = price
    if r5m.get('pct_b', 0.5) > 1.0:
        short_entry['price'] = r5m.get('bb_u', price)

    return long_entry, short_entry

# ========== 生成信号报告 ==========
def generate_signal_report(eval_result, long_entry, short_entry):
    """生成格式化的信号报告"""
    data = eval_result['data']
    r1h = data.get('1h', {})
    r5m = data.get('5m', {})

    price = r5m.get('price', r1h.get('price', 0))
    funding = binance.fetch_funding_rate('BTC/USDT:USDT')
    ob = binance.fetch_order_book('BTC/USDT:USDT', 5)

    bid_vol = sum([b[1] for b in ob['bids'][:5]])
    ask_vol = sum([a[1] for a in ob['asks'][:5]])
    ob_ratio = bid_vol / (bid_vol + ask_vol) * 100 if (bid_vol + ask_vol) > 0 else 50

    lines = []
    lines.append("=" * 58)
    lines.append(f"📊 BTC/USDT 永续合约信号报告")
    lines.append(f"更新时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append("=" * 58)
    lines.append(f"\n💰 当前价格: ${price:,.2f}")
    lines.append(f"📍 布林带(5m): ${r5m.get('bb_l',0):,.2f} ~ ${r5m.get('bb_u',0):,.2f}")
    lines.append(f"📍 布林带(1h): ${r1h.get('bb_l',0):,.2f} ~ ${r1h.get('bb_u',0):,.2f}")
    lines.append(f"📊 资金费率: {funding['fundingRate']*100:+.4f}%")
    lines.append(f"📊 订单簿: {ob_ratio:.0f}%买 / {100-ob_ratio:.0f}%卖")

    # 各周期信号
    lines.append(f"\n{'周期':<6} {'方向':^8} {'RSI':^7} {'%b':^7} {'MA7':>10} {'MACD':>10}")
    lines.append("-" * 58)
    for tf, key in [('1m','1m'),('5m','5m'),('15m','15m'),('1h','1h'),('4h','4h'),('1d','1d')]:
        r = data.get(key, {})
        dir_icon = "📈" if r.get('bullish') else "📉"
        rsi = r.get('rsi', 0)
        pctb = r.get('pct_b', 0.5)
        ma7 = r.get('ma7', 0)
        macd = r.get('macd', 0)
        lines.append(f"{tf:<6} {dir_icon:^8} {rsi:>5.1f}  {pctb:>6.3f}  ${ma7:>9,.0f}  {macd:>+9.1f}")

    # 信号详情
    lines.append(f"\n🔍 信号评分:")
    for d in eval_result['details']:
        lines.append(f"  {d}")

    lines.append(f"\n🎯 信号强度:")
    lines.append(f"  做多评分: {eval_result['long_score']} 分")
    lines.append(f"  做空评分: {eval_result['short_score']} 分")

    # 入场建议
    le = long_entry
    se = short_entry

    if le['price']:
        lines.append(f"\n🟢 做多信号 (评分{eval_result['long_score']}):")
        lines.append(f"  入场价: ${le['price']:,.2f}")
        lines.append(f"  止损: ${le['stop_loss']:,.2f} (距-{abs(le['price']-le['stop_loss'])/le['price']*100:.1f}%)")
        lines.append(f"  止盈1: ${le['tp1']:,.2f}")
        lines.append(f"  止盈2: ${le['tp2']:,.2f}")
        lines.append(f"  止盈3: ${le['tp3']:,.2f}")
        lines.append(f"  理由: {le['reason']}")

    if se['price']:
        lines.append(f"\n🔴 做空信号 (评分{eval_result['short_score']}):")
        lines.append(f"  入场价: ${se['price']:,.2f}")
        lines.append(f"  止损: ${se['stop_loss']:,.2f} (距+{abs(se['price']-se['stop_loss'])/se['price']*100:.1f}%)")
        lines.append(f"  止盈1: ${se['tp1']:,.2f}")
        lines.append(f"  止盈2: ${se['tp2']:,.2f}")
        lines.append(f"  止盈3: ${se['tp3']:,.2f}")
        lines.append(f"  理由: {se['reason']}")

    if not le['price'] and not se['price']:
        lines.append(f"\n⚪ 当前无明确入场信号，观望为主")

    lines.append(f"\n" + "=" * 58)
    lines.append(f"⚠️ 风险提示: 指标仅供参考，非投资建议")

    return "\n".join(lines)

# ========== 主任务 ==========
def run_strategy_cycle():
    """执行一轮策略分析"""
    try:
        log("🔄 获取多周期数据...")
        data = fetch_all_timeframes()
        if not data:
            log("❌ 数据获取失败")
            return None

        eval_result = eval_signal(data)
        long_entry, short_entry = calc_entry_exit(eval_result)

        # 生成报告
        report = generate_signal_report(eval_result, long_entry, short_entry)
        print(report)

        # 保存到文件
        save_json(DB_FILE, {
            "updated": datetime.now().isoformat(),
            "eval_result": {
                "long_score": eval_result['long_score'],
                "short_score": eval_result['short_score'],
                "details": eval_result['details']
            },
            "long_entry": {k: float(v) if isinstance(v, (int, float)) and v != 0 else v
                           for k, v in long_entry.items()},
            "short_entry": {k: float(v) if isinstance(v, (int, float)) and v != 0 else v
                           for k, v in short_entry.items()},
            "price": float(data.get('5m', {}).get('price', 0)),
            "rsi_5m": float(data.get('5m', {}).get('rsi', 0)),
            "pctb_5m": float(data.get('5m', {}).get('pct_b', 0)),
            "funding_rate": float(binance.fetch_funding_rate('BTC/USDT:USDT')['fundingRate'])
        })

        # 写报告文件
        with open(REPORT_FILE, 'w', encoding='utf-8') as f:
            f.write(report)

        log(f"📊 做多:{eval_result['long_score']}分 | 做空:{eval_result['short_score']}分 | 价格:${data.get('5m',{}).get('price',0):,.0f}")

        return eval_result

    except Exception as e:
        log(f"❌ 策略执行出错: {e}")
        import traceback
        traceback.print_exc()
        return None

# ========== 启动入口 ==========
if __name__ == "__main__":
    log("🚀 BTC量化策略任务启动")
    log(f"📍 监控标的: BTC/USDT 永续合约")
    log(f"📍 数据来源: 币安")

    # 立即执行一次
    run_strategy_cycle()

    log("✅ 策略初始化完成，报告已保存")
