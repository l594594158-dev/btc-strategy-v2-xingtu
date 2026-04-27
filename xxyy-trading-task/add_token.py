#!/usr/bin/env python3
"""
添加代币到数据库2号
用法: python3 add_token.py <合约地址> [chain]
"""

import json
import os
import sys
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_DIR = os.path.join(BASE_DIR, "databases")

def add_to_db2(ca, chain="bsc"):
    db_file = os.path.join(DB_DIR, "db2.json")
    
    with open(db_file, 'r') as f:
        db = json.load(f)
    
    # 检查是否已存在
    for token in db["tokens"]:
        if token.get("tokenAddress") == ca:
            print(f"代币 {ca} 已在数据库2号中")
            return
    
    token = {
        "tokenAddress": ca,
        "chain": chain,
        "add_time": datetime.now().isoformat()
    }
    
    db["tokens"].append(token)
    
    with open(db_file, 'w') as f:
        json.dump(db, f, ensure_ascii=False, indent=2)
    
    print(f"✅ 代币 {ca} 已添加到数据库2号")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法: python3 add_token.py <合约地址> [chain]")
        sys.exit(1)
    
    ca = sys.argv[1]
    chain = sys.argv[2] if len(sys.argv) > 2 else "bsc"
    
    add_to_db2(ca, chain)
