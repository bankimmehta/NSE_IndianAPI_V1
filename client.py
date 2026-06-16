"""
client.py — indianapi.in client with logging, validation, and quota guards.

  * key from INDIANAPI_KEY env var (never hardcoded)
  * >= 1 request/second enforced
  * VALID responses cached on disk; INVALID/empty responses are NOT cached
    (so they retry next run instead of poisoning the dataset)
  * every request/response logged (status, size, timing, and the body snippet
    when something is empty/wrong) so you can see exactly what the API returned
"""

import os
import time
import json
import logging

import requests

import config

config.CACHE_DIR.mkdir(parents=True, exist_ok=True)
config.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

log = logging.getLogger("indianapi")

_last_call = [0.0]
_n_calls = [0]


def configure_logging(logfile=None, level=logging.INFO):
    """Console + optional file logging. Call once from the entry point."""
    log.setLevel(level)
    log.handlers.clear()
    cfmt = logging.Formatter("%(asctime)s %(levelname)-7s %(message)s", "%H:%M:%S")
    ch = logging.StreamHandler()
    ch.setFormatter(cfmt)
    log.addHandler(ch)
    if logfile:
        fh = logging.FileHandler(logfile, encoding="utf-8")
        fh.setFormatter(logging.Formatter("%(asctime)s %(levelname)-7s %(message)s"))
        log.addHandler(fh)


def api_key() -> str:
    k = os.getenv(config.API_KEY_ENV)
    if not k:
        raise RuntimeError(
            f"Set your API key first:  export {config.API_KEY_ENV}=your-key")
    return k


def _cache_path(ticker):
    return config.CACHE_DIR / f"{ticker.replace('&', 'AND')}.json"


def _fresh(path) -> bool:
    # Cache is permanent: a cached file is always reused unless --refresh is
    # passed. Fundamentals only change quarterly, so re-fetching would just
    # burn requests on identical numbers. Refresh a stock after its results:
    #   python extract.py --only TICKER --refresh
    return path.exists()


def calls_made() -> int:
    return _n_calls[0]


def is_valid(data) -> bool:
    """A usable stock payload has a company name and at least one financial period."""
    return (isinstance(data, dict)
            and bool(data.get("companyName"))
            and bool(data.get("financials")))


def _why_empty(data) -> str:
    """Best-effort explanation of an empty/invalid response, for the log."""
    if not isinstance(data, dict):
        return f"response is {type(data).__name__}, not an object"
    msg = data.get("message") or data.get("error") or data.get("detail") or data.get("status")
    keys = list(data.keys())
    bits = [f"keys={keys}"]
    if msg:
        bits.append(f"message={msg!r}")
    if "companyName" in data and not data.get("companyName"):
        bits.append("companyName is blank")
    if "financials" in data and not data.get("financials"):
        bits.append("financials is empty")
    return "; ".join(bits)


def get_stock(ticker: str, name: str, refresh: bool = False):
    """Return raw stock JSON, or None if the API gave nothing usable.

    Valid responses are cached. Invalid/empty ones are logged (with the body)
    and NOT cached, so they retry next run.
    """
    cache = _cache_path(ticker)
    if not refresh and _fresh(cache):
        with open(cache, encoding="utf-8") as f:
            data = json.load(f)
        log.info("%-12s CACHE hit", ticker)
        return data

    dt = time.time() - _last_call[0]
    if dt < config.RATE_LIMIT_SECONDS:
        time.sleep(config.RATE_LIMIT_SECONDS - dt)

    log.info("%-12s GET %s  name=%r", ticker, config.API_URL, name)
    t0 = time.time()
    try:
        resp = requests.get(config.API_URL, params={"name": name},
                            headers={config.API_KEY_HEADER: api_key()}, timeout=30)
    except requests.RequestException as e:
        log.error("%-12s NETWORK ERROR: %s", ticker, e)
        raise
    _last_call[0] = time.time()
    _n_calls[0] += 1
    elapsed = time.time() - t0
    log.info("%-12s HTTP %s in %.1fs (%d bytes)", ticker, resp.status_code,
             elapsed, len(resp.content))

    if resp.status_code != 200:
        log.error("%-12s NON-200. body: %s", ticker, resp.text[:600])
        return None

    try:
        data = resp.json()
    except ValueError:
        log.error("%-12s response was not JSON. body: %s", ticker, resp.text[:600])
        return None

    if not is_valid(data):
        log.warning("%-12s EMPTY/INVALID -- %s", ticker, _why_empty(data))
        log.warning("%-12s body snippet: %s", ticker, json.dumps(data)[:600])
        return None        # do NOT cache; will retry next run

    with open(cache, "w", encoding="utf-8") as f:
        json.dump(data, f)
    log.info("%-12s OK  -> %s", ticker, data.get("companyName"))
    return data
