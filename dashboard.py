#!/usr/bin/env python3
"""
Birdeye Token Safety Dashboard — Streamlit web app
Real-time Solana token safety scanner powered by Birdeye Data API.

Author: dockfixlabs
Sprint 3 — Birdeye BIP Competition (May 2026)

Deploy: streamlit run dashboard.py
Cloud:  https://streamlit.io/cloud (free, connects to GitHub)
"""

import os
import time
import requests
import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Birdeye Token Safety Radar",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="expanded",
)

BASE_URL = "https://public-api.birdeye.so"

# ── Styles ────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
    .score-safe   { color: #00c853; font-weight: bold; font-size: 1.1em; }
    .score-warn   { color: #ffd600; font-weight: bold; font-size: 1.1em; }
    .score-risky  { color: #ff1744; font-weight: bold; font-size: 1.1em; }
    .metric-card  { background: #1e1e2e; border-radius: 12px; padding: 16px; margin: 4px; }
    .stProgress > div > div { background-color: #6c47ff; }
    div[data-testid="stSidebarContent"] { background: #0e0e1a; }
</style>
""", unsafe_allow_html=True)


# ── BirdEye API helpers ───────────────────────────────────────────────────────

@st.cache_data(ttl=300, show_spinner=False)
def fetch_trending(api_key: str, limit: int = 50, chain: str = "solana") -> list:
    headers = {"X-API-KEY": api_key, "x-chain": chain, "Accept": "application/json"}
    resp = requests.get(
        f"{BASE_URL}/defi/token_trending",
        headers=headers,
        params={"sort_by": "v24hUSD", "sort_type": "desc", "offset": 0, "limit": limit},
        timeout=15,
    )
    if resp.status_code == 200:
        d = resp.json()
        if d.get("success"):
            return d["data"].get("tokens", d["data"].get("items", []))
    return []


@st.cache_data(ttl=300, show_spinner=False)
def fetch_security(api_key: str, address: str, chain: str = "solana") -> dict:
    headers = {"X-API-KEY": api_key, "x-chain": chain, "Accept": "application/json"}
    resp = requests.get(
        f"{BASE_URL}/defi/token_security",
        headers=headers,
        params={"address": address},
        timeout=10,
    )
    if resp.status_code == 200:
        d = resp.json()
        if d.get("success"):
            return d.get("data", {})
    return {}


@st.cache_data(ttl=300, show_spinner=False)
def fetch_overview(api_key: str, address: str, chain: str = "solana") -> dict:
    headers = {"X-API-KEY": api_key, "x-chain": chain, "Accept": "application/json"}
    resp = requests.get(
        f"{BASE_URL}/defi/token_overview",
        headers=headers,
        params={"address": address},
        timeout=10,
    )
    if resp.status_code == 200:
        d = resp.json()
        if d.get("success"):
            return d.get("data", {})
    return {}


@st.cache_data(ttl=300, show_spinner=False)
def fetch_wallet_tokens(api_key: str, wallet_address: str, chain: str = "solana") -> list:
    """Fetch all token holdings for a wallet address."""
    headers = {"X-API-KEY": api_key, "x-chain": chain, "Accept": "application/json"}
    resp = requests.get(
        f"{BASE_URL}/v1/wallet/token_list",
        headers=headers,
        params={"wallet": wallet_address},
        timeout=15,
    )
    if resp.status_code == 200:
        d = resp.json()
        if d.get("success"):
            return d.get("data", {}).get("items", [])
    return []


@st.cache_data(ttl=300, show_spinner=False)
def fetch_new_listings(api_key: str, limit: int = 20, chain: str = "solana") -> list:
    headers = {"X-API-KEY": api_key, "x-chain": chain, "Accept": "application/json"}
    resp = requests.get(
        f"{BASE_URL}/defi/v2/tokens/new_listing",
        headers=headers,
        params={"limit": limit, "meme_platform_enabled": False},
        timeout=15,
    )
    if resp.status_code == 200:
        d = resp.json()
        if d.get("success"):
            return d["data"].get("items", [])
    return []


def score_token(security: dict, overview: dict) -> tuple[float, list[str]]:
    """Score 0-100. Returns (score, risk_flags)."""
    score = 100.0
    flags = []

    if security.get("mintAuthority"):
        score -= 25
        flags.append("🔴 Mintable — authority still active")

    if security.get("freezeAuthority"):
        score -= 15
        flags.append("🟠 Freezable — authority still active")

    top10 = security.get("top10HolderPercent")
    if top10 is not None:
        if top10 > 80:
            score -= 30
            flags.append(f"🔴 High concentration — top 10 hold {top10:.1f}%")
        elif top10 > 50:
            score -= 15
            flags.append(f"🟡 Moderate concentration — top 10 hold {top10:.1f}%")

    liquidity = overview.get("liquidity", 0) or 0
    if liquidity < 5_000:
        score -= 20
        flags.append(f"🟠 Low liquidity — ${liquidity:,.0f}")

    holders = overview.get("holder", 0) or 0
    if holders < 100:
        score -= 10
        flags.append(f"🟡 Few holders — {holders:,}")

    return max(0.0, score), flags


def score_color(score: float) -> str:
    if score >= 70:
        return "score-safe"
    elif score >= 40:
        return "score-warn"
    return "score-risky"


def score_badge(score: float) -> str:
    if score >= 70:
        return "🟢"
    elif score >= 40:
        return "🟡"
    return "🔴"


# ── Sidebar ───────────────────────────────────────────────────────────────────

with st.sidebar:
    st.image("https://bds.birdeye.so/favicon.ico", width=32)
    st.title("🛡️ Token Safety Radar")
    st.caption("Powered by [Birdeye Data](https://bds.birdeye.so) API")
    st.divider()

    api_key = st.text_input(
        "Birdeye API Key",
        value=os.getenv("BIRDEYE_API_KEY", ""),
        type="password",
        help="Get your free key at bds.birdeye.so",
    )

    chain = st.selectbox("Chain", ["solana", "ethereum", "bsc", "base"], index=0)

    top_n = st.slider("Tokens to scan", min_value=10, max_value=100, value=50, step=10)

    min_score = st.slider("Minimum safety score", min_value=0, max_value=100, value=60, step=5)

    show_new_listings = st.checkbox("Also scan new listings", value=False)

    st.divider()
    scan_btn = st.button("🔍 Run Scan", type="primary", use_container_width=True)

    st.divider()
    st.caption("**How scoring works**")
    st.caption("Starts at 100 and deducts:")
    st.caption("• −25 Mintable token")
    st.caption("• −15 Freezable token")
    st.caption("• −30 High holder concentration (>80%)")
    st.caption("• −20 Low liquidity (<$5k)")
    st.caption("• −10 Few holders (<100)")


# ── Main page ─────────────────────────────────────────────────────────────────

st.title("🛡️ Birdeye Token Safety Radar")
st.caption(f"Real-time Solana token safety scoring · {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')} · Built with [Birdeye Data API](https://bds.birdeye.so)")

if not api_key:
    st.info("👈 Enter your Birdeye API key in the sidebar to start scanning.", icon="🔑")
    st.markdown("""
    ### What this does
    This dashboard has two modes:

    **📊 Trending Scan** — Scans the top trending Solana tokens and rates each for safety across 6 risk dimensions.

    **🔍 Wallet Analyzer** — Paste any Solana wallet address to instantly see a safety report for every token you hold.

    | Signal | What it checks |
    |---|---|
    | 🔴 Mintability | Can the creator print more tokens? |
    | 🟠 Freezability | Can the creator freeze wallets? |
    | 🔴 Concentration | Do top 10 wallets hold >80% of supply? |
    | 🟠 Liquidity | Is there enough liquidity to trade safely? |
    | 🟡 Holders | Are there enough unique holders? |

    **Endpoints used:** `/defi/token_trending` · `/defi/token_security` · `/defi/token_overview` · `/defi/v2/tokens/new_listing` · `/v1/wallet/token_list`

    Get your free API key at **[bds.birdeye.so](https://bds.birdeye.so)** — no credit card required.
    """)
    st.stop()

# ── Tabs ─────────────────────────────────────────────────────────────────────
tab_trending, tab_wallet = st.tabs(["📊 Trending Token Scan", "🔍 Wallet Safety Analyzer"])

# ═══════════════════════════════════════════════════════════════════════════════
# TAB 2: WALLET ANALYZER
# ═══════════════════════════════════════════════════════════════════════════════
with tab_wallet:
    st.subheader("🔍 Wallet Safety Analyzer")
    st.caption("Paste a Solana wallet address to see the safety score for every token you hold.")

    wallet_col, btn_col = st.columns([4, 1])
    with wallet_col:
        wallet_address = st.text_input(
            "Wallet address",
            placeholder="e.g. 9WzDXwBbmkg8ZTbNMqUxvQRAyrZzDsGYdLVL9zYtAWWM",
            label_visibility="collapsed",
        )
    with btn_col:
        wallet_scan_btn = st.button("🔍 Analyze", type="primary", use_container_width=True)

    if wallet_scan_btn and wallet_address.strip():
        with st.spinner(f"Fetching tokens for `{wallet_address[:12]}…`"):
            wallet_tokens = fetch_wallet_tokens(api_key, wallet_address.strip(), chain)

        if not wallet_tokens:
            st.warning("No tokens found in this wallet, or the address is invalid. Make sure you're using a Solana wallet address.")
        else:
            w_results = []
            w_progress = st.progress(0, text=f"Scoring {len(wallet_tokens)} tokens…")

            for i, tok in enumerate(wallet_tokens):
                addr = tok.get("address", "")
                symbol = tok.get("symbol", "???")
                usd_value = tok.get("valueUsd", 0) or 0

                w_progress.progress((i + 1) / len(wallet_tokens), text=f"[{i+1}/{len(wallet_tokens)}] {symbol}…")

                security = fetch_security(api_key, addr, chain)
                time.sleep(0.1)
                overview = fetch_overview(api_key, addr, chain)
                score, flags = score_token(security, overview)

                w_results.append({
                    "badge": score_badge(score),
                    "symbol": symbol,
                    "name": tok.get("name", ""),
                    "address": addr,
                    "score": round(score, 1),
                    "flags": flags,
                    "usd_value": usd_value,
                    "price_usd": overview.get("price", 0) or 0,
                    "liquidity_usd": overview.get("liquidity", 0) or 0,
                    "holders": overview.get("holder", 0) or 0,
                    "mintable": bool(security.get("mintAuthority")),
                    "freezable": bool(security.get("freezeAuthority")),
                })

            w_progress.empty()
            st.session_state["wallet_results"] = w_results
            st.session_state["wallet_address"] = wallet_address

    # Display wallet results
    w_results = st.session_state.get("wallet_results", [])
    if w_results:
        w_addr = st.session_state.get("wallet_address", "")
        df_w = pd.DataFrame(w_results)
        safe_w = df_w[df_w["score"] >= min_score]
        risky_w = df_w[df_w["score"] < min_score]
        total_usd = df_w["usd_value"].sum()

        # Portfolio summary
        wc1, wc2, wc3, wc4 = st.columns(4)
        wc1.metric("Tokens in Wallet", len(df_w))
        wc2.metric("✅ Safe", len(safe_w))
        wc3.metric("⚠️ Risky", len(risky_w))
        wc4.metric("Portfolio Value", f"${total_usd:,.2f}")

        if len(risky_w) > 0:
            st.error(f"⚠️ **{len(risky_w)} risky token(s) detected in your wallet.** Review the details below.")
        else:
            st.success("✅ All tokens in this wallet passed the safety check!")

        # Safe wallet tokens
        if len(safe_w) > 0:
            st.subheader(f"✅ Safe Holdings ({len(safe_w)})")
            safe_w_display = safe_w[["badge", "symbol", "score", "usd_value", "liquidity_usd", "holders", "mintable", "freezable"]].copy()
            safe_w_display.columns = ["🚦", "Symbol", "Score", "Value (USD)", "Liquidity", "Holders", "Mintable", "Freezable"]
            safe_w_display["Value (USD)"] = safe_w_display["Value (USD)"].apply(lambda x: f"${x:,.2f}")
            safe_w_display["Liquidity"] = safe_w_display["Liquidity"].apply(lambda x: f"${x:,.0f}")
            safe_w_display["Holders"] = safe_w_display["Holders"].apply(lambda x: f"{x:,}")
            st.dataframe(
                safe_w_display,
                use_container_width=True,
                hide_index=True,
                column_config={
                    "Score": st.column_config.ProgressColumn("Score", min_value=0, max_value=100, format="%.0f"),
                    "Mintable": st.column_config.CheckboxColumn("Mintable"),
                    "Freezable": st.column_config.CheckboxColumn("Freezable"),
                },
            )

        # Risky wallet tokens
        if len(risky_w) > 0:
            st.subheader(f"⚠️ Risky Holdings ({len(risky_w)})")
            for _, row in risky_w.sort_values("score").iterrows():
                with st.container():
                    rc1, rc2 = st.columns([1, 4])
                    with rc1:
                        st.metric(f"{row['symbol']}", f"{row['score']:.0f} / 100")
                    with rc2:
                        st.caption(f"Value: **${row['usd_value']:,.2f}** · `{row['address'][:20]}…`")
                        for flag in row["flags"]:
                            st.caption(flag)
                st.divider()

        # CSV export
        w_csv = df_w.drop(columns=["badge", "flags"], errors="ignore").to_csv(index=False)
        st.download_button(
            "📥 Download Wallet Report (CSV)",
            data=w_csv,
            file_name=f"wallet_safety_{w_addr[:8]}_{datetime.utcnow().strftime('%Y%m%d')}.csv",
            mime="text/csv",
        )

    elif not wallet_scan_btn:
        st.info("Enter a Solana wallet address above and click Analyze.")



# ═══════════════════════════════════════════════════════════════════════════════
# TAB 1: TRENDING SCAN
# ═══════════════════════════════════════════════════════════════════════════════
with tab_trending:

    # Run scan
    if scan_btn or ("results" not in st.session_state):
        if not api_key:
            st.warning("Please enter your Birdeye API key first.")
            st.stop()

        with st.spinner("Fetching trending tokens..."):
            tokens = fetch_trending(api_key, limit=top_n, chain=chain)

        if not tokens:
            st.error("Could not fetch trending tokens. Check your API key and try again.")
            st.stop()

        results = []
        api_calls = 1  # trending = 1 call

        progress = st.progress(0, text=f"Scanning {len(tokens)} tokens...")
        status_placeholder = st.empty()

        for i, token in enumerate(tokens):
            addr = token.get("address") or token.get("mint", "")
            symbol = token.get("symbol", "???")

            progress.progress((i + 1) / len(tokens), text=f"[{i+1}/{len(tokens)}] Scanning {symbol}…")

            security = fetch_security(api_key, addr, chain)
            api_calls += 1
            time.sleep(0.1)

            overview = fetch_overview(api_key, addr, chain)
            api_calls += 1

            score, flags = score_token(security, overview)

            results.append({
                "rank": i + 1,
                "badge": score_badge(score),
                "symbol": symbol,
                "name": token.get("name", ""),
                "address": addr,
                "score": round(score, 1),
                "flags": flags,
                "flag_count": len(flags),
                "v24hUSD": overview.get("v24hUSD") or token.get("v24hUSD", 0) or 0,
                "price_usd": overview.get("price", 0) or 0,
                "liquidity_usd": overview.get("liquidity", 0) or 0,
                "holders": overview.get("holder", 0) or 0,
                "top10_holder_pct": security.get("top10HolderPercent", 0) or 0,
                "mintable": bool(security.get("mintAuthority")),
                "freezable": bool(security.get("freezeAuthority")),
            })

        # New listings
        new_listing_results = []
        if show_new_listings:
            with st.spinner("Fetching new listings..."):
                new_tokens = fetch_new_listings(api_key, limit=20, chain=chain)
                api_calls += 1
            for token in new_tokens:
                addr = token.get("address", "")
                symbol = token.get("symbol", "???")
                security = fetch_security(api_key, addr, chain)
                api_calls += 1
                overview = fetch_overview(api_key, addr, chain)
                api_calls += 1
                score, flags = score_token(security, overview)
                new_listing_results.append({
                    "symbol": symbol,
                    "name": token.get("name", ""),
                    "address": addr,
                    "score": round(score, 1),
                    "flags": flags,
                    "price_usd": overview.get("price", 0) or 0,
                    "liquidity_usd": overview.get("liquidity", 0) or 0,
                    "holders": overview.get("holder", 0) or 0,
                })

        progress.empty()
        st.session_state["results"] = results
        st.session_state["new_listing_results"] = new_listing_results
        st.session_state["api_calls"] = api_calls
        st.session_state["scan_time"] = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")

    # Display results from session state
    results = st.session_state.get("results", [])
    new_listing_results = st.session_state.get("new_listing_results", [])
    api_calls = st.session_state.get("api_calls", 0)
    scan_time = st.session_state.get("scan_time", "")

    if not results:
        st.info("Click **Run Scan** in the sidebar to start.")
        st.stop()

    df = pd.DataFrame(results)
    safe = df[df["score"] >= min_score]
    risky = df[df["score"] < min_score]

    # ── Summary metrics ───────────────────────────────────────────────────────
    col1, col2, col3, col4, col5 = st.columns(5)
    col1.metric("Tokens Scanned", len(df))
    col2.metric("✅ Safe", len(safe), help=f"Score ≥ {min_score}")
    col3.metric("⚠️ Risky", len(risky), help=f"Score < {min_score}")
    col4.metric("API Calls Made", api_calls)
    col5.metric("Avg Safety Score", f"{df['score'].mean():.1f}")

    st.caption(f"Last scan: {scan_time}")

    # ── Score distribution chart ──────────────────────────────────────────────
    st.subheader("📊 Safety Score Distribution")

    col_chart, col_scatter = st.columns([1, 2])

    with col_chart:
        fig_hist = px.histogram(
            df, x="score", nbins=20,
            color_discrete_sequence=["#6c47ff"],
            labels={"score": "Safety Score", "count": "Tokens"},
            title="Score Histogram",
        )
        fig_hist.add_vline(x=min_score, line_dash="dash", line_color="#ff1744",
                           annotation_text=f"Min safe ({min_score})")
        fig_hist.update_layout(
            plot_bgcolor="#0e0e1a", paper_bgcolor="#0e0e1a",
            font_color="white", height=280,
        )
        st.plotly_chart(fig_hist, use_container_width=True)

    with col_scatter:
        df["v24hUSD_log"] = (df["v24hUSD"] + 1).apply(lambda x: max(x, 1))
        df["color_cat"] = df["score"].apply(
            lambda s: "Safe (≥70)" if s >= 70 else ("Caution (40-69)" if s >= 40 else "Risky (<40)")
        )
        fig_scatter = px.scatter(
            df,
            x="score", y="v24hUSD",
            color="color_cat",
            color_discrete_map={"Safe (≥70)": "#00c853", "Caution (40-69)": "#ffd600", "Risky (<40)": "#ff1744"},
            hover_data={"symbol": True, "score": True, "holders": True, "liquidity_usd": True, "v24hUSD": True, "color_cat": False},
            labels={"score": "Safety Score", "v24hUSD": "24h Volume (USD)"},
            log_y=True,
            title="Safety Score vs 24h Trading Volume",
        )
        fig_scatter.update_layout(
            plot_bgcolor="#0e0e1a", paper_bgcolor="#0e0e1a",
            font_color="white", height=280,
        )
        st.plotly_chart(fig_scatter, use_container_width=True)

    # ── Safe tokens table ─────────────────────────────────────────────────────
    st.subheader(f"✅ Safe Tokens  (score ≥ {min_score})")

    if len(safe) > 0:
        display_cols = ["rank", "badge", "symbol", "score", "price_usd", "liquidity_usd", "holders", "top10_holder_pct", "mintable", "freezable"]
        safe_display = safe[display_cols].copy()
        safe_display.columns = ["#", "🚦", "Symbol", "Score", "Price (USD)", "Liquidity (USD)", "Holders", "Top10 %", "Mintable", "Freezable"]
        safe_display["Price (USD)"] = safe_display["Price (USD)"].apply(lambda x: f"${x:.6f}" if x < 1 else f"${x:,.4f}")
        safe_display["Liquidity (USD)"] = safe_display["Liquidity (USD)"].apply(lambda x: f"${x:,.0f}")
        safe_display["Holders"] = safe_display["Holders"].apply(lambda x: f"{x:,}")
        safe_display["Top10 %"] = safe_display["Top10 %"].apply(lambda x: f"{x:.1f}%" if x else "—")

        st.dataframe(
            safe_display,
            use_container_width=True,
            hide_index=True,
            column_config={
                "Score": st.column_config.ProgressColumn("Score", min_value=0, max_value=100, format="%.0f"),
                "Mintable": st.column_config.CheckboxColumn("Mintable"),
                "Freezable": st.column_config.CheckboxColumn("Freezable"),
            },
        )
    else:
        st.warning(f"No tokens scored ≥ {min_score} in this scan. Try lowering the threshold.")

    # ── Risky tokens ──────────────────────────────────────────────────────────
    with st.expander(f"⚠️ Risky Tokens  ({len(risky)} flagged)", expanded=False):
        if len(risky) > 0:
            for _, row in risky.sort_values("score").iterrows():
                with st.container():
                    c1, c2 = st.columns([1, 4])
                    with c1:
                        st.metric(f"{row['symbol']}", f"{row['score']:.0f} / 100")
                    with c2:
                        st.caption(f"`{row['address'][:20]}…`")
                        for flag in row["flags"]:
                            st.caption(flag)
                st.divider()
        else:
            st.success("No risky tokens found in this scan!")

    # ── New listings ──────────────────────────────────────────────────────────
    if new_listing_results:
        st.subheader("🆕 New Listings Safety Check")
        df_new = pd.DataFrame(new_listing_results)
        st.dataframe(
            df_new[["symbol", "score", "price_usd", "liquidity_usd", "holders"]],
            use_container_width=True,
            hide_index=True,
            column_config={
                "score": st.column_config.ProgressColumn("Score", min_value=0, max_value=100, format="%.0f"),
            },
        )

    # ── Raw data download ─────────────────────────────────────────────────────
    st.subheader("📥 Export")
    csv = df.drop(columns=["badge", "color_cat", "v24hUSD_log", "flags"], errors="ignore").to_csv(index=False)
    st.download_button(
        label="Download Full Results (CSV)",
        data=csv,
        file_name=f"birdeye_scan_{datetime.utcnow().strftime('%Y%m%d_%H%M')}.csv",
        mime="text/csv",
    )

# ── Footer (outside tabs) ─────────────────────────────────────────────────────
st.divider()
st.caption(
    "🛡️ **Birdeye Token Safety Radar** · Built by [@dockfixlabs](https://github.com/dockfixlabs) "
    "for the [Birdeye BIP Competition](https://earn.superteam.fun/listing/birdeye-data-4-week-bip-competition-sprint-2) · "
    "Endpoints: `/defi/token_trending` · `/defi/token_security` · `/defi/token_overview` · `/defi/v2/tokens/new_listing` · `/v1/wallet/token_list`"
)
