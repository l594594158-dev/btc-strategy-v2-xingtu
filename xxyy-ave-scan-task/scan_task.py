#!/usr/bin/env python3
"""
XXYY + AVE 联合扫描任务
- Phase1: XXYY 每5秒扫NEW/ALMOST代币 → 基础指标过滤 → 数据库1号
- Phase2: AVE 每5秒扫描数据库1号 → KOL指标验证 → 数据库2号(达标)/数据库4号(不达标)
"""

import json
import os
import time
import requests
from datetime import datetime, timedelta
from collections import defaultdict

# ============ 配置 ============
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_DIR = os.path.join(BASE_DIR, "databases")
CONFIG_FILE = os.path.join(BASE_DIR, "config.json")
REPORT_FILE = os.path.join(BASE_DIR, "扫描任务汇报.md")

XXYY_API_KEY = "xxyy_ak_6aa15eea2a2444bfbe91ab"
XXYY_BASE = "https://www.xxyy.io"

AVE_API_KEY = "tl8WN1ejRUAXUk1YO6ARlBzDGnAXlCJTo7BLXhldFE8wh0cbi01j7aNrl15Yfyke"
AVE_BASE = "https://data.ave-api.xyz"

HEADERS_XXYY = {"Authorization": f"Bearer {XXYY_API_KEY}"}
HEADERS_AVE = {"X-API-KEY": AVE_API_KEY}

SCAN_INTERVAL = 5
COOLDOWN_SECONDS = 30
MAX_VERIFY_ROUNDS = 3
TOKEN_DELAY = 1

# 链名映射：XXYY链名 -> AVE API链名
CHAIN_MAP_XXYY_TO_AVE = {
    "sol": "solana",   # XXYY用"sol"，AVE用"solana"
    "bsc": "bsc",      # 相同
    "eth": "eth",      # 相同
    "tron": "tron",    # 相同
}

def to_ave_chain(chain):
    """将XXYY链名转换为AVE链名"""
    return CHAIN_MAP_XXYY_TO_AVE.get(chain, chain)

# ============ 工具函数 ============

def load_config():
    with open(CONFIG_FILE, 'r') as f:
        return json.load(f)

def load_db(name):
    path = os.path.join(DB_DIR, f"{name}.json")
    if os.path.exists(path):
        with open(path, 'r') as f:
            return json.load(f)
    return {"name": name, "tokens": []}

def save_db(name, data):
    path = os.path.join(DB_DIR, f"{name}.json")
    with open(path, 'w') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def get_all_addresses_in_db():
    """获取所有数据库中的代币地址，用于去重"""
    all_addrs = set()
    for db_name in ["db1", "db2", "db3", "db4"]:
        db = load_db(db_name)
        for token in db.get("tokens", []):
            all_addrs.add(token.get("tokenAddress", ""))
    return all_addrs

def is_token_in_any_db(token_address):
    """检查代币是否已在任何数据库中"""
    for db_name in ["db1", "db2", "db3", "db4"]:
        db = load_db(db_name)
        for t in db.get("tokens", []):
            if t.get("tokenAddress") == token_address:
                return True
    return False

def now_str():
    return datetime.now().strftime('%Y-%m-%d %H:%M:%S')

def log(msg):
    print(f"[{now_str()}] {msg}")

def append_report(msg):
    with open(REPORT_FILE, 'a', encoding='utf-8') as f:
        f.write(f"[{now_str()}] {msg}\n")

# ============ XXYY API ============

def fetch_xxxy_feed(chain):
    """获取XXYY trending代币（数据完整，有holders）"""
    url = f"{XXYY_BASE}/api/trade/open/api/trending-list"
    try:
        payload = {"chain": chain, "current_page": 0, "page_size": 50}
        resp = requests.post(url, headers=HEADERS_XXYY, json=payload, timeout=15)
        data = resp.json()
        if data.get("code") == 200:
            items = data.get("data", []) if isinstance(data.get("data"), list) else data.get("data", {}).get("list", [])
            return items
    except Exception as e:
        log(f"  ⚠️ XXYY trending {chain} 获取失败: {e}")
    return []

def query_xxxy_token(token_address, chain):
    """查询XXYY代币详情"""
    url = f"{XXYY_BASE}/api/trade/open/api/query"
    params = {"ca": token_address, "chain": chain}
    try:
        resp = requests.get(url, headers=HEADERS_XXYY, params=params, timeout=10)
        return resp.json()
    except:
        return None

# ============ AVE API ============

def query_ave_token(token_address, chain):
    """查询AVE代币详情"""
    token_id = f"{token_address}-{to_ave_chain(chain)}"
    url = f"{AVE_BASE}/v2/tokens/{token_id}"
    try:
        resp = requests.get(url, headers=HEADERS_AVE, timeout=10)
        return resp.json()
    except:
        return None

def get_ave_top_holders(token_address, chain, limit=20):
    """获取AVE代币Top holders"""
    token_id = f"{token_address}-{to_ave_chain(chain)}"
    url = f"{AVE_BASE}/v2/tokens/top100/{token_id}"
    params = {"limit": limit}
    try:
        resp = requests.get(url, headers=HEADERS_AVE, params=params, timeout=10)
        data = resp.json()
        if data.get("status") == 1:
            return data.get("data", [])
    except:
        pass
    return []

def get_wallet_tx_history(wallet_address, token_address, chain, from_time=None):
    """获取钱包对某代币的交易历史"""
    url = f"{AVE_BASE}/v2/address/tx"
    params = {
        "wallet_address": wallet_address,
        "chain": to_ave_chain(chain),
        "token_address": token_address,
        "page_size": 50
    }
    if from_time:
        params["from_time"] = from_time
    try:
        resp = requests.get(url, headers=HEADERS_AVE, params=params, timeout=10)
        data = resp.json()
        if data.get("status") == 1:
            return data.get("data", {}).get("result", [])
    except:
        pass
    return []

def get_wallet_pnl(wallet_address, token_address, chain):
    """获取钱包在某代币上的PNL"""
    url = f"{AVE_BASE}/v2/address/pnl"
    params = {
        "wallet_address": wallet_address,
        "chain": to_ave_chain(chain),
        "token_address": token_address
    }
    try:
        resp = requests.get(url, headers=HEADERS_AVE, params=params, timeout=10)
        return resp.json()
    except:
        return None

def get_smart_wallets(chain, sort="total_profit_rate", limit=50):
    """获取链上聪明钱包列表"""
    url = f"{AVE_BASE}/v2/address/smart_wallet/list"
    params = {"chain": to_ave_chain(chain), "sort": sort, "sort_dir": "desc", "limit": limit}
    try:
        resp = requests.get(url, headers=HEADERS_AVE, params=params, timeout=10)
        data = resp.json()
        if data.get("status") == 1:
            return data.get("data", [])
    except:
        pass
    return []

# ============ XXYY 初筛过滤 ============

def check_xxxy_filters(token_address, chain, config, token_data=None):
    """用XXYY API检查代币是否满足基础指标"""
    filters = config["settings"]["xxxy"]["filters"]
    
    # trending数据直接传入，否则查询
    if token_data is None:
        result = query_xxxy_token(token_address, chain)
        if not result or result.get("code") != 200:
            return None
        data = result.get("data", {})
        if not data:
            return None
    else:
        data = token_data
    
    # trending格式提取指标
    liquidity = float(data.get("liquid", 0) or 0)
    marketcap = float(data.get("marketCapUSD", 0) or data.get("marketCap", 0) or 0)
    holders = int(data.get("holders", 0) or 0)
    volume = float(data.get("volume", 0) or 0)
    
    # top10 holder占比（从security.topHolder）
    top_holder_pct = float(data.get("security", {}).get("topHolder", {}).get("value", 0) or 0)
    
    # 打印指标
    log(f"  📊 {token_address[:12]}... | 流动性: ${liquidity:.0f} | 市值: ${marketcap:.0f} | Top10: {top_holder_pct:.1f}% | 持币: {holders} | 成交量: ${volume:.0f}")
    
    # 检查各项过滤条件
    reason = []
    if liquidity < filters["liquidity_min"]:
        reason.append(f"流动性${liquidity:.0f}<{filters['liquidity_min']}")
    # 市值在 $10k - $800k 之间
    marketcap_min = filters.get("marketcap_min", 10000)
    marketcap_max = filters.get("marketcap_max", 800000)
    if not (marketcap_min <= marketcap <= marketcap_max):
        reason.append(f"市值${marketcap:.0f}不在${marketcap_min}-${marketcap_max}范围")
    if top_holder_pct >= filters["top10_holder_max"]:
        reason.append(f"Top10占比{top_holder_pct:.1f}%>={filters['top10_holder_max']}%")
    if holders < filters["holder_min"]:
        reason.append(f"持币人数{holders}<{filters['holder_min']}")
    if volume < filters["volume_min"]:
        reason.append(f"成交量${volume:.0f}<{filters['volume_min']}")
    
    if reason:
        log(f"  ❌ {token_address[:12]}... XXYY不达标: {'; '.join(reason)}")
        return None
    
    log(f"  ✅ {token_address[:12]}... XXYY达标!")
    return {
        "tokenAddress": token_address,
        "chain": chain,
        "liquidity": liquidity,
        "marketcap": marketcap,
        "symbol": data.get("symbol", ""),
        "top10_pct": top_holder_pct,
        "holders": holders,
        "volume": volume,
        "add_time": datetime.now().isoformat(),
        "verify_rounds": 0,
        "last_verify_time": None,
        "kol_checks": []
    }

# ============ AVE KOL验证 ============

def check_ave_kol_filters(token_address, chain, config):
    """
    用AVE API验证KOL指标
    返回: (是否达标, 详细结果)
    """
    filters = config["settings"]["ave"]["filters"]
    five_minutes_ago = int((datetime.now() - timedelta(minutes=5)).timestamp())

    def parse_tx_time(tx_time):
        """解析交易时间（可能是unix时间戳int或ISO字符串）"""
        if isinstance(tx_time, int):
            return tx_time
        if isinstance(tx_time, str):
            try:
                # ISO格式: '2026-04-02T11:53:51.000068Z'
                return int(datetime.fromisoformat(tx_time.replace('Z', '+00:00')).timestamp())
            except:
                return 0
        return 0
    
    # 1. 获取代币Top Holders
    holders = get_ave_top_holders(token_address, chain, limit=20)
    if not holders:
        return False, {"reason": "无holder数据"}
    
    # 2. 获取聪明钱包列表
    smart_wallets = get_smart_wallets(chain, limit=100)
    smart_addresses = {w["wallet_address"].lower() for w in smart_wallets}
    
    # 3. 对每个top holder检查交易历史 + Holder数据辅助判断
    kol_buys = []  # KOL买入记录
    total_buy_amount = 0
    total_sell_amount = 0
    recent_buy_count = 0
    has_smart_money = False  # 是否有聪明钱（大户+盈利）
    
    for holder in holders:
        wallet = holder.get("address", "")
        if not wallet:
            continue
        
        # 判断是否是KOL/聪明钱包
        is_kol = wallet.lower() in smart_addresses
        
        # 检查Holder级别的聪明钱指标（辅助判断）
        balance_ratio = float(holder.get("balance_ratio", 0) or 0)
        unrealized = float(holder.get("unrealized_profit", 0) or 0)
        realized = float(holder.get("realized_profit", 0) or 0)
        total_profit = unrealized + realized
        balance_usd = float(holder.get("balance_usd", 0) or 0)
        
        # 只要是大户(>1%仓位)且有盈利，就算smart money
        if balance_ratio > 0.01 and total_profit > 0:
            has_smart_money = True
            # 也记录unrealized用于后续盈利检查
            holder["unrealized_profit"] = unrealized
        
        # 获取该钱包对此代币的交易历史
        txs = get_wallet_tx_history(wallet, token_address, chain)
        
        buy_amt = 0
        sell_amt = 0
        last_buy_time = 0
        
        for tx in txs:
            tx_time = parse_tx_time(tx.get("time", 0))
            if tx_time < five_minutes_ago:
                continue
            
            # 判断是buy还是sell
            from_amt = float(tx.get("from_amount", 0) or 0)
            from_usd = float(tx.get("from_price_usd", 0) or 0)
            
            # 简化判断：如果from_price_usd存在且较大，认为是卖出
            if from_usd > 0:
                sell_amt += from_amt * from_usd
            else:
                buy_amt += abs(from_amt)
            
            if tx_time > last_buy_time:
                last_buy_time = tx_time
        
        if buy_amt > 0:
            total_buy_amount += buy_amt
            if is_kol:
                kol_buys.append({
                    "wallet": wallet,
                    "buy_amount": buy_amt,
                    "last_buy_time": last_buy_time,
                    "is_kol": True,
                    "unrealized_profit": unrealized
                })
                recent_buy_count += 1
        
        total_sell_amount += sell_amt
    
    # 4. 对于无交易记录但有聪明钱的代币，用Holder数据补充判断
    if total_buy_amount == 0 and has_smart_money:
        # 用Holder的balance_usd估算买入金额
        for holder in holders:
            balance_usd = float(holder.get("balance_usd", 0) or 0)
            unrealized = float(holder.get("unrealized_profit", 0) or 0)
            realized = float(holder.get("realized_profit", 0) or 0)
            total_profit = unrealized + realized
            is_kol = holder.get("address", "").lower() in smart_addresses
            
            if balance_ratio := float(holder.get("balance_ratio", 0) or 0) > 0.01 and total_profit > 0:
                # 大户且盈利，估算其持仓成本
                estimated_cost = max(0, balance_usd - total_profit)
                if estimated_cost > 0:
                    total_buy_amount += estimated_cost
                    if is_kol:
                        kol_buys.append({
                            "wallet": holder.get("address", ""),
                            "buy_amount": estimated_cost,
                            "last_buy_time": 0,  # 不知道购买时间
                            "is_kol": True,
                            "estimated": True,
                            "unrealized_profit": unrealized
                        })
    
    # 4. 检查各项KOL条件
    log(f"  🔍 {token_address[:12]}... | KOL买入数: {len(kol_buys)} | 总买入: ${total_buy_amount:.2f} | 5min内买入: {recent_buy_count} | SmartMoney: {has_smart_money}")
    
    # 5. 检查5分钟买<卖（无交易时跳过，有交易时要求买>卖）
    has_real_tx = total_buy_amount > 0 or total_sell_amount > 0
    if filters["buy_lt_sell_ratio_5m"] and has_real_tx and total_buy_amount >= total_sell_amount:
        log(f"  ❌ 5min买${total_buy_amount:.2f} >= 卖${total_sell_amount:.2f}")
        return False, {"reason": f"5min买<卖不满足"}
    
    # 6. 检查KOL数量
    if len(kol_buys) < filters["kol_buy_count_min"]:
        log(f"  ❌ KOL数量{len(kol_buys)} < {filters['kol_buy_count_min']}")
        return False, {"reason": f"KOL数量{len(kol_buys)}<{filters['kol_buy_count_min']}"}
    
    # 7. 检查KOL总买入金额
    if total_buy_amount < filters["kol_buy_amount_min"]:
        log(f"  ❌ KOL买入${total_buy_amount:.2f} < ${filters['kol_buy_amount_min']}")
        return False, {"reason": f"KOL金额${total_buy_amount:.2f}<${filters['kol_buy_amount_min']}"}
    
    # 8. 检查KOL未实现盈利和购买时间
    for kol in kol_buys:
        unrealized = kol.get("unrealized_profit", 0)
        
        # 未实现盈利检查（用holder数据中已有的值）
        # 注意：盈利过高说明是后入场，不是"聪明钱"
        if unrealized >= filters["kol_unrealized_profit_max"]:
            log(f"  ❌ KOL未实现盈利${unrealized:.2f} >= ${filters['kol_unrealized_profit_max']}（过高=后入场）")
            return False, {"reason": f"KOL盈利过高"}
        
        # 购买时间检查（仅对有实际交易记录的KOL生效）
        if kol.get("last_buy_time", 0) > 0:
            buy_age_minutes = (datetime.now().timestamp() - kol["last_buy_time"]) / 60
            if buy_age_minutes >= filters["kol_buy_time_max_minutes"]:
                log(f"  ❌ KOL购买时间{buy_age_minutes:.1f}min >= {filters['kol_buy_time_max_minutes']}min")
                return False, {"reason": f"KOL购买时间过久"}
    
    log(f"  ✅ {token_address[:12]}... KOL指标全部达标!")
    return True, {
        "kol_buys": kol_buys,
        "total_buy_amount": total_buy_amount,
        "recent_buy_count": recent_buy_count
    }

# ============ Phase 1: XXYY 初筛 ============

def phase1_xxxy_scan(config):
    """Phase1: XXYY trending 代币筛选（数据完整，无需单独查询）"""
    log("=" * 50)
    log("🔍 Phase1: XXYY trending 代币初筛")
    
    chains = config["settings"]["xxxy"]["chains"]
    existing = get_all_addresses_in_db()
    new_tokens = []
    
    for chain in chains:
        log(f"  📡 获取 {chain}/trending...")
        items = fetch_xxxy_feed(chain)
        log(f"  📡 {chain}/trending 获取到 {len(items)} 个代币")
        
        for item in items:
            token_addr = item.get("tokenAddress", "") or item.get("mint", "")
            if not token_addr or token_addr in existing:
                continue
            
            token_info = check_xxxy_filters(token_addr, chain, config, token_data=item)
            if token_info:
                new_tokens.append(token_info)
                existing.add(token_addr)
    
    # 写入数据库1号
    if new_tokens:
        db1 = load_db("db1")
        db1["tokens"].extend(new_tokens)
        save_db("db1", db1)
        log(f"  ✅ 新增 {len(new_tokens)} 个代币到数据库1号")
        for t in new_tokens:
            log(f"     - {t['tokenAddress'][:20]}... ({t['chain']})")
    
    return len(new_tokens)

# ============ Phase 2: AVE KOL验证 ============

def phase2_ave_verify(config):
    """Phase2: AVE KOL指标验证"""
    log("=" * 50)
    log("🔍 Phase2: AVE KOL指标验证")
    
    db1 = load_db("db1")
    tokens_to_remove = []
    to_db2 = []
    to_db4 = []
    
    now_ts = datetime.now().timestamp()
    
    for token in db1.get("tokens", []):
        token_addr = token["tokenAddress"]
        chain = token.get("chain", "bsc")
        
        # 检查冷却时间
        last_verify = token.get("last_verify_time")
        rounds = token.get("verify_rounds", 0)
        
        if last_verify:
            last_verify_dt = datetime.fromisoformat(last_verify)
            elapsed = (datetime.now() - last_verify_dt).total_seconds()
            if elapsed < COOLDOWN_SECONDS:
                remaining = COOLDOWN_SECONDS - elapsed
                log(f"  ⏳ {token_addr[:12]}... 冷却中({remaining:.0f}s剩余)")
                continue
        
        log(f"  🔍 验证代币: {token_addr[:20]}... (第{rounds+1}次)")
        
        # 调用AVE验证
        passed, result = check_ave_kol_filters(token_addr, chain, config)
        
        # 更新验证记录
        token["verify_rounds"] = rounds + 1
        token["last_verify_time"] = datetime.now().isoformat()
        token["kol_checks"].append({
            "time": datetime.now().isoformat(),
            "passed": passed,
            "result": result
        })
        
        if passed:
            log(f"  ✅ {token_addr[:12]}... KOL验证通过!")
            to_db2.append(token)
            tokens_to_remove.append(token_addr)
        else:
            if rounds + 1 >= MAX_VERIFY_ROUNDS:
                log(f"  ❌ {token_addr[:12]}... 验证{rounds+1}次不通过，移入数据库4号")
                to_db4.append(token)
                tokens_to_remove.append(token_addr)
            else:
                log(f"  ⏳ {token_addr[:12]}... 第{rounds+1}次验证失败，{COOLDOWN_SECONDS}秒后重试")
        
        # 每个代币间隔
        time.sleep(TOKEN_DELAY)
    
    # 更新数据库1号
    db1["tokens"] = [t for t in db1["tokens"] if t["tokenAddress"] not in tokens_to_remove]
    save_db("db1", db1)
    
    # 写入数据库2号
    if to_db2:
        db2 = load_db("db2")
        db2["tokens"].extend(to_db2)
        save_db("db2", db2)
        log(f"  ✅ {len(to_db2)} 个代币移入数据库2号")
    
    # 写入数据库4号
    if to_db4:
        db4 = load_db("db4")
        db4["tokens"].extend(to_db4)
        save_db("db4", db4)
        log(f"  ❌ {len(to_db4)} 个代币移入数据库4号")
    
    return len(to_db2), len(to_db4)

# ============ 主循环 ============

def init_report():
    header = f"""# XXYY + AVE 联合扫描任务汇报

## 任务配置
- 扫描间隔: 每5秒
- XXYY过滤: 流动性>$8000 | 市值$800k-$10M | Top10<35% | 持币>50 | 成交量>$30k
- AVE验证: 5min买<卖 | KOL数>2 | KOL金额>$100 | KOL未实现盈利<10% | KOL购买时间<5min
- 冷却机制: 验证失败等待30秒，重复3次后移入db4

## 运行记录
---
"""
    with open(REPORT_FILE, 'w', encoding='utf-8') as f:
        f.write(header)

def run_task():
    log("🚀 XXYY+AVE联合扫描任务启动")
    log(f"⏰ 扫描间隔: {SCAN_INTERVAL}秒")
    log(f"🔧 KOL冷却: {COOLDOWN_SECONDS}秒, 最大{MAX_VERIFY_ROUNDS}轮")
    
    init_report()
    
    while True:
        try:
            config = load_config()
            
            # Phase 1: XXYY初筛
            new_count = phase1_xxxy_scan(config)
            
            # Phase 2: AVE验证
            to_db2, to_db4 = phase2_ave_verify(config)
            
            # 统计
            db1 = load_db("db1")
            db2 = load_db("db2")
            db3 = load_db("db3")
            db4 = load_db("db4")
            
            log(f"📊 数据库状态: db1={len(db1['tokens'])} | db2={len(db2['tokens'])} | db3={len(db3['tokens'])} | db4={len(db4['tokens'])}")
            
            append_report(f"Phase1新增:{new_count} | db2移入:{to_db2} | db4移入:{to_db4}")
            
            time.sleep(SCAN_INTERVAL)
            
        except KeyboardInterrupt:
            log("\n⚠️ 任务已停止")
            break
        except Exception as e:
            log(f"错误: {e}")
            import traceback
            traceback.print_exc()
            time.sleep(5)

if __name__ == "__main__":
    run_task()
