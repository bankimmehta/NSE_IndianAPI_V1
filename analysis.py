"""
analysis.py — multi-year fundamental analysis over the FULL statement history.

Core principle: nothing is judged on a single year. Every metric is evaluated
across all available annual periods (>=5 years expected). A weak latest year
shows up as a dip in a trend or as "strong in 6 of 7 years", never as a verdict.

Outputs are factual — values, trends, consistency counts, forensic scores, and
red/green flags with plain-English notes. No weighted composite score.

Everything here runs on the CACHED json — zero API calls.
"""

import numpy as np
import pandas as pd

FIN_HINTS = ["bank", "financ", "nbfc", "insurance", "capital market", "broker", "amc"]

# thresholds (tune to taste)
ROCE_GOOD = 15.0          # %
ROE_GOOD = 15.0           # %
DE_HIGH = 1.5             # debt/equity
INT_COVER_MIN = 3.0       # EBIT / interest
MIN_YEARS = 5             # minimum annual periods for a full read


# ---------------------------------------------------------------------------
# series helpers (pull a line item across all annual years)
# ---------------------------------------------------------------------------
def _num(s):
    try:
        return float(str(s).strip())
    except (ValueError, TypeError):
        return np.nan


def _annual(raw):
    fins = [p for p in (raw.get("financials") or []) if p.get("Type") == "Annual"]
    return sorted(fins, key=lambda p: int(p["FiscalYear"]))


def _series(raw, group, key):
    """{year: value} for one line item across all annual periods."""
    out = {}
    for p in _annual(raw):
        for it in p["stockFinancialMap"].get(group, []):
            if it.get("key") == key:
                out[int(p["FiscalYear"])] = _num(it.get("value"))
    return out


def _ratio_series(num: dict, den: dict, pct=True):
    out = {}
    for y in sorted(set(num) & set(den)):
        n, d = num.get(y), den.get(y)
        if n is not None and d not in (None, 0) and not (isinstance(d, float) and np.isnan(d)):
            out[y] = (n / d) * (100 if pct else 1)
    return out


def is_financial(raw):
    text = f"{raw.get('industry','')} {(raw.get('companyProfile') or {}).get('mgIndustry','')}".lower()
    return any(h in text for h in FIN_HINTS)


# ---------------------------------------------------------------------------
# trend / consistency primitives (operate on a {year: value} series)
# ---------------------------------------------------------------------------
def _clean(series: dict):
    items = [(y, v) for y, v in sorted(series.items())
             if v is not None and not (isinstance(v, float) and np.isnan(v))]
    return items


def cagr(series: dict):
    items = _clean(series)
    if len(items) < 2:
        return np.nan
    (y0, v0), (yn, vn) = items[0], items[-1]
    n = yn - y0
    if v0 is None or v0 <= 0 or vn is None or vn <= 0 or n <= 0:
        return np.nan
    return ((vn / v0) ** (1 / n) - 1) * 100


def trend(series: dict, rel_tol=0.03, pp_tol=0.5, is_pct=False):
    """rising / falling / stable via slope over the window."""
    items = _clean(series)
    if len(items) < 3:
        return "n/a"
    ys = np.array([y for y, _ in items], float)
    vs = np.array([v for _, v in items], float)
    slope = np.polyfit(ys - ys[0], vs, 1)[0]
    if is_pct:                              # series already in % points
        if slope > pp_tol:
            return "rising"
        if slope < -pp_tol:
            return "falling"
        return "stable"
    mean = np.mean(np.abs(vs)) or 1.0
    if slope / mean > rel_tol:
        return "rising"
    if slope / mean < -rel_tol:
        return "falling"
    return "stable"


def count_years(series: dict, predicate):
    items = _clean(series)
    return sum(1 for _, v in items if predicate(v)), len(items)


def latest(series: dict):
    items = _clean(series)
    return items[-1][1] if items else np.nan


def avg(series: dict):
    items = _clean(series)
    return float(np.mean([v for _, v in items])) if items else np.nan


def yoy(series: dict):
    items = _clean(series)
    out = {}
    for (y0, v0), (y1, v1) in zip(items, items[1:]):
        if v0 and v0 > 0:
            out[y1] = (v1 / v0 - 1) * 100
    return out


# ---------------------------------------------------------------------------
# build all the per-year ratio series
# ---------------------------------------------------------------------------
def ratios(raw):
    rev = _series(raw, "INC", "TotalRevenue")
    gp = _series(raw, "INC", "GrossProfit")
    ebit = _series(raw, "INC", "OperatingIncome")
    ni = _series(raw, "INC", "NetIncome")
    eps = _series(raw, "INC", "DilutedNormalizedEPS")
    interest = {y: abs(v) for y, v in _series(raw, "INC", "InterestInc(Exp)Net-Non-OpTotal").items()
                if v is not None}

    ta = _series(raw, "BAL", "TotalAssets")
    teq = _series(raw, "BAL", "TotalEquity")
    tl = _series(raw, "BAL", "TotalLiabilities")
    debt = _series(raw, "BAL", "TotalDebt")
    cash = _series(raw, "BAL", "CashandShortTermInvestments") or _series(raw, "BAL", "Cash")
    tca = _series(raw, "BAL", "TotalCurrentAssets")
    tcl = _series(raw, "BAL", "TotalCurrentLiabilities")
    re = _series(raw, "BAL", "RetainedEarnings(AccumulatedDeficit)")

    ocf = _series(raw, "CAS", "CashfromOperatingActivities")
    capex = _series(raw, "CAS", "CapitalExpenditures")

    cap_employed = {y: ta[y] - tcl.get(y, 0) for y in ta if ta.get(y) is not None}
    fcf = {y: ocf[y] + capex.get(y, 0) for y in ocf if ocf.get(y) is not None}

    return {
        "revenue": rev, "gross_profit": gp, "ebit": ebit, "net_income": ni, "eps": eps,
        "gross_margin": _ratio_series(gp, rev), "op_margin": _ratio_series(ebit, rev),
        "net_margin": _ratio_series(ni, rev),
        "roe": _ratio_series(ni, teq), "roa": _ratio_series(ni, ta),
        "roce": _ratio_series(ebit, cap_employed),
        "debt_equity": _ratio_series(debt, teq, pct=False),
        "interest_cover": _ratio_series(ebit, interest, pct=False),
        "current_ratio": _ratio_series(tca, tcl, pct=False),
        "ocf": ocf, "fcf": fcf, "capex": capex,
        "cash_conversion": _ratio_series(ocf, ni),
        "net_debt": {y: debt.get(y, 0) - cash.get(y, 0) for y in debt},
        "_raw": {"ta": ta, "teq": teq, "tl": tl, "tca": tca, "tcl": tcl, "re": re,
                 "ebit": ebit, "rev": rev, "ni": ni, "ocf": ocf, "debt": debt},
    }


# ---------------------------------------------------------------------------
# forensic scores (computed from the statement window)
# ---------------------------------------------------------------------------
def altman_z_private(r):
    """Altman Z' (book-value variant — no market cap needed). Latest year."""
    R = r["_raw"]
    y = max(R["ta"]) if R["ta"] else None
    if y is None:
        return np.nan, "n/a"
    try:
        ta = R["ta"][y]
        wc = R["tca"][y] - R["tcl"][y]
        z = (0.717 * (wc / ta) + 0.847 * (R["re"][y] / ta) +
             3.107 * (R["ebit"][y] / ta) + 0.420 * (R["teq"][y] / R["tl"][y]) +
             0.998 * (R["rev"][y] / ta))
    except (KeyError, ZeroDivisionError, TypeError):
        return np.nan, "n/a"
    zone = "safe" if z > 2.9 else ("grey" if z >= 1.23 else "distress")
    return round(z, 2), zone


def piotroski_f(r):
    """Piotroski F-score (0-9) using the latest two years."""
    R = r["_raw"]
    yrs = sorted(R["ta"])
    if len(yrs) < 2:
        return np.nan
    y, yp = yrs[-1], yrs[-2]
    s = 0
    try:
        roa_y = R["ni"][y] / R["ta"][y]
        roa_p = R["ni"][yp] / R["ta"][yp]
        s += R["ni"][y] > 0
        s += R["ocf"][y] > 0
        s += roa_y > roa_p
        s += R["ocf"][y] > R["ni"][y]                      # accruals
        s += (R["debt"][y] / R["ta"][y]) < (R["debt"][yp] / R["ta"][yp])  # lower leverage
        s += (R["tca"][y] / R["tcl"][y]) > (R["tca"][yp] / R["tcl"][yp])  # current ratio up
        s += (r["gross_margin"].get(y, 0) > r["gross_margin"].get(yp, 0))  # margin up
        s += (R["rev"][y] / R["ta"][y]) > (R["rev"][yp] / R["ta"][yp])    # asset turnover up
        s += 1                                              # no dilution: assumed (shares ~ flat)
    except (KeyError, ZeroDivisionError, TypeError):
        return np.nan
    return int(s)


# ---------------------------------------------------------------------------
# flags (factual, multi-year)
# ---------------------------------------------------------------------------
def flags(raw, r):
    fin = is_financial(raw)
    red, green = [], []

    # --- earnings quality: NI positive but OCF weak across years ---
    ni, ocf = r["net_income"], r["ocf"]
    bad_cash = [y for y in sorted(set(ni) & set(ocf))
                if (ni.get(y) or 0) > 0 and (ocf.get(y) or 0) < (ni.get(y) or 0) * 0.5]
    if len(bad_cash) >= 2:
        red.append(("Weak cash conversion",
                    f"Operating cash flow well below net income in {len(bad_cash)} years "
                    f"({', '.join('FY'+str(y) for y in bad_cash)}) — earnings not backed by cash."))

    # --- profitability consistency ---
    n_prof, n = count_years(ni, lambda v: v > 0)
    if n and n_prof == n:
        green.append(("Consistently profitable", f"Positive net income in all {n} years."))
    elif n and n_prof <= n - 2:
        red.append(("Loss-making years", f"Net loss in {n - n_prof} of {n} years."))

    # --- ROCE quality across window (non-financial) ---
    if not fin and r["roce"]:
        n_good, n = count_years(r["roce"], lambda v: v >= ROCE_GOOD)
        if n and n_good >= n - 1:
            green.append(("Strong ROCE", f"ROCE >= {ROCE_GOOD:.0f}% in {n_good} of {n} years "
                                         f"(avg {avg(r['roce']):.1f}%)."))
        elif n and n_good == 0:
            red.append(("Low ROCE", f"ROCE never reached {ROCE_GOOD:.0f}% "
                                    f"(avg {avg(r['roce']):.1f}%)."))

    # --- margin direction ---
    gm_t = trend(r["gross_margin"], is_pct=True)
    if gm_t == "falling":
        red.append(("Margins compressing", "Gross margin trending down over the window."))
    elif gm_t == "rising":
        green.append(("Margins expanding", "Gross margin trending up over the window."))

    # --- leverage (non-financial) ---
    if not fin and r["debt_equity"]:
        de_latest = latest(r["debt_equity"])
        if de_latest is not np.nan and de_latest > DE_HIGH and trend(r["debt_equity"]) == "rising":
            red.append(("Rising leverage",
                        f"Debt/Equity at {de_latest:.2f} and climbing."))
        nd = latest(r["net_debt"])
        if nd is not np.nan and nd < 0:
            green.append(("Net cash", "Cash exceeds total debt (net cash position)."))

    # --- interest coverage (non-financial) ---
    if not fin and r["interest_cover"]:
        ic = latest(r["interest_cover"])
        if ic is not np.nan and ic < INT_COVER_MIN:
            red.append(("Thin interest cover",
                        f"EBIT covers interest only {ic:.1f}x (<{INT_COVER_MIN:.0f}x)."))

    # --- FCF generation ---
    if r["fcf"]:
        n_pos, n = count_years(r["fcf"], lambda v: v > 0)
        if n and n_pos == n:
            green.append(("Reliable free cash flow", f"Positive FCF in all {n} years."))
        elif n and n_pos <= n // 2:
            red.append(("Weak free cash flow", f"Negative FCF in {n - n_pos} of {n} years."))

    # --- growth ---
    rev_c = cagr(r["revenue"])
    if not np.isnan(rev_c):
        if rev_c >= 10:
            green.append(("Healthy growth", f"Revenue CAGR {rev_c:.1f}% over the window."))
        elif rev_c < 0:
            red.append(("Shrinking revenue", f"Revenue CAGR {rev_c:.1f}% (declining)."))

    # --- Altman (non-financial) ---
    if not fin:
        z, zone = altman_z_private(r)
        if zone == "distress":
            red.append(("Altman distress zone", f"Altman Z' = {z} (<1.23)."))
        elif zone == "safe":
            green.append(("Altman safe zone", f"Altman Z' = {z} (>2.9)."))

    return red, green


# ---------------------------------------------------------------------------
# top-level: one analysis per stock
# ---------------------------------------------------------------------------
def analyze(raw, ticker):
    r = ratios(raw)
    fin = is_financial(raw)
    red, green = flags(raw, r)
    z, zone = altman_z_private(r) if not fin else (np.nan, "n/a")
    years = sorted(r["revenue"])
    n_years = len(_clean(r["revenue"]))

    severe = [f for f in red if f[0] in
              ("Weak cash conversion", "Loss-making years", "Altman distress zone",
               "Rising leverage", "Shrinking revenue")]
    investigate = (n_years >= MIN_YEARS) and (len(severe) == 0)

    summary = {
        "ticker": ticker,
        "company": raw.get("companyName"),
        "is_financial": fin,
        "years": n_years,
        "rev_cagr_pct": round(cagr(r["revenue"]), 1) if not np.isnan(cagr(r["revenue"])) else None,
        "ni_cagr_pct": round(cagr(r["net_income"]), 1) if not np.isnan(cagr(r["net_income"])) else None,
        "eps_cagr_pct": round(cagr(r["eps"]), 1) if not np.isnan(cagr(r["eps"])) else None,
        "gross_margin_now": round(latest(r["gross_margin"]), 1) if not np.isnan(latest(r["gross_margin"])) else None,
        "gross_margin_trend": trend(r["gross_margin"], is_pct=True),
        "op_margin_trend": trend(r["op_margin"], is_pct=True),
        "net_margin_trend": trend(r["net_margin"], is_pct=True),
        "roe_avg_pct": round(avg(r["roe"]), 1) if not np.isnan(avg(r["roe"])) else None,
        "roe_years_ge15": f"{count_years(r['roe'], lambda v: v>=ROE_GOOD)[0]}/{count_years(r['roe'], lambda v: v>=ROE_GOOD)[1]}",
        "roce_avg_pct": round(avg(r["roce"]), 1) if not np.isnan(avg(r["roce"])) else None,
        "roce_now_pct": round(latest(r["roce"]), 1) if not np.isnan(latest(r["roce"])) else None,
        "de_now": round(latest(r["debt_equity"]), 2) if not np.isnan(latest(r["debt_equity"])) else None,
        "de_trend": trend(r["debt_equity"]),
        "interest_cover_now": round(latest(r["interest_cover"]), 1) if not np.isnan(latest(r["interest_cover"])) else None,
        "current_ratio_now": round(latest(r["current_ratio"]), 2) if not np.isnan(latest(r["current_ratio"])) else None,
        "fcf_positive_years": f"{count_years(r['fcf'], lambda v: v>0)[0]}/{count_years(r['fcf'], lambda v: v>0)[1]}",
        "ocf_positive_years": f"{count_years(r['ocf'], lambda v: v>0)[0]}/{count_years(r['ocf'], lambda v: v>0)[1]}",
        "cash_conversion_avg_pct": round(avg(r["cash_conversion"]), 0) if not np.isnan(avg(r["cash_conversion"])) else None,
        "piotroski_f": piotroski_f(r),
        "altman_z": z if not (isinstance(z, float) and np.isnan(z)) else None,
        "altman_zone": zone,
        "n_red_flags": len(red),
        "n_green_flags": len(green),
        "investigate": investigate,
    }
    return {"summary": summary, "ratios": r, "red": red, "green": green,
            "years": years}


def summary_row(raw, ticker):
    return analyze(raw, ticker)["summary"]


def flags_long(raw, ticker):
    a = analyze(raw, ticker)
    rows = []
    for kind, items in (("RED", a["red"]), ("GREEN", a["green"])):
        for name, note in items:
            rows.append({"ticker": ticker, "type": kind, "flag": name, "note": note})
    return rows


def ratio_table(raw, ticker, keys=("gross_margin", "op_margin", "net_margin",
                                    "roe", "roce", "debt_equity", "interest_cover",
                                    "current_ratio", "fcf")):
    """Wide per-year table (years as columns) for the app/Excel."""
    r = ratios(raw)
    rows = {}
    for k in keys:
        s = r.get(k, {})
        rows[k] = {int(y): v for y, v in s.items()}
    df = pd.DataFrame(rows).T
    df = df.reindex(columns=sorted(df.columns))
    df.index.name = "metric"
    return df
