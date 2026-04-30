#!/usr/bin/env python3
"""
birdeye-token-radar: Solana token safety scanner using Birdeye Data API
Uses /defi/token_trending and /defi/token_security endpoints to surface
only the trending tokens worth watching.

Author: dockfixlabs
"""

import os
import sys
import json
import time
import argparse
import requests
from datetime import datetime
from typing import Optional

BASE_URL = "https://public-api.birdeye.so"

RISK_THRESHOLDS = {
    "top_holder_pct_max": 30.0,   # top holder should own < 30% of supply
    "mintable_reject": True,       # reject mintable tokens
    "freezable_reject": True,      # reject freezable tokens
    "min_liquidity_usd": 5_000,    # at least $5k liquidity
    "min_holder_count": 100,       # at least 100 holders
}

SECURITY_FLAGS = {
    "is_token_2022",
    "top10HolderPercent",
    "ownerBalance",
    "creationTime",
}


class BirdeyeRadar:
    def __init__(self, api_key: str, chain: str = "solana"):
        self.api_key = api_key
        self.chain = chain
        self.session = requests.Session()
        self.session.headers.update({
            "X-API-KEY": api_key,
            "x-chain": chain,
            "Accept": "application/json",
        })
        self.call_count = 0

    def _get(self, endpoint: str, params: dict = None) -> Optional[dict]:
        url = f"{BASE_URL}{endpoint}"
        try:
            resp = self.session.get(url, params=params or {}, timeout=10)
            self.call_count += 1
            if resp.status_code == 200:
                return resp.json()
            else:
                print(f"  [!] {endpoint} -> HTTP {resp.status_code}", file=sys.stderr)
                return None
        except requests.RequestException as e:
            print(f"  [!] Request error: {e}", file=sys.stderr)
            return None

    def get_trending_tokens(self, limit: int = 50, sort_by: str = "v24hUSD") -> list[dict]:
        """Fetch trending tokens sorted by 24h volume."""
        print(f"[*] Fetching top {limit} trending tokens by {sort_by}...")
        data = self._get("/defi/token_trending", params={
            "sort_by": sort_by,
            "sort_type": "desc",
            "offset": 0,
            "limit": limit,
        })
        if data and data.get("success") and data.get("data"):
            tokens = data["data"].get("tokens", data["data"].get("items", []))
            print(f"    -> {len(tokens)} tokens returned")
            return tokens
        return []

    def get_token_security(self, address: str) -> Optional[dict]:
        """Fetch security data for a single token."""
        data = self._get("/defi/token_security", params={"address": address})
        if data and data.get("success"):
            return data.get("data", {})
        return None

    def get_token_overview(self, address: str) -> Optional[dict]:
        """Fetch overview (price, liquidity, holders) for a token."""
        data = self._get("/defi/token_overview", params={"address": address})
        if data and data.get("success"):
            return data.get("data", {})
        return None

    def get_new_listings(self, limit: int = 20) -> list[dict]:
        """Fetch recently listed tokens."""
        print(f"[*] Fetching {limit} new token listings...")
        data = self._get("/defi/v2/tokens/new_listing", params={
            "limit": limit,
            "meme_platform_enabled": False,
        })
        if data and data.get("success") and data.get("data"):
            items = data["data"].get("items", [])
            print(f"    -> {len(items)} new listings")
            return items
        return []

    def score_token(self, security: dict, overview: dict) -> tuple[float, list[str]]:
        """
        Score a token 0-100 based on safety signals.
        Returns (score, list_of_risk_flags).
        """
        score = 100.0
        flags = []

        # --- Mintability ---
        if security.get("mintAuthority"):
            score -= 25
            flags.append("MINTABLE (authority still active)")

        # --- Freezability ---
        if security.get("freezeAuthority"):
            score -= 15
            flags.append("FREEZABLE (authority still active)")

        # --- Top holder concentration ---
        top10 = security.get("top10HolderPercent")
        if top10 is not None:
            if top10 > 80:
                score -= 30
                flags.append(f"HIGH CONCENTRATION: top10 hold {top10:.1f}%")
            elif top10 > 50:
                score -= 15
                flags.append(f"MODERATE CONCENTRATION: top10 hold {top10:.1f}%")

        # --- Liquidity ---
        liquidity = overview.get("liquidity", 0) or 0
        if liquidity < RISK_THRESHOLDS["min_liquidity_usd"]:
            score -= 20
            flags.append(f"LOW LIQUIDITY: ${liquidity:,.0f}")

        # --- Holder count ---
        holders = overview.get("holder", 0) or 0
        if holders < RISK_THRESHOLDS["min_holder_count"]:
            score -= 10
            flags.append(f"FEW HOLDERS: {holders}")

        return max(0.0, score), flags

    def scan(self, top_n: int = 50) -> list[dict]:
        """
        Main scan: fetch trending tokens, check each for security + overview,
        score them, and return sorted results.
        """
        results = []
        tokens = self.get_trending_tokens(limit=top_n)

        if not tokens:
            print("[!] No trending tokens found. Check your API key.")
            return []

        print(f"\n[*] Analysing {len(tokens)} tokens (security + overview per token)...")
        print(f"    (This makes ~{len(tokens) * 2} additional API calls)\n")

        for i, token in enumerate(tokens, 1):
            addr = token.get("address") or token.get("mint")
            symbol = token.get("symbol", "???")
            name = token.get("name", "")
            v24h = token.get("v24hUSD", token.get("v24hChangePercent", 0)) or 0

            sys.stdout.write(f"\r  [{i:>2}/{len(tokens)}] {symbol:<12} {addr[:8]}...")
            sys.stdout.flush()

            security = self.get_token_security(addr) or {}
            time.sleep(0.15)  # polite rate limiting
            overview = self.get_token_overview(addr) or {}
            time.sleep(0.15)

            score, flags = self.score_token(security, overview)

            results.append({
                "rank": i,
                "symbol": symbol,
                "name": name,
                "address": addr,
                "score": score,
                "flags": flags,
                "v24hUSD": overview.get("v24hUSD") or v24h,
                "price_usd": overview.get("price", 0),
                "liquidity_usd": overview.get("liquidity", 0),
                "holders": overview.get("holder", 0),
                "top10_holder_pct": security.get("top10HolderPercent"),
                "mintable": bool(security.get("mintAuthority")),
                "freezable": bool(security.get("freezeAuthority")),
            })

        print(f"\n\n[*] Total API calls made: {self.call_count}")
        results.sort(key=lambda x: (-x["score"], -x["v24hUSD"]))
        return results


def print_report(results: list[dict], min_score: float = 60.0):
    safe = [r for r in results if r["score"] >= min_score and not r["flags"]]
    risky = [r for r in results if r["score"] < min_score or r["flags"]]

    print("\n" + "=" * 70)
    print(f"  BIRDEYE TOKEN RADAR — {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}")
    print("=" * 70)

    print(f"\n✅  SAFE TOKENS (score ≥ {min_score}, {len(safe)} found)\n")
    if safe:
        print(f"  {'#':<4} {'Symbol':<12} {'Score':>6}  {'Price USD':>12}  {'Liq USD':>12}  {'Holders':>8}")
        print("  " + "-" * 58)
        for r in safe[:20]:
            print(
                f"  {r['rank']:<4} {r['symbol']:<12} {r['score']:>5.0f}  "
                f"${r['price_usd']:>11.6f}  ${r['liquidity_usd']:>11,.0f}  {r['holders']:>8,}"
            )
    else:
        print("  (none met the safety threshold)")

    print(f"\n⚠️   RISKY TOKENS ({len(risky)} flagged)\n")
    for r in risky[:10]:
        print(f"  [{r['score']:>3.0f}] {r['symbol']:<12} {r['address'][:12]}...")
        for flag in r["flags"]:
            print(f"         ↳ {flag}")

    print("\n" + "=" * 70)


def main():
    parser = argparse.ArgumentParser(
        description="Birdeye Token Radar — surface safe trending Solana tokens",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python scanner.py --api-key YOUR_KEY
  python scanner.py --api-key YOUR_KEY --top 100 --min-score 70
  python scanner.py --api-key YOUR_KEY --json > results.json
  BIRDEYE_API_KEY=xxx python scanner.py
        """,
    )
    parser.add_argument("--api-key", default=os.getenv("BIRDEYE_API_KEY"), help="Birdeye API key (or set BIRDEYE_API_KEY env var)")
    parser.add_argument("--top", type=int, default=50, help="Number of trending tokens to scan (default: 50)")
    parser.add_argument("--min-score", type=float, default=60.0, help="Minimum safety score to flag as safe (default: 60)")
    parser.add_argument("--json", action="store_true", help="Output results as JSON")
    parser.add_argument("--chain", default="solana", help="Chain to query (default: solana)")
    args = parser.parse_args()

    if not args.api_key:
        print("Error: Birdeye API key required. Use --api-key or set BIRDEYE_API_KEY env var.")
        print("Get a free key at: https://bds.birdeye.so")
        sys.exit(1)

    radar = BirdeyeRadar(api_key=args.api_key, chain=args.chain)
    results = radar.scan(top_n=args.top)

    if args.json:
        print(json.dumps(results, indent=2))
    else:
        print_report(results, min_score=args.min_score)

    print(f"\n[done] {radar.call_count} API calls made across {len(results)} tokens scanned.")


if __name__ == "__main__":
    main()
