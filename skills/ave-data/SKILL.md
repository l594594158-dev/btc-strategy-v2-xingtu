---
name: ave-data
description: >-
  获取 Ave Data API 的 KOL 钱包数据、聪明钱包列表、钱包盈亏、持币分析等。
  用于分析聪明钱/大V钱包动向，配合 XXYY 或 Ave Trade API 实现跟单交易。
  触发词: "KOL钱包", "聪明钱", "smart money", "大V钱包", "跟单", "wallet分析", "Ave"
version: 1.0.0
metadata: { "openclaw": { "requires": { "env": ["AVE_API_KEY"], "bins": ["curl"] }, "primaryEnv": "AVE_API_KEY", "emoji": "📊", "homepage": "https://cloud.ave.ai" } }
---

# Ave Data API

数据 API（非交易 API），用于查询 KOL 钱包、聪明钱包、持币分布、交易历史等。

**Base URL:** `https://data.ave-api.xyz` 或 `https://prod.ave-api.com`
**认证:** Header `X-API-KEY: <your_api_key>`

---

## 端点总览

| 功能 | 方法 | 端点 | CU消耗 |
|------|------|------|--------|
| **聪明钱包列表** | GET | `/v2/address/smart_wallet/list` | 5 |
| 钱包PNL(单代币) | GET | `/v2/address/pnl` | 5 |
| 钱包信息(全链) | GET | `/v2/address/walletinfo` | 5 |
| 钱包持仓 | GET | `/v2/address/walletinfo/tokens` | 10 |
| 钱包交易历史 | GET | `/v2/address/tx` | 100 |
| 代币Top100 holders | GET | `/v2/tokens/top100/{token-id}` | 10 |
| 代币详情 | GET | `/v2/tokens/{token-id}` | 5 |
| 代币搜索 | GET | `/v2/tokens` | 5 |
| 代币批量价格 | POST | `/v2/tokens/price` | 100 |
| 热门代币 | GET | `/v2/tokens/trending` | 5 |
| 代币风险检测 | GET | `/v2/contracts/{token-id}` | 10 |
| 交易对详情 | GET | `/v2/pairs/{pair-id}` | 5 |
| Swap历史 | GET | `/v2/txs/swap/{pair-id}` | 50 |
| 流动性历史 | GET | `/v2/txs/liq/{pair-id}` | 50 |
| 支持的链 | GET | `/v2/supported_chains` | - |

---

## 链标识符

| Chain | ID |
|-------|-----|
| Solana | `solana` |
| BSC | `bsc` |
| Ethereum | `eth` |
| Base | `base` |
| Arbitrum | `arbitrum` |
| Optimism | `optimism` |
| Avalanche | `avax` |
| Polygon | `polygon` |
| Blast | `blast` |
| Merlin | `merlin` |
| TON | `ton` |

---

## 核心端点详解

### 1. 聪明钱包列表 ⭐
`GET /v2/address/smart_wallet/list`

按盈利能力筛选链上聪明钱包排名。

**参数:**
| 参数 | 必填 | 说明 |
|------|------|------|
| chain | Yes | 链名，如 `solana`, `bsc` |
| sort | No | 排序字段: `total_profit`, `total_profit_rate`, `total_volume`, `total_trades`, `token_profit_rate`, `last_trade_time` |
| sort_dir | No | `desc`(默认) 或 `asc` |

**示例:**
```bash
curl -s "https://data.ave-api.xyz/v2/address/smart_wallet/list?chain=solana&sort=total_profit_rate&sort_dir=desc" \
  -H "X-API-KEY: $AVE_API_KEY"
```

### 2. 钱包PNL（单个代币）
`GET /v2/address/pnl`

查询某个钱包在某个代币上的盈亏。

**参数:**
| 参数 | 必填 | 说明 |
|------|------|------|
| wallet_address | Yes | 钱包地址 |
| chain | Yes | 链名 |
| token_address | Yes | 代币合约地址 |
| from_time | No | Unix时间戳（最早15天前） |
| page_size | No | 默认100，最大100 |

### 3. 钱包信息（全链）
`GET /v2/address/walletinfo`

查询某钱包在一条链上所有代币的盈亏。

**参数:**
| 参数 | 必填 | 说明 |
|------|------|------|
| wallet_address | Yes | 钱包地址 |
| chain | Yes | 链名 |

### 4. 钱包持仓
`GET /v2/address/walletinfo/tokens`

查询某钱包在某链上的所有持仓代币。

**参数:**
| 参数 | 必填 | 说明 |
|------|------|------|
| wallet_address | Yes | 钱包地址 |
| chain | Yes | 链名 |
| sort | No | `total_profit`, `unrealized_profit`, `balance_amount`, `balance_usd`, `last_txn_time` |
| sort_dir | No | `desc`(默认) 或 `asc` |
| hide_sold | No | 1=隐藏已卖出，默认0 |
| hide_small | No | 1=隐藏小额，默认0 |

### 5. 代币Top100 holders
`GET /v2/tokens/top100/{token-id}`

格式: `token_address-chain`，如 `4k3Dyjzvzp8eMZWUXbBCjEvwSkkk59S5iCNLY3QrkX6R-solana`

返回: holder地址, 持仓比例, 持仓USD, 买卖历史

### 6. Swap交易历史
`GET /v2/txs/swap/{pair-id}`

查询某交易对的所有swap记录。

返回: tx_id, time, sender, from/to代币, 金额, 价格, buy/sell类型

### 7. 钱包交易历史
`GET /v2/address/tx`

查询某钱包在某个代币上的完整交易历史。

**参数:**
| 参数 | 必填 | 说明 |
|------|------|------|
| wallet_address | Yes | 钱包地址 |
| chain | Yes | 链名 |
| token_address | Yes | 代币地址 |
| from_time | No | Unix时间戳（最早15天前） |

---

## XXYY 也有同类接口（已有API Key可直接用）

| 功能 | 端点 |
|------|------|
| **KOL买币列表** | `GET /api/trade/open/api/kol-buy-list` |
| **聪明钱包买币列表** | `GET /api/trade/open/api/tag-holder-buy-list` |
| 代币查询 | `GET /api/trade/open/api/query` |
| 钱包列表 | `GET /api/trade/open/api/wallets` |

XXYY 接口 Header: `Authorization: Bearer xxyy_ak_6aa15eea2a2444bfbe91ab`

---

## 示例查询

### Ave - 查询SOL链聪明钱包（按收益率排序）
```bash
curl -s "https://data.ave-api.xyz/v2/address/smart_wallet/list?chain=solana&sort=total_profit_rate&sort_dir=desc" \
  -H "X-API-KEY: $AVE_API_KEY"
```

### XXYY - 查询BSC KOL买币列表
```bash
curl -s "https://www.xxyy.io/api/trade/open/api/kol-buy-list?chain=bsc" \
  -H "Authorization: Bearer xxyy_ak_6aa15eea2a2444bfbe91ab"
```

### XXYY - 查询BSC 聪明钱包买币列表
```bash
curl -s "https://www.xxyy.io/api/trade/open/api/tag-holder-buy-list?chain=bsc" \
  -H "Authorization: Bearer xxyy_ak_6aa15eea2a2444bfbe91ab"
```

### Ave - 查询某钱包在某代币上的盈亏
```bash
curl -s "https://data.ave-api.xyz/v2/address/pnl?wallet_address=<地址>&chain=solana&token_address=<代币>" \
  -H "X-API-KEY: $AVE_API_KEY"
```

### Ave - 代币Top100 holders
```bash
curl -s "https://data.ave-api.xyz/v2/tokens/top100/<token_address>-solana" \
  -H "X-API-KEY: $AVE_API_KEY"
```

---

## WebSocket（需Pro计划）

**Endpoint:** `wss://wss.ave-api.xyz`

| 订阅类型 | 命令 | 说明 |
|---------|------|------|
| 实时Swap | `subscribe tx <pair_address> <chain>` | 交易对swap推送 |
| 实时流动性 | `subscribe liq <pair_address> <chain>` | 流动性变化推送 |
| 实时K线 | `subscribe kline <pair_address> <chain> [interval]` | K线更新 |
| 实时价格 | `subscribe price <addr-chain> [<addr-chain>...]` | 价格变动推送 |
