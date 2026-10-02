# SPDX-FileCopyrightText: 2026 Joshua Menezes and AlphEdge contributors
# SPDX-License-Identifier: MIT
"""Dynamic NSE universe selection (Nifty 200 + Next 50 + Midcap 150) ranked by ADTV.

Fetches current index constituents from NSE archives, caches CSVs locally for 30 days
(rebalances are quarterly), computes 3-month ADTV, returns top-N tickers.
Falls back to a hardcoded list if NSE archives are unreachable.
"""
from __future__ import annotations
from datetime import datetime, timedelta
from pathlib import Path
from typing import Iterable
import io
import logging

import pandas as pd
import requests

log = logging.getLogger("alpha_strategy.universe")

# NSE Archives URLs (industry-standard public CSVs)
NSE_URLS = {
    "nifty200": "https://archives.nseindia.com/content/indices/ind_nifty200list.csv",
    "niftynext50": "https://archives.nseindia.com/content/indices/ind_niftynext50list.csv",
    "niftymidcap150": "https://archives.nseindia.com/content/indices/ind_niftymidcap150list.csv",
    "nifty100": "https://archives.nseindia.com/content/indices/ind_nifty100list.csv",
    "nifty50": "https://archives.nseindia.com/content/indices/ind_nifty50list.csv",
}

# Resilient hardcoded fallback (top liquid Indian large/mid caps as of late 2024)
FALLBACK_TICKERS = [
    "RELIANCE", "TCS", "HDFCBANK", "ICICIBANK", "INFY", "BHARTIARTL", "SBIN",
    "LT", "HINDUNILVR", "ITC", "BAJFINANCE", "KOTAKBANK", "AXISBANK", "MARUTI",
    "M&M", "SUNPHARMA", "NTPC", "ONGC", "HCLTECH", "TITAN", "ULTRACEMCO",
    "POWERGRID", "BAJAJFINSV", "WIPRO", "ADANIPORTS", "NESTLEIND", "JSWSTEEL",
    "TATASTEEL", "TATAMOTORS", "ASIANPAINT", "COALINDIA", "HINDALCO", "BPCL",
    "GRASIM", "SBILIFE", "HDFCLIFE", "DRREDDY", "EICHERMOT", "BRITANNIA",
    "TECHM", "DIVISLAB", "CIPLA", "INDUSINDBK", "TATACONSUM", "BAJAJ-AUTO",
    "APOLLOHOSP", "HEROMOTOCO", "UPL", "SHREECEM", "BSE", "IRFC", "TRENT",
    "PAYTM", "MAZDOCK", "SUZLON", "ZOMATO", "DMART", "DLF", "GODREJCP", "PIDILITIND",
    "AMBUJACEM", "ADANIENT", "VEDL", "GAIL", "IOC", "TATAPOWER", "BANKBARODA",
    "PNB", "CANBK", "BEL", "HAL", "BHEL", "PFC", "RECLTD", "INDIGO", "MOTHERSON",
    "BALKRISIND", "JINDALSTEL", "MCDOWELL-N", "MCX", "MUTHOOTFIN", "CHOLAFIN",
    "ASHOKLEY", "BIOCON", "LICI", "IRCTC", "NATIONALUM", "ABFRL", "VOLTAS",
    "SIEMENS", "ABB", "PAGEIND", "BERGEPAINT", "MARICO", "DABUR", "COLPAL",
    "HAVELLS", "CROMPTON", "PEL", "AUROPHARMA", "LUPIN", "TORNTPHARM",
    "CONCOR", "PETRONET", "GMRINFRA", "INDIANB", "IDFCFIRSTB", "FEDERALBNK",
    "RBLBANK", "BANDHANBNK", "AUBANK", "IDEA", "POLICYBZR", "NAUKRI",
    "DEEPAKNTR", "ALKEM", "GLENMARK", "JUBLFOOD", "ESCORTS",
    "NMDC", "SAIL", "MOIL", "JINDALPOLY", "APLAPOLLO", "ASTRAL", "POLYCAB",
    "KEC", "HONAUT", "IOC",
]


def _http_get(url: str, timeout: float = 15.0) -> bytes | None:
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                      "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36",
        "Accept": "text/csv,application/csv,*/*",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": "https://www.nseindia.com/",
    }
    try:
        r = requests.get(url, headers=headers, timeout=timeout)
        if r.status_code == 200 and len(r.content) > 100:
            return r.content
        log.warning("NSE fetch %s -> HTTP %s", url, r.status_code)
    except Exception as e:
        log.warning("NSE fetch %s failed: %s", url, e)
    return None


def _cache_path(name: str, cache_dir: Path) -> Path:
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir / f"nse_{name}.csv"


def _is_fresh(p: Path, max_age_days: int) -> bool:
    if not p.exists():
        return False
    age = datetime.now() - datetime.fromtimestamp(p.stat().st_mtime)
    return age < timedelta(days=max_age_days)


def fetch_index_csv(name: str, cache_dir: Path = Path("cache"),
                    max_age_days: int = 30) -> pd.DataFrame | None:
    """Returns DataFrame with at least a 'Symbol' column, or None on failure."""
    if name not in NSE_URLS:
        return None
    p = _cache_path(name, cache_dir)
    raw: bytes | None = None
    if _is_fresh(p, max_age_days):
        try:
            raw = p.read_bytes()
        except Exception:
            raw = None
    if raw is None:
        raw = _http_get(NSE_URLS[name])
        if raw is not None:
            try:
                p.write_bytes(raw)
            except Exception:
                pass
    if raw is None:
        return None
    try:
        df = pd.read_csv(io.BytesIO(raw))
    except Exception as e:
        log.warning("parse %s csv failed: %s", name, e)
        return None
    # NSE CSVs use 'Symbol' column
    cols = {c.lower(): c for c in df.columns}
    sym = cols.get("symbol")
    if not sym:
        return None
    df = df.rename(columns={sym: "Symbol"})
    df["Symbol"] = df["Symbol"].astype(str).str.strip().str.upper()
    return df


def get_constituent_universe(index_universe: str = "combined",
                             cache_dir: Path = Path("cache"),
                             max_age_days: int = 30) -> list[str]:
    """Fetches union of selected NSE index constituents."""
    if index_universe == "nifty50":
        sources = ["nifty50"]
    elif index_universe == "nifty100":
        sources = ["nifty100"]
    elif index_universe == "nifty200":
        sources = ["nifty200"]
    elif index_universe == "combined":
        sources = ["nifty200", "niftynext50", "niftymidcap150"]
    else:
        sources = ["nifty200"]

    tickers: set[str] = set()
    for s in sources:
        df = fetch_index_csv(s, cache_dir=cache_dir, max_age_days=max_age_days)
        if df is not None and not df.empty:
            tickers.update(df["Symbol"].tolist())

    if not tickers:
        log.warning("All NSE fetches failed; using FALLBACK_TICKERS (%d)",
                    len(FALLBACK_TICKERS))
        tickers = set(FALLBACK_TICKERS)

    # Drop weird symbols
    tickers = {t for t in tickers if t and t.replace("&", "").replace("-", "").isalnum()}
    return sorted(tickers)


def to_yahoo_symbol(nse_symbol: str) -> str:
    """NSE 'RELIANCE' -> Yahoo 'RELIANCE.NS'."""
    s = nse_symbol.strip().upper()
    if s.endswith(".NS"):
        return s
    return f"{s}.NS"


def from_yahoo_symbol(yahoo: str) -> str:
    return yahoo.replace(".NS", "").upper()


def rank_by_adtv(price_data: dict[str, pd.DataFrame],
                 lookback_days: int = 63,
                 top_n: int = 100) -> list[str]:
    """Pick top-N tickers by 3-month average daily traded value (close * volume).

    price_data: dict ticker -> DataFrame with 'Close','Volume' (yahoo symbols).
    Returns Yahoo symbols.
    """
    rows: list[tuple[str, float]] = []
    for sym, df in price_data.items():
        if df is None or df.empty:
            continue
        if not {"Close", "Volume"}.issubset(df.columns):
            continue
        sub = df.tail(lookback_days)
        if len(sub) < 20:
            continue
        adtv = float((sub["Close"] * sub["Volume"]).mean())
        if adtv > 0:
            rows.append((sym, adtv))
    rows.sort(key=lambda x: x[1], reverse=True)
    return [s for s, _ in rows[:top_n]]

