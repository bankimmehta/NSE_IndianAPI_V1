#!/usr/bin/env python3
"""
app.py — Streamlit viewer for the indianapi.in NIFTY 50 dataset.

Reads what extract.py produced (output/nifty50_data.json + the Excel). It does
NOT call the API, so browsing never spends your quota.

Run:  streamlit run app.py
"""

import json
import streamlit as st

st.set_page_config(page_title="NIFTY 50 Fundamentals", layout="wide")
st.title("📊 NIFTY 50 Fundamentals — indianapi.in")
st.caption("All figures in ₹ crore · annual statements · read-only (no API calls)")

import pandas as pd
import config
import parse
import analysis

DATA = config.OUTPUT_DIR / "nifty50_data.json"
XLSX = config.OUTPUT_DIR / "nifty50_fundamentals.xlsx"

if not DATA.exists():
    st.warning("No data yet. Run **`python extract.py`** first (it fetches the 50 "
               "stocks and writes the dataset this app reads).")
    st.stop()

with open(DATA, encoding="utf-8") as f:
    raw_all = json.load(f)


@st.cache_data
def overview_df():
    return pd.DataFrame([parse.snapshot(raw, tk) for tk, raw in raw_all.items()])


@st.cache_data
def analysis_df():
    return pd.DataFrame([analysis.summary_row(raw, tk) for tk, raw in raw_all.items()])


ov = overview_df()
an = analysis_df()

tab_overview, tab_screen, tab_detail = st.tabs(
    ["🏆 Overview", "🔬 Screener", "🔍 Stock detail"])

# ---------------------------------------------------------------------------
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
           "rev_growth_pct": "{:+.1f}%", "rev_5y_cagr_pct": "{:.1f}%",
           "div_yield_pct": "{:.2f}%"}
    styled = view.style.format({k: v for k, v in fmt.items() if k in view.columns}, na_rep="—")
    st.dataframe(styled, use_container_width=True, height=620)

    if XLSX.exists():
        with open(XLSX, "rb") as f:
            st.download_button("⬇️ Download full Excel workbook", f.read(),
                               "nifty50_fundamentals.xlsx",
                               "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

# ---------------------------------------------------------------------------
with tab_screen:
    st.subheader("Shortlist on your own rules")
    st.caption("All criteria evaluated over the full multi-year history. "
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
    cols = ["ticker", "company", "rev_cagr_pct", "ni_cagr_pct", "roce_avg_pct",
            "roe_avg_pct", "de_now", "piotroski_f", "altman_zone",
            "fcf_positive_years", "n_red_flags", "n_green_flags"]
    st.dataframe(hits[[c for c in cols if c in hits.columns]]
                 .sort_values("roce_avg_pct", ascending=False),
                 use_container_width=True, hide_index=True, height=460)
    st.download_button("⬇️ Download shortlist (CSV)", hits.to_csv(index=False).encode(),
                       "shortlist.csv", "text/csv")

# ---------------------------------------------------------------------------
with tab_detail:
    labels = {tk: f"{tk} — {raw.get('companyName','')}" for tk, raw in raw_all.items()}
    pick = st.selectbox("Stock", list(raw_all.keys()), format_func=lambda t: labels[t])
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
            st.dataframe(show.style.format("{:,.0f}", na_rep="—"),
                         use_container_width=True)

    # ---- multi-year analysis ----
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
    st.markdown("**Ratios by year** (trend read across the row)")
    rt = analysis.ratio_table(raw, pick)
    rt.columns = [str(c) for c in rt.columns]
    st.dataframe(rt.style.format("{:,.1f}", na_rep="—"), use_container_width=True)

    cc = st.columns(2)
    with cc[0]:
        st.markdown("#### Key ratios")
        km = parse.metrics_long(raw, pick)
        if not km.empty:
            for cat in km["category"].unique():
                sub = km[km["category"] == cat][["metric", "value"]]
                with st.expander(cat):
                    st.dataframe(sub.reset_index(drop=True), use_container_width=True,
                                 height=min(300, 40 + 28 * len(sub)))
    with cc[1]:
        st.markdown("#### Shareholding (latest)")
        sh = parse.shareholding(raw, pick)
        if not sh.empty:
            st.dataframe(sh[["holder", "percent", "as_of"]], use_container_width=True)
        av = raw.get("analystView") or []
        if av:
            st.markdown("#### Analyst recommendations")
            ad = pd.DataFrame([{"Rating": a.get("ratingName"),
                                "Analysts": a.get("numberOfAnalystsLatest")}
                               for a in av if a.get("ratingName") != "Total"])
            st.dataframe(ad, use_container_width=True, hide_index=True)

    news = parse.news(raw)
    if news:
        st.markdown("#### Recent news")
        for n in news[:6]:
            st.markdown(f"- [{n.get('title')}]({n.get('url')})  ·  _{n.get('source')}_")
