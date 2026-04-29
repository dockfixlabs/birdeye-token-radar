# 🦅 Birdeye Token Radar

A CLI tool that surfaces **safe, trending Solana tokens** by combining Birdeye's trending feed with its token security API — filtering out honeypots, mintable rug pulls, and high-concentration wallets in real time.

Built for the **Birdeye Data 4-Week BIP Competition** (Sprint 2, April–May 2026).

---

## What it does

1. Fetches the top N trending tokens by 24h volume via `/defi/token_trending`
2. Checks each token's security profile via `/defi/token_security`
3. Enriches with price/liquidity/holder data via `/defi/token_overview`
4. Scores each token 0–100 based on risk signals
5. Prints a colour-coded safety report

### Scoring model

| Signal | Penalty |
|---|---|
| Mint authority still active | −25 pts |
| Freeze authority still active | −15 pts |
| Top 10 wallets hold > 80% | −30 pts |
| Top 10 wallets hold 50–80% | −15 pts |
| Liquidity < $5 000 | −20 pts |
| Holder count < 100 | −10 pts |

Tokens scoring ≥ 60 with zero flags are surfaced as **safe**.

---

## Birdeye endpoints used

| Endpoint | Purpose |
|---|---|
| `GET /defi/token_trending` | Pull top 50 tokens ranked by 24h USD volume |
| `GET /defi/token_security` | Detect mint/freeze authority, top-holder concentration |
| `GET /defi/token_overview` | Price, liquidity (USD), holder count |
| `GET /defi/v2/tokens/new_listing` | Optional: scan fresh listings too |

A single full scan of 50 tokens makes **~101 API calls** (1 trending + 50 security + 50 overview).

---

## Quickstart

```bash
git clone https://github.com/dockfixlabs/birdeye-token-radar
cd birdeye-token-radar
pip install requests
export BIRDEYE_API_KEY=your_key_here
python scanner.py --top 50 --min-score 60
```

---

## Options

```
--api-key    Birdeye API key (or set BIRDEYE_API_KEY env var)
--top        Number of trending tokens to scan (default: 50)
--min-score  Minimum score to classify as safe (default: 60)
--json       Emit JSON instead of human-readable table
--chain      Chain to query (default: solana)
```

---

## Author

**[Dockfix Labs](https://github.com/dockfixlabs)** — I solve technical problems for money.
