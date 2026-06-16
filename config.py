"""
config.py — settings for the indianapi.in NIFTY 50 extractor.

API: https://stock.indianapi.in/stock  (keyed by company NAME, not NSE ticker).
Auth: set your key as an env var  ->  INDIANAPI_KEY
Limits: 1 request/second, 500 requests/MONTH. One full NIFTY 50 pull = 50 calls,
so responses are cached on disk and the app NEVER calls the API (read-only).
"""

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CACHE_DIR = ROOT / "cache"          # one cached JSON per ticker
OUTPUT_DIR = ROOT / "output"        # Excel + combined dataset

# --- API ---
API_URL = os.getenv("INDIANAPI_URL", "https://stock.indianapi.in/stock")
API_KEY_ENV = "INDIANAPI_KEY"
API_KEY_HEADER = "X-Api-Key"
RATE_LIMIT_SECONDS = 1.2            # >= 1/sec, with margin
CACHE_TTL_DAYS = 36500             # ~100 years = permanent; use --refresh to update
MONTHLY_BUDGET = 500               # for the on-screen budget warning

# --- NIFTY 50: NSE ticker -> name to search on indianapi ---
# (If a name resolves to the wrong company on your first run, edit it here.)
NIFTY_50 = {
 "RELIANCE": "Reliance Industries",
 #"TCS": "Tata Consultancy Services",
 "HDFCBANK": "HDFC Bank",
 "ICICIBANK": "ICICI Bank",
# "INFY": "Infosys",
# "HINDUNILVR": "Hindustan Unilever",
# "ITC": "ITC",
# "SBIN": "State Bank of India",
 "BHARTIARTL": "Bharti Airtel",
# "KOTAKBANK": "Kotak Mahindra Bank",
# "LT": "Larsen & Toubro",
# "BAJFINANCE": "Bajaj Finance",
# "AXISBANK": "Axis Bank",
 "ASIANPAINT": "Asian Paints",
# "MARUTI": "Maruti Suzuki India",
# "HCLTECH": "HCL Technologies",
 #"SUNPHARMA": "Sun Pharmaceutical Industries",
"TITAN": "Titan Company",
 "ULTRACEMCO": "UltraTech Cement",
# "WIPRO": "Wipro",
# "NESTLEIND": "Nestle India",
# "ONGC": "Oil & Natural Gas Corporation",
# "NTPC": "NTPC",
# "POWERGRID": "Power Grid Corporation of India",
# "TATAMOTORS": "Tata Motors",
# "TATASTEEL": "Tata Steel",
# "JSWSTEEL": "JSW Steel",
# "ADANIENT": "Adani Enterprises",
# "ADANIPORTS": "Adani Ports and Special Economic Zone",
 "COALINDIA": "Coal India",
# "BAJAJFINSV": "Bajaj Finserv",
# "HDFCLIFE": "HDFC Life Insurance Company",
# "SBILIFE": "SBI Life Insurance Company",
# "TECHM": "Tech Mahindra",
# "GRASIM": "Grasim Industries",
# "HINDALCO": "Hindalco Industries",
 "DRREDDY": "Dr. Reddy's Laboratories",
# "CIPLA": "Cipla",
# "BRITANNIA": "Britannia Industries",
# "EICHERMOT": "Eicher Motors",
# "HEROMOTOCO": "Hero MotoCorp",
# "BAJAJ-AUTO": "Bajaj Auto",
# "INDUSINDBK": "IndusInd Bank",
# "M&M": "Mahindra & Mahindra",
# "APOLLOHOSP": "Apollo Hospitals Enterprise",
# "BPCL": "Bharat Petroleum Corporation",
# "TATACONSUM": "Tata Consumer Products",
# "LTIM": "LTIMindtree",
# "SHRIRAMFIN": "Shriram Finance",
# "DIVISLAB": "Divi's Laboratories",
}
