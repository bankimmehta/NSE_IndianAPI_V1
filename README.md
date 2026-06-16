# NIFTY 50 Fundamentals — indianapi.in

Pulls all NIFTY 50 stocks from **indianapi.in** (the only source that gives
clean, India-correct fundamentals — full 5+ year statements, ratios, analyst
views, shareholding), writes **one Excel workbook**, and serves a **Streamlit**
viewer. No yfinance, no scraping.

## 1. Set your API key (never hardcode it)
```bash
# macOS/Linux
export INDIANAPI_KEY="your-new-key"
# Windows PowerShell
$env:INDIANAPI_KEY="your-new-key"
```
(If your working endpoint differs from the default, also set
`INDIANAPI_URL`. Default is `https://stock.indianapi.in/stock`.)

## 2. Install
```bash
pip install -r requirements.txt
```

## 3. Extract (spends API calls — minds the quota)
```bash
python extract.py                 # all 50; uses cache where < 7 days old
python extract.py --only RELIANCE,TCS,INFY     # subset
python extract.py --refresh       # force re-fetch (~50 calls)
```
Writes to `output/`:
- `nifty50_fundamentals.xlsx` — tabs: **ReadMe, Overview, Income, Balance,
  Cash Flow, KeyMetrics, Shareholding** (all ₹ crore; statement years are columns)
- `nifty50_data.json` — combined dataset the app reads

## 4. View on a webpage
```bash
streamlit run app.py
```
Overview table (sortable) + per-stock detail (statements with years as columns,
key ratios, shareholding, analyst recommendations, news) + Excel download.
**The app never calls the API**, so browsing costs nothing.

## Quota discipline (important)
- Limits: **1 request/second, 500 requests/month.** One full pull = 50 calls.
- Each ticker's response is cached to `cache/` for **7 days**; re-runs within
  that window cost **0 calls**. The client enforces the 1/sec pace.
- That's ~10 full refreshes a month. Don't `--refresh` casually.

## Notes
- indianapi keys stocks by **company name**, not NSE ticker. The mapping lives in
  `config.NIFTY_50` (ticker -> name). If a name resolves to the wrong company on
  first run, fix that one line.
- All figures are as the API reports them (₹ crore). Revenue growth in Overview
  is computed FY-over-FY from the income statement and matches the API's own
  growth metric.

## Files
- `config.py` — NIFTY 50 name map, API URL, rate limit, paths
- `client.py` — API client (env-var key, 1/sec, 7-day cache, budget counter)
- `parse.py` — JSON -> snapshot / statements / metrics / shareholding
- `extract.py` — fetch all 50 -> Excel + combined dataset
- `app.py` — Streamlit viewer (read-only)


## Analysis & shortlisting (new — runs on cached data, 0 API calls)
`analysis.py` evaluates every stock across its FULL annual history (>=5 years),
never a single year. A weak latest year reads as a dip in a trend, not a verdict.

Two new Excel tabs:
- **Analysis** — one row/stock: revenue/NI/EPS CAGR, margin trends, avg ROE/ROCE
  with consistency counts (e.g. "ROE>=15% in 6/7 yrs"), Debt/Equity & trend,
  interest cover, FCF-positive years, cash conversion, Piotroski F (0-9),
  Altman Z' zone, red/green flag counts, and an `investigate` flag
  (>=5 yrs of data AND no severe red flags).
- **Flags** — every red/green flag per stock with a plain-English note
  (weak cash conversion, low/strong ROCE, margin direction, rising leverage,
  thin interest cover, FCF reliability, growth, Altman distress, net cash, ...).

Forensic scores (Altman Z', Piotroski F) and bank-inapplicable checks are
skipped/limited for financials (detected from industry).

In the **app**: a **Screener** tab lets you filter on your own rules (min
revenue CAGR, min avg ROCE, max D/E, min Piotroski, FCF-every-year, no red
flags, investigate-only) and download the shortlist; the **Stock detail** tab
shows each name's red/green flags and a by-year ratio table.
