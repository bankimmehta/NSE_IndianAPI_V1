#!/usr/bin/env python3
"""
app.py — Streamlit viewer for the indianapi.in NIFTY 50 dataset.

Robust data loading (works locally AND on Streamlit Cloud / GitHub):
  1. searches several likely paths for nifty50_data.json
  2. else reads all cache/*.json
  3. else lets you UPLOAD json file(s) right in the browser
Handles both the combined {ticker: bundle} dataset and single-stock bundles,
and de-duplicates name collisions (same company returned for >1 ticker).

Run:  streamlit run app.py
"""

import json
from pathlib import Path

import streamlit as st
import pandas as pd

import config
import parse
import analysis

st.set_page_config(page_title="NIFTY 50 Fundamentals", layout="wide")
st.title("📊 NIFTY 50 Fundamentals — indianapi.in")
st.caption("All figures in ₹ crore · annual statements · read-only (no API calls)")


# ---------------------------------------------------------------------------
# robust dataset loading
# ---------------------------------------------------------------------------
def _wrap(data: dict) -> dict:
    """Normalize loaded JSON into {ticker: bundle}, accepting either form."""
    if isinstance(data, dict) and "financials" in data and "companyName" in data:
        # a SINGLE-stock bundle (e.g. response.json)
        cp = data.get("companyProfile") or {}
        tk = cp.get("exchangeCodeNse") or data.get("companyName") or "STOCK"
        return {tk: data}
    if isinstance(data, dict):
        # combined {ticker: bundle} — keep only entries that look like bundles
        return {k: v for k, v in data.items()
                if isinstance(v, dict) and v.get("financials")}
    return {}


def _candidate_paths():
    names = [config.OUTPUT_DIR / "nifty50_data.json",
             config.ROOT / "nifty50_data.json",
             Path.cwd() / "output" / "nifty50_data.json",
             Path.cwd() / "nifty50_data.json"]
    return names


def load_dataset():
    # 1) combined json on disk
    for p in _candidate_paths():
        if p.exists():
            try:
                return _wrap(json.load(open(p, encoding="utf-8"))), f"file: {p}"
            except Exception:  # noqa: BLE001
                pass
    # 2) rebuild from cache/*.json
    cache_files = sorted(config.CACHE_DIR.glob("*.json")) if config.CACHE_DIR.exists() else []
    if cache_files:
        out = {}
        for cf in cache_files:
            try:
                out.update(_wrap(json.load(open(cf, encoding="utf-8"))))
            except Exception:  # noqa: BLE001
                continue
        if out:
            return out, f"cache/ ({len(out)} stocks)"
    return None, None


def dedupe(raw_all: dict):
    """Keep first ticker per company; report collisions."""
    seen, kept, collisions = {}, {}, {}
    for tk, raw in raw_all.items():
        name = raw.get("companyName") or tk
        if name in seen:
            collisions.setdefault(name, [seen[name]]).append(tk)
        else:
            seen[name] = tk
            kept[tk] = raw
    return kept, collisions


raw_all, source = load_dataset()

# Upload fallback (works on Streamlit Cloud where files aren't on disk)
if not raw_all:
    st.warning("No dataset found on disk. Upload your **nifty50_data.json** "
               "(or one/more per-stock JSON files) to view them here.")
    ups = st.file_uploader("Upload JSON", type="json", accept_multiple_files=True)
    if ups:
        raw_all = {}
        for u in ups:
            try:
                raw_all.update(_wrap(json.load(u)))
            except Exception as e:  # noqa: BLE001
                st.error(f"{u.name}: {e}")
        source = f"upload ({len(raw_all)} stocks)"
    if not raw_all:
        st.info("Tip: commit `output/nifty50_data.json` to your repo so the app "
                "finds it automatically, or upload it above.")
        st.stop()

raw_all, collisions = dedupe(raw_all)
st.caption(f"Loaded {len(raw_all)} stocks · {source}")
if collisions:
    msg = "; ".join(f"**{name}** ← {', '.join(tks)}" for name, tks in collisions.items())
    st.warning("⚠️ Duplicate companies detected — these tickers returned the same "
               f"company (likely a name in `config.NIFTY_50` that didn't resolve): {msg}. "
               "Kept one of each. Fix those names and re-run extract.")


# ---------------------------------------------------------------------------
@st.cache_data
def overview_df(keys):
    return pd.DataFrame([parse.snapshot(raw_all[k], k) for k in keys])


@st.cache_data
def analysis_df(keys):
    return pd.DataFrame([analysis.summary_row(raw_all[k], k) for k in keys])


keys = list(raw_all.keys())
ov = overview_df(keys)
an = analysis_df(keys)

tab_overview, tab_screen, tab_detail = st.tabs(
    ["🏆 Overview", "🔬 Screener", "🔍 Stock detail"])

# ---- Overview ----
with tab_overview:
    st.subheader(f"{len(ov)} stocks")
    cols = ["ticker", "company", "industry", "price_nse", "pct_change",
            "market_cap_cr", "pe_ttm", "pb", "roe_pct", "roic_pct",
            "net_margin_pct", "debt_to_equity", "rev_growth_pct",
            "rev_5y_cagr_pct", "div_yield_pct", "rating"]
    view = ov[[c for c in cols if c in ov.columns]].copy()
    fmt = {"price_nse": "{:.2f}", "pct_change": "{:+.2f}%", "market_cap_cr": "{:,.0f}",
           "pe_ttm": "{:.1f}", "pb": "{:.2f}", "roe_pct": "{:.1f}%", "roic_pct": "{:.1f}%",
           "net_margin_pct": "{:.1f}%", "debt_to_equity": "{:.2f}",
           "rev_growth_pct": "{:+.1f}%", "rev_5y_cagr_pct": "{:.1f}%", "div_yield_pct": "{:.2f}%"}
    st.dataframe(view.style.format({k: v for k, v in fmt.items() if k in view.columns}, na_rep="—"),
                 use_container_width=True, height=560)
    xlsx = config.OUTPUT_DIR / "nifty50_fundamentals.xlsx"
    if xlsx.exists():
        with open(xlsx, "rb") as f:
            st.download_button("⬇️ Download full Excel workbook", f.read(),
                               "nifty50_fundamentals.xlsx",
                               "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

# ---- Screener ----
with tab_screen:
    st.subheader("Shortlist on your own rules")
    st.caption("Every criterion is evaluated over the FULL multi-year history. "
               "Filters apply together (AND).")
    c1, c2, c3 = st.columns(3)
    with c1:
        min_rev_cagr = st.slider("Min revenue CAGR %", -10, 40, 8)
        min_roce = st.slider("Min avg ROCE %", 0, 40, 15)
    with c2:
        max_de = st.slider("Max Debt/Equity", 0.0, 5.0, 1.5, 0.1)
        min_piotroski = st.slider("Min Piotroski F", 0, 9, 5)
    with c3:
        need_fcf = st.checkbox("FCF positive every year", value=False)
        no_red = st.checkbox("No red flags", value=False)
        only_invest = st.checkbox("Only 'investigate' = True", value=True)
        incl_fin = st.checkbox("Include financials", value=True)

    df = an.copy()

    def fcf_all(s):
        try:
            a, b = str(s).split("/"); return a == b and b != "0"
        except Exception:  # noqa: BLE001
            return False

    m = pd.Series(True, index=df.index)
    m &= df["rev_cagr_pct"].fillna(-999) >= min_rev_cagr
    m &= df["roce_avg_pct"].fillna(-999) >= min_roce
    m &= df["de_now"].fillna(999) <= max_de
    m &= df["piotroski_f"].fillna(-1) >= min_piotroski
    if need_fcf:
        m &= df["fcf_positive_years"].apply(fcf_all)
    if no_red:
        m &= df["n_red_flags"] == 0
    if only_invest:
        m &= df["investigate"]
    if not incl_fin:
        m &= ~df["is_financial"]

    hits = df[m]
    st.markdown(f"**{len(hits)} of {len(df)} stocks match.**")
    scols = ["ticker", "company", "rev_cagr_pct", "ni_cagr_pct", "roce_avg_pct",
             "roe_avg_pct", "de_now", "piotroski_f", "altman_zone",
             "fcf_positive_years", "n_red_flags", "n_green_flags"]
    st.dataframe(hits[[c for c in scols if c in hits.columns]]
                 .sort_values("roce_avg_pct", ascending=False),
                 use_container_width=True, hide_index=True, height=440)
    st.download_button("⬇️ Download shortlist (CSV)", hits.to_csv(index=False).encode(),
                       "shortlist.csv", "text/csv")

# ---- Detail ----
with tab_detail:
    labels = {tk: f"{tk} — {raw_all[tk].get('companyName','')}" for tk in keys}
    pick = st.selectbox("Stock", keys, format_func=lambda t: labels[t])
    raw = raw_all[pick]
    snap = parse.snapshot(raw, pick)

    st.subheader(f"{snap['company']}  ·  {snap['industry']}")
    c = st.columns(6)
    c[0].metric("Price (NSE)", f"₹{snap['price_nse']:,.2f}" if snap['price_nse'] else "—",
                f"{snap['pct_change']:+.2f}%" if snap['pct_change'] is not None else None)
    c[1].metric("Market cap", f"₹{snap['market_cap_cr']:,.0f} Cr" if snap['market_cap_cr'] else "—")
    c[2].metric("P/E (TTM)", f"{snap['pe_ttm']:.1f}" if snap['pe_ttm'] else "—")
    c[3].metric("ROE", f"{snap['roe_pct']:.1f}%" if snap['roe_pct'] is not None else "—")
    c[4].metric("Rev growth", f"{snap['rev_growth_pct']:+.1f}%" if snap['rev_growth_pct'] is not None else "—")
    c[5].metric("Rating", snap['rating'] or "—")

    stmts, years = parse.statements(raw)
    st.markdown("#### Financial statements (₹ crore, annual)")
    for name in ["Income", "Balance", "Cash Flow"]:
        df = stmts.get(name)
        if df is None or df.empty:
            continue
        with st.expander(name, expanded=(name == "Income")):
            show = df.copy()
            show.columns = [str(y) for y in show.columns]
            st.dataframe(show.style.format("{:,.0f}", na_rep="—"), use_container_width=True)

    a = analysis.analyze(raw, pick)
    st.markdown("#### Multi-year analysis")
    fc1, fc2 = st.columns(2)
    with fc1:
        if a["red"]:
            st.markdown("**🔴 Red flags**")
            for nm, note in a["red"]:
                st.markdown(f"- **{nm}** — {note}")
        else:
            st.caption("No red flags.")
    with fc2:
        if a["green"]:
            st.markdown("**🟢 Green flags**")
            for nm, note in a["green"]:
                st.markdown(f"- **{nm}** — {note}")
        else:
            st.caption("No green flags.")
    st.markdown("**Ratios by year** (read the trend across each row)")
    rt = analysis.ratio_table(raw, pick)
    rt.columns = [str(c) for c in rt.columns]
    st.dataframe(rt.style.format("{:,.1f}", na_rep="—"), use_container_width=True)

    news = parse.news(raw)
    if news:
        st.markdown("#### Recent news")
        for n in news[:6]:
            st.markdown(f"- [{n.get('title')}]({n.get('url')})  ·  _{n.get('source')}_")
