#!/usr/bin/env python3
"""
XXYY 自动交易任务
- 每3秒扫描数据库2号
- 流动性 > 6000 USD → 买入 → 移入数据库3号
- 流动性 <= 6000 USD → 移入数据库4号
- 买入后发送通知
"""

import json
import os
import time
import requests
from datetime import datetime

# 配置
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
XXYY_API_KEY = "xxyy_ak_6aa15eea2a2444bfbe91ab"
XXYY_API_BASE = "https://www.xxyy.io"
HEADERS = {"Authorization": f"Bearer {XXYY_API_KEY}"}

CONFIG_FILE = os.path.join(BASE_DIR, "config.json")
REPORT_FILE = os.path.join(BASE_DIR, "交易任务汇报.md")
DB_DIR = os.path.join(BASE_DIR, "databases")

LIQUIDITY_THRESHOLD = 6000  # USD

# BSC 配置
BSC_WALLET = "0xf47d64c93ef6d42b64ad9be78d7c6bc02bd387bd"
BSC_BUY_AMOUNT = 0.003  # BNB
BSC_TIP = 0.1  # Gwei

# SOL 配置
SOL_WALLET = "7Z84WHmP3misUmPE7WdfUSizgWaqEgtErCWwWNYygXvb"
SOL_BUY_AMOUNT = 0.02  # SOL
SOL_TIP = 0.01  # SOL

def load_config():
    with open(CONFIG_FILE, 'r') as f:
        return json.load(f)

def load_db(db_name):
    db_file = os.path.join(DB_DIR, f"{db_name}.json")
    if os.path.exists(db_file):
        with open(db_file, 'r') as f:
            return json.load(f)
    return {"name": db_name, "tokens": []}

def save_db(db_name, data):
    db_file = os.path.join(DB_DIR, f"{db_name}.json")
    with open(db_file, 'w') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def query_token(ca, chain="bsc"):
    """查询代币详情"""
    url = f"{XXYY_API_BASE}/api/trade/open/api/query"
    params = {"ca": ca, "chain": chain}
    try:
        resp = requests.get(url, headers=HEADERS, params=params, timeout=10)
        return resp.json()
    except Exception as e:
        print(f"查询代币失败: {e}")
        return None

def buy_token(ca, chain="bsc", amount=0.003, tip=0.1):
    """买入代币"""
    # 根据链选择钱包
    if chain == "bsc":
        wallet = BSC_WALLET
    elif chain == "sol":
        wallet = SOL_WALLET
    else:
        wallet = BSC_WALLET
    
    url = f"{XXYY_API_BASE}/api/trade/open/api/swap"
    payload = {
        "chain": chain,
        "walletAddress": wallet,
        "tokenAddress": ca,
        "isBuy": True,
        "amount": amount,
        "tip": tip,
        "slippage": 20
    }
    try:
        resp = requests.post(url, headers=HEADERS, json=payload, timeout=30)
        return resp.json()
    except Exception as e:
        print(f"买入失败: {e}")
        return None

def send_wechat(message):
    """发送微信推送"""
    import subprocess
    cmd = [
        "openclaw", "message", "send",
        "--channel", "openclaw-weixin",
        "--account", "d67d274ba92d-im-bot",
        "--target", "o9cq80_h_BaEgBVnsrfqjOMF8Rug@im.wechat",
        "--message", message
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        if result.returncode == 0:
            print(f"  📤 微信推送成功")
        else:
            print(f"  ⚠️ 微信推送失败: {result.stderr}")
    except Exception as e:
        print(f"  ⚠️ 微信推送异常: {e}")

def append_report(message):
    """写入汇报文件"""
    with open(REPORT_FILE, 'a', encoding='utf-8') as f:
        f.write(message + "\n")

def format_notification(token_data, buy_result, chain="bsc"):
    """格式化买入通知"""
    symbol = token_data.get("data", {}).get("baseSymbol", "UNKNOWN")
    price = token_data.get("data", {}).get("tradeInfo", {}).get("price", 0)
    mc = token_data.get("data", {}).get("tradeInfo", {}).get("marketCapUsd", 0)
    ca = token_data.get("data", {}).get("tokenAddress", "")
    
    # 计算预估持仓
    if chain == "bsc":
        amount = BSC_BUY_AMOUNT
        token_name = "BNB"
    elif chain == "sol":
        amount = SOL_BUY_AMOUNT
        token_name = "SOL"
    else:
        amount = BSC_BUY_AMOUNT
        token_name = "BNB"
    
    holdings = amount / price if price > 0 else 0
    
    notification = f"""
🔔 买入成功

🪙 代币: {symbol}
📊 现价: ${price:.8f}
💰 买入金额: {amount} {token_name}
📦 预估持仓: {holdings:.0f} {symbol}
💎 CA: {ca}
⏰ 时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
━━━━━━━━━━━━━━━━━━
"""
    return notification

def process_token(token, db2, db3, db4):
    """处理单个代币"""
    ca = token.get("tokenAddress")
    chain = token.get("chain", "bsc")
    
    print(f"正在扫描: {ca}")
    
    # 查询代币详情
    token_data = query_token(ca, chain)
    if not token_data or token_data.get("code") != 200:
        print(f"代币 {ca} 查询失败，跳过")
        return
    
    # 获取流动性
    liquidity = token_data.get("data", {}).get("pairInfo", {}).get("liquidateUsd", 0)
    symbol = token_data.get("data", {}).get("baseSymbol", "UNKNOWN")
    
    print(f"  {symbol}: 流动性 ${liquidity:.2f}")
    
    if liquidity > LIQUIDITY_THRESHOLD:
        # 流动性满足 → 买入
        print(f"  ✅ 流动性满足，买入...")
        
        # 根据链设置买入金额和手续费
        if chain == "bsc":
            amount = BSC_BUY_AMOUNT
            tip = BSC_TIP
        elif chain == "sol":
            amount = SOL_BUY_AMOUNT
            tip = SOL_TIP
        else:
            amount = BSC_BUY_AMOUNT
            tip = BSC_TIP
        
        buy_result = buy_token(ca, chain, amount, tip)
        
        if buy_result and buy_result.get("code") == 200:
            # 从db2移除
            db2["tokens"] = [t for t in db2["tokens"] if t.get("tokenAddress") != ca]
            
            # 移入db3
            token["buy_time"] = datetime.now().isoformat()
            token["buy_result"] = buy_result
            db3["tokens"].append(token)
            
            # 发送通知
            msg = format_notification(token_data, buy_result, chain)
            append_report(msg)
            send_wechat(msg)  # 微信推送
            print(msg)
        else:
            print(f"  ❌ 买入失败: {buy_result}")
    else:
        # 流动性不足 → 移入db4
        print(f"  ❌ 流动性不足，移入数据库4号")
        db2["tokens"] = [t for t in db2["tokens"] if t.get("tokenAddress") != ca]
        token["reject_reason"] = f"流动性 ${liquidity:.2f} < ${LIQUIDITY_THRESHOLD}"
        db4["tokens"].append(token)

def init_report_file():
    """初始化汇报文件"""
    header = f"""# XXYY 自动交易任务汇报

## 任务配置
- 扫描间隔: 每3秒
- 流动性阈值: > ${LIQUIDITY_THRESHOLD}
- BSC 买入金额: {BSC_BUY_AMOUNT} BNB
- 钱包: {BSC_WALLET}

## 交易记录
---
"""
    with open(REPORT_FILE, 'w', encoding='utf-8') as f:
        f.write(header)

def run_task():
    """主任务循环"""
    print("🚀 XXYY 自动交易任务启动")
    print(f"📊 流动性阈值: ${LIQUIDITY_THRESHOLD}")
    print(f"⏰ 扫描间隔: 3秒")
    print("-" * 40)
    
    init_report_file()
    
    while True:
        try:
            db2 = load_db("db2")
            db3 = load_db("db3")
            db4 = load_db("db4")
            
            if not db2["tokens"]:
                print(f"[{datetime.now().strftime('%H:%M:%S')}] 数据库2号为空，等待...")
            else:
                print(f"[{datetime.now().strftime('%H:%M:%S')}] 待处理代币: {len(db2['tokens'])} 个")
                
                # 逐个处理（避免并发问题）
                tokens_to_process = db2["tokens"].copy()
                for token in tokens_to_process:
                    process_token(token, db2, db3, db4)
                    time.sleep(1)  # 每个代币处理间隔1秒
                
                # 保存数据库
                save_db("db2", db2)
                save_db("db3", db3)
                save_db("db4", db4)
            
            time.sleep(3)
            
        except KeyboardInterrupt:
            print("\n⚠️ 任务已停止")
            break
        except Exception as e:
            print(f"错误: {e}")
            time.sleep(5)

if __name__ == "__main__":
    run_task()
