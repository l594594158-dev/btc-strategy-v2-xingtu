---
name: xxyy-trade
description: >-
  This skill should be used when the user asks to "buy token", "sell token",
  "swap token", "trade crypto", "check trade status", "query transaction",
  "scan tokens", "feed", "monitor chain", "query token", "token details",
  "check token safety", "list wallets", "show wallets", "my wallets",
  "AI scan", "AI扫链", "auto scan", "smart scan", "tweet scan", "推文扫链",
  "twitter scan", "onboarding", "get started",
  "check IP", "get IP", "IP whitelist", "查IP", "IP白名单",
  "launch token", "create token", "发币", "创建代币",
  or mentions trading on Solana/ETH/BSC/Base chains via XXYY.
  Enables on-chain token trading and data queries through the XXYY Open API.
version: 1.3.0
metadata: { "openclaw": { "requires": { "env": ["XXYY_API_KEY"], "bins": ["curl"] }, "primaryEnv": "XXYY_API_KEY", "emoji": "💹", "homepage": "https://www.xxyy.io" } }
---

# XXYY Trade

On-chain token trading and data queries on Solana, Ethereum, BSC, and Base via XXYY Open API.

## Prerequisites

Set environment variables before use:
- `XXYY_API_KEY` (required) -- Your XXYY Open API Key (format: `xxyy_ak_xxxx`). Get one at https://www.xxyy.io/apikey
- `XXYY_API_BASE_URL` (optional) -- API base URL, defaults to `https://www.xxyy.io`

## Authentication

All requests require header: `Authorization: Bearer $XXYY_API_KEY`

## Security Notes

- **⚠️ API Key = Wallet access** -- Your XXYY API Key can execute real on-chain trades using your wallet balance. If it leaks, anyone can buy/sell tokens with your funds. Never share it, never commit it to version control, never expose it in logs or public channels. If you suspect a leak, regenerate the key immediately at https://xxyy.io.
- **Custodial trading model** -- XXYY is a custodial trading platform. You only provide your wallet address (public key) and API Key. No private keys or wallet signing are needed -- XXYY executes trades on your behalf through their platform.
- **No read-only mode** -- The same API Key is used for both data queries (Feed, Token Query) and trading (Buy, Sell). There is currently no separate read-only key.
- **IP whitelist (recommended)** -- For extra security, configure an IP whitelist for your API Key at https://www.xxyy.io/apikey. Only whitelisted IPs can call the API. Use the `get_ip` tool to check your current outbound IP before setting up the whitelist.

## API Reference

> **STRICT: Only the endpoints listed below exist. Do NOT guess, infer, or construct any URL that is not explicitly documented here. If you need functionality not covered below, tell the user it is not supported.**
>
> Complete endpoint list:
> - `POST /api/trade/open/api/swap` — Buy / Sell
> - `GET  /api/trade/open/api/trade` — Query Trade
> - `GET  /api/trade/open/api/ping` — Ping
> - `POST /api/trade/open/api/feed/{type}` — Feed Scan
> - `GET  /api/trade/open/api/query` — Token Query
> - `GET  /api/trade/open/api/wallets` — List Wallets
> - `GET  /api/trade/open/api/wallet/info` — Wallet Info
> - `GET  /api/trade/open/api/pnl` — PNL Query
> - `GET  /api/trade/open/api/trades` — Trade History
> - `GET  /api/trade/open/api/ip` — Get IP (exempt from IP whitelist)
> - `GET  /api/trade/open/api/kol-buy-list` — KOL Buy List
> - `GET  /api/trade/open/api/tag-holder-buy-list` — Tag Holder Buy List
> - `GET  /api/trade/open/api/label-list` — Label List (tokens with specific labels, SOL only)
> - `POST /api/trade/open/api/signal-list` — Signal List (AI trending signals, SOL/BSC)
> - `POST /api/trade/open/api/trending-list` — Trending List (hot tokens by period, SOL/BSC)
> - `POST /api/trade/open/api/{chain}/launch` — Launch Token (create new token, SOL/BSC)

### Buy Token
`POST ${XXYY_API_BASE_URL:-https://www.xxyy.io}/api/trade/open/api/swap`

```json
{
  "chain": "sol",
  "walletAddress": "<user_wallet>",
  "tokenAddress": "<token_contract>",
  "isBuy": true,
  "amount": 0.1,
  "tip": 0.001,
  "slippage": 20
}
```

#### Buy Parameters

| Param | Required | Type | Valid values | Description |
|-------|----------|------|-------------|-------------|
| `chain` | YES | string | `sol` / `eth` / `bsc` / `base` | Only these 4 values accepted |
| `walletAddress` | YES | string | SOL: Base58 32-44 chars; EVM: 0x+40hex | Wallet address on XXYY platform, must match chain |
| `tokenAddress` | YES | string | Valid contract address | Token contract address to buy |
| `isBuy` | YES | boolean | `true` | Must be true for buy |
| `amount` | YES | number | > 0 | Amount in native currency (SOL/ETH/BNB) |
| `tip` | YES | number | SOL: 0.001-0.1 (unit: SOL); EVM: 0.1-100 (unit: Gwei) | Priority fee for all chains. If not provided, falls back to priorityFee |
| `slippage` | NO | number | 0-100 | Slippage tolerance %, default 20 |
| `model` | NO | number | 1 or 2 | 1=anti-sandwich (default), 2=fast mode |
| `priorityFee` | NO | number | >= 0 | Solana chain only. Extra priority fee in addition to tip |

### Sell Token
`POST ${XXYY_API_BASE_URL:-https://www.xxyy.io}/api/trade/open/api/swap`

```json
{
  "chain": "sol",
  "walletAddress": "<user_wallet>",
  "tokenAddress": "<token_contract>",
  "isBuy": false,
  "amount": 50,
  "tip": 0.001
}
```

#### Sell Parameters

| Param | Required | Type | Valid values | Description |
|-------|----------|------|-------------|-------------|
| `chain` | YES | string | `sol` / `eth` / `bsc` / `base` | Only these 4 values accepted |
| `walletAddress` | YES | string | SOL: Base58 32-44 chars; EVM: 0x+40hex | Wallet address on XXYY platform, must match chain |
| `tokenAddress` | YES | string | Valid contract address | Token contract address to sell |
| `isBuy` | YES | boolean | `false` | Must be false for sell |
| `amount` | YES | number | 1-100 | Sell percentage. Example: 50 = sell 50% of holdings |
| `tip` | YES | number | SOL: 0.001-0.1 (unit: SOL); EVM: 0.1-100 (unit: Gwei) | Priority fee for all chains. If not provided, falls back to priorityFee |
| `slippage` | NO | number | 0-100 | Slippage tolerance %, default 20 |
| `model` | NO | number | 1 or 2 | 1=anti-sandwich (default), 2=fast mode |
| `priorityFee` | NO | number | >= 0 | Solana chain only. Extra priority fee in addition to tip |

### tip / priorityFee Rules

- `tip` (required) -- Universal priority fee for ALL chains. EVM chains (eth/bsc/base) use tip as the priority fee. If tip is not provided, the API falls back to priorityFee.
  - SOL chain: unit is SOL (1 = 1 SOL, very expensive). Recommended range: 0.001 - 0.1
  - EVM chains (eth/bsc/base): unit is Gwei. Recommended range: 0.1 - 100
- `priorityFee` (optional) -- Only effective on Solana chain. Solana supports both tip and priorityFee simultaneously.

### Query Trade
`GET ${XXYY_API_BASE_URL:-https://www.xxyy.io}/api/trade/open/api/trade?txId=<tx_id>`

Response fields: txId, status (pending/success/failed), statusDesc, chain, tokenAddress, walletAddress, isBuy, baseAmount, quoteAmount

### Trade History
`GET ${XXYY_API_BASE_URL:-https://www.xxyy.io}/api/trade/open/api/trades?walletAddress=<wallet>&chain=<chain>`

Paginated query of successful trade records for a specific wallet. Only returns completed transactions, sorted by creation time (newest first).

#### Trade History Parameters

| Param | Required | Type | Valid values | Description |
|-------|----------|------|-------------|-------------|
| `walletAddress` | YES | string | Wallet address | Must belong to current API Key user |
| `chain` | YES | string | `sol` / `eth` / `bsc` / `base` | Chain identifier (required) |
| `tokenAddress` | NO | string | Contract address | Filter by specific token |
| `pageNum` | NO | int | >= 1 | Page number, default 1 |
| `pageSize` | NO | int | 1-20 | Items per page, default 20 |

### Ping
`GET ${XXYY_API_BASE_URL:-https://www.xxyy.io}/api/trade/open/api/ping`

Returns "pong" if API key is valid.

### Feed (Scan Tokens)
`POST ${XXYY_API_BASE_URL:-https://www.xxyy.io}/api/trade/open/api/feed/{type}?chain={chain}`

Retrieve Meme token lists: newly launched, almost graduated, or graduated.

| Param | Required | Type | Valid values | Description |
|-------|----------|------|-------------|-------------|
| `type` | YES | path string | `NEW` / `ALMOST` / `COMPLETED` | NEW = newly launched, ALMOST = almost graduated, COMPLETED = graduated |
| `chain` | NO | query string | `sol` / `bsc` | Only these 2 chains supported. Default `sol` |

All filters are optional. Range parameters use comma-separated string format `"min,max"`.

| Param | Type | Description |
|-------|------|-------------|
| `mc` | string | Market cap range (USD) |
| `liq` | string | Liquidity range (USD) |
| `holder` | string | Holder count range |
| `devHp` | string | Dev holding % range |
| `topHp` | string | Top10 holding % range |
| `progress` | string | Graduation progress % range |

### Token Query
`GET ${XXYY_API_BASE_URL:-https://www.xxyy.io}/api/trade/open/api/query?ca={contract_address}&chain={chain}`

Query token details: price, security checks, tax rates, holder distribution.

| Param | Required | Type | Valid values | Description |
|-------|----------|------|-------------|-------------|
| `ca` | YES | string | Contract address | Token contract address |
| `chain` | NO | string | `sol` / `eth` / `bsc` / `base` | Default `sol` |

### List Wallets
`GET ${XXYY_API_BASE_URL:-https://www.xxyy.io}/api/trade/open/api/wallets`

Query the current user's wallet list (with balances).

| Param | Required | Type | Valid values | Description |
|-------|----------|------|-------------|-------------|
| `chain` | NO | string | `sol` / `eth` / `bsc` / `base` | Default `sol` |

### Get IP
`GET ${XXYY_API_BASE_URL:-https://www.xxyy.io}/api/trade/open/api/ip`

Get the current outbound IP address. **Exempt from IP whitelist restrictions.**

### KOL Buy List
`GET ${XXYY_API_BASE_URL:-https://www.xxyy.io}/api/trade/open/api/kol-buy-list`

Get tokens bought by KOL wallets.

### Signal List
`POST ${XXYY_API_BASE_URL:-https://www.xxyy.io}/api/trade/open/api/signal-list`

AI trending signals (SOL/BSC).

### Trending List
`POST ${XXYY_API_BASE_URL:-https://www.xxyy.io}/api/trade/open/api/trending-list`

Hot tokens by trading period (SOL/BSC).

### Launch Token
`POST ${XXYY_API_BASE_URL:-https://www.xxyy.io}/api/trade/open/api/{chain}/launch`

Create a new token on SOL or BSC.
