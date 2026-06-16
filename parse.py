"""
parse.py — turn one raw indianapi stock payload into clean tables.

Produces, per stock:
  * snapshot   : one flat dict of headline figures (price, mcap, P/E, ROE, ...)
  * statements : {'Income','Balance','Cash Flow'} DataFrames, years as columns
  * metrics    : long DataFrame of every keyMetrics figure (category, metric, value)
  * shareholding, analyst rating, news

All money values are in Rs crore as the API returns them.
"""

import re
import pandas as pd

# line items dropped from statements (not data)
_SKIP = {"periodType", "periodLength"}


def _num(s):
    if s is None:
        return None
    try:
        return float(str(s).strip())
    except (ValueError, TypeError):
        return None


def _clean_key(k: str) -> str:
    return re.sub(r"[^a-z0-9]", "", str(k).lower())


def _km_flat(raw) -> dict:
    """Flatten keyMetrics into {clean_key: value}, tolerating the API's
    trailing-')' typos and casing."""
    out = {}
    for cat, items in (raw.get("keyMetrics") or {}).items():
        if isinstance(items, list):
            for it in items:
                k = it.get("key")
                if k is not None:
                    out[_clean_key(k)] = _num(it.get("value"))
    return out


def _annual_periods(raw):
    fins = [p for p in (raw.get("financials") or []) if p.get("Type") == "Annual"]
    return sorted(fins, key=lambda p: int(p["FiscalYear"]))


# ---------------------------------------------------------------------------
def statements(raw) -> tuple[dict, list]:
    periods = _annual_periods(raw)
    years = [int(p["FiscalYear"]) for p in periods]
    name_map = {"INC": "Income", "BAL": "Balance", "CAS": "Cash Flow"}
    out = {}
    for grp, nice in name_map.items():
        items, disp = {}, {}
        for p in periods:
            fy = int(p["FiscalYear"])
            for it in p["stockFinancialMap"].get(grp, []):
                k = it.get("key")
                if not k or k in _SKIP:
                    continue
                items.setdefault(k, {})[fy] = _num(it.get("value"))
                disp[k] = (it.get("displayName") or k).strip()
        if not items:
            out[nice] = pd.DataFrame()
            continue
        df = pd.DataFrame(items).T.reindex(columns=years)
        df.index = [disp.get(k, k) for k in df.index]
        df.index.name = "Line Item"
        out[nice] = df.sort_index()
    return out, years


def _revenue_series(raw):
    periods = _annual_periods(raw)
    out = {}
    for p in periods:
        for it in p["stockFinancialMap"].get("INC", []):
            if it.get("key") == "TotalRevenue":
                out[int(p["FiscalYear"])] = _num(it.get("value"))
    return out


def _income_item(raw, key):
    periods = _annual_periods(raw)
    if not periods:
        return None
    for it in periods[-1]["stockFinancialMap"].get("INC", []):
        if it.get("key") == key:
            return _num(it.get("value"))
    return None


# ---------------------------------------------------------------------------
def snapshot(raw, ticker) -> dict:
    sd = raw.get("stockDetailsReusableData") or {}
    cp = raw.get("companyProfile") or {}
    km = _km_flat(raw)
    cur = raw.get("currentPrice") or {}

    rev = _revenue_series(raw)
    rev_years = sorted(rev)
    latest_fy = rev_years[-1] if rev_years else None
    rev_latest = rev.get(latest_fy) if latest_fy else None
    rev_prev = rev.get(rev_years[-2]) if len(rev_years) >= 2 else None
    rev_growth = (rev_latest / rev_prev - 1) if (rev_latest and rev_prev and rev_prev > 0) else None

    def km1(*keys):
        for k in keys:
            v = km.get(_clean_key(k))
            if v is not None:
                return v
        return None

    return {
        "ticker": ticker,
        "company": raw.get("companyName"),
        "industry": raw.get("industry") or cp.get("mgIndustry"),
        "nse_code": cp.get("exchangeCodeNse"),
        "isin": cp.get("isInId"),
        "price_nse": _num(cur.get("NSE")),
        "pct_change": _num(raw.get("percentChange")),
        "year_high": _num(raw.get("yearHigh")),
        "year_low": _num(raw.get("yearLow")),
        "market_cap_cr": _num(sd.get("marketCap")),
        "pe_ttm": _num(sd.get("pPerEBasicExcludingExtraordinaryItemsTTM")),
        "pb": km1("priceToBookMostRecentFiscalYear"),
        "div_yield_pct": _num(sd.get("currentDividendYieldCommonStockPrimaryIssueLTM")),
        "roe_pct": km1("returnOnAverageEquityTrailing12Month", "returnOnAverageEquityMostRecentFiscalYear"),
        "roic_pct": km1("returnOnInvestmentTrailing12Month", "returnOnInvestmentMostRecentFiscalYear"),
        "op_margin_pct": km1("operatingMarginTrailing12Month"),
        "net_margin_pct": km1("netProfitMarginPercentTrailing12Month"),
        "gross_margin_pct": km1("grossMarginTrailing12Month"),
        "debt_to_equity": km1("totalDebtPerTotalEquityMostRecentQuarter", "totalDebtPerTotalEquityMostRecentFiscalYear"),
        "current_ratio": km1("currentRatioMostRecentFiscalYear"),
        "interest_cover": km1("netInterestCoverageMostRecentFiscalYear"),
        "rev_5y_cagr_pct": km1("revenueGrowthRate5Year"),
        "eps_5y_cagr_pct": km1("ePSGrowthRate5Year"),
        "latest_fy": latest_fy,
        "revenue_latest_cr": rev_latest,
        "rev_growth_pct": rev_growth * 100 if rev_growth is not None else None,
        "net_income_cr": _income_item(raw, "NetIncome"),
        "rating": sd.get("averageRating"),
        "risk": (raw.get("riskMeter") or {}).get("categoryName"),
    }


def metrics_long(raw, ticker) -> pd.DataFrame:
    rows = []
    for cat, items in (raw.get("keyMetrics") or {}).items():
        if isinstance(items, list):
            for it in items:
                rows.append({"ticker": ticker, "category": cat,
                             "metric": it.get("key"), "value": _num(it.get("value"))})
    return pd.DataFrame(rows)


def shareholding(raw, ticker) -> pd.DataFrame:
    rows = []
    for cat in (raw.get("shareholding") or []):
        name = cat.get("displayName") or cat.get("categoryName")
        cats = cat.get("categories") or []
        if cats:
            latest = cats[-1]
            rows.append({"ticker": ticker, "holder": name,
                         "as_of": latest.get("holdingDate"),
                         "percent": _num(latest.get("percentage"))})
    return pd.DataFrame(rows)


def news(raw):
    return raw.get("recentNews") or []
