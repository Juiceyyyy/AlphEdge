"""yfinance OHLCV downloader with parquet cache + eviction."""
from __future__ import annotations
from datetime import datetime, timedelta
from pathlib import Path
from typing import Iterable
import logging
import time

import pandas as pd

log = logging.getLogger("alpha_strategy.data")

# Silence yfinance's chatty stderr (decoy ticker probes, "possibly delisted" warnings)
for _name in ("yfinance", "yfinance.utils", "yfinance.scrapers", "yfinance.data"):
    _l = logging.getLogger(_name)
    _l.setLevel(logging.CRITICAL)
    _l.propagate = False

_EVICT_MARKER = ".last_evict"


def _safe_yf_download(tickers: list[str], start: str, end: str,
                      max_retries: int = 2) -> pd.DataFrame | None:
    """Wrapper around yfinance with retries."""
    try:
        import yfinance as yf
    except ImportError:
        log.error("yfinance not installed")
        return None
    last_err: Exception | None = None
    for attempt in range(max_retries + 1):
        try:
            df = yf.download(
                tickers=tickers,
                start=start,
                end=end,
                progress=False,
                auto_adjust=False,
                threads=True,
                group_by="ticker",
            )
            if df is not None and not df.empty:
                return df
        except Exception as e:
            last_err = e
            log.warning("yf.download attempt %d failed: %s", attempt + 1, e)
            time.sleep(1.5 * (attempt + 1))
    if last_err:
        log.warning("yf.download exhausted retries: %s", last_err)
    return None


def _parquet_path(symbol: str, cache_dir: Path) -> Path:
    safe = symbol.replace("/", "_").replace("\\", "_").replace("^", "_idx_")
    return cache_dir / f"{safe}.parquet"


def _load_cached(symbol: str, cache_dir: Path) -> pd.DataFrame | None:
    p = _parquet_path(symbol, cache_dir)
    if not p.exists():
        return None
    try:
        df = pd.read_parquet(p)
        if df is None or df.empty:
            return None
        if not isinstance(df.index, pd.DatetimeIndex):
            df.index = pd.to_datetime(df.index)
        return df
    except Exception as e:
        log.warning("cache read %s failed: %s", symbol, e)
        return None


def _save_cached(symbol: str, df: pd.DataFrame, cache_dir: Path) -> None:
    cache_dir.mkdir(parents=True, exist_ok=True)
    p = _parquet_path(symbol, cache_dir)
    try:
        df.to_parquet(p)
    except Exception as e:
        log.warning("cache write %s failed: %s", symbol, e)


def _normalize_ohlcv(df: pd.DataFrame) -> pd.DataFrame:
    """Ensure consistent OHLCV columns."""
    rename = {}
    for c in df.columns:
        cl = str(c).strip().lower()
        if cl in ("open",): rename[c] = "Open"
        elif cl in ("high",): rename[c] = "High"
        elif cl in ("low",): rename[c] = "Low"
        elif cl in ("close",): rename[c] = "Close"
        elif cl in ("adj close", "adjclose"): rename[c] = "AdjClose"
        elif cl in ("volume",): rename[c] = "Volume"
    df = df.rename(columns=rename)
    keep = [c for c in ("Open", "High", "Low", "Close", "AdjClose", "Volume") if c in df.columns]
    df = df[keep].copy()
    if not isinstance(df.index, pd.DatetimeIndex):
        df.index = pd.to_datetime(df.index)
    df = df.sort_index()
    df = df[~df.index.duplicated(keep="last")]
    df = df.dropna(subset=[c for c in ("Open", "High", "Low", "Close") if c in df.columns],
                   how="any")
    return df


def download_history(symbols: list[str],
                     years: int = 16,
                     cache_dir: str | Path = "cache/ohlcv",
                     batch_size: int = 25,
                     refresh_days: int = 1) -> dict[str, pd.DataFrame]:
    """Download OHLCV for symbols. Uses cache where fresh; refreshes recent bars only.

    Returns dict yahoo_symbol -> DataFrame.
    """
    cache_dir = Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)

    today = datetime.now().date()
    full_start = (today - timedelta(days=int(years * 365.25) + 5)).isoformat()
    end = (today + timedelta(days=1)).isoformat()

    out: dict[str, pd.DataFrame] = {}
    needs_full: list[str] = []
    needs_incremental: list[tuple[str, str]] = []  # (sym, start)

    for s in symbols:
        cached = _load_cached(s, cache_dir)
        if cached is None or cached.empty:
            needs_full.append(s)
            continue
        last = cached.index.max().date()
        if (today - last).days <= refresh_days:
            out[s] = cached
            continue
        inc_start = (last - timedelta(days=5)).isoformat()
        needs_incremental.append((s, inc_start))
        out[s] = cached  # populate now; will be merged below

    # Full downloads in batches
    for i in range(0, len(needs_full), batch_size):
        batch = needs_full[i:i + batch_size]
        df = _safe_yf_download(batch, start=full_start, end=end)
        if df is None:
            continue
        for sym in batch:
            try:
                if isinstance(df.columns, pd.MultiIndex):
                    if sym in df.columns.get_level_values(0):
                        sub = df[sym].dropna(how="all")
                    else:
                        continue
                else:
                    sub = df.dropna(how="all")
                sub = _normalize_ohlcv(sub)
                if sub.empty:
                    continue
                out[sym] = sub
                _save_cached(sym, sub, cache_dir)
            except Exception as e:
                log.warning("split download %s: %s", sym, e)

    # Incremental refreshes
    if needs_incremental:
        # group by start date for fewer downloads
        groups: dict[str, list[str]] = {}
        for sym, st in needs_incremental:
            groups.setdefault(st, []).append(sym)
        for st, syms in groups.items():
            for i in range(0, len(syms), batch_size):
                batch = syms[i:i + batch_size]
                df = _safe_yf_download(batch, start=st, end=end)
                if df is None:
                    continue
                for sym in batch:
                    try:
                        if isinstance(df.columns, pd.MultiIndex):
                            if sym not in df.columns.get_level_values(0):
                                continue
                            sub = df[sym].dropna(how="all")
                        else:
                            sub = df.dropna(how="all")
                        sub = _normalize_ohlcv(sub)
                        if sub.empty:
                            continue
                        merged = pd.concat([out.get(sym), sub])
                        merged = merged[~merged.index.duplicated(keep="last")].sort_index()
                        out[sym] = merged
                        _save_cached(sym, merged, cache_dir)
                    except Exception as e:
                        log.warning("incremental merge %s: %s", sym, e)

    return out


def evict_stale_cache(cache_dir: str | Path = "cache/ohlcv",
                      universe_symbols: Iterable[str] | None = None,
                      max_age_days: int = 400,
                      throttle_days: int = 30) -> int:
    """Delete parquet files older than max_age_days OR not in current universe.
    Throttled to run at most once every `throttle_days`. Returns number deleted.
    """
    cache_dir = Path(cache_dir)
    if not cache_dir.exists():
        return 0
    marker = cache_dir / _EVICT_MARKER
    if marker.exists():
        try:
            age = datetime.now() - datetime.fromtimestamp(marker.stat().st_mtime)
            if age < timedelta(days=throttle_days):
                return 0
        except Exception:
            pass

    universe_set = {str(s) for s in universe_symbols} if universe_symbols else None
    cutoff = datetime.now() - timedelta(days=max_age_days)
    n = 0
    for p in cache_dir.glob("*.parquet"):
        try:
            sym = p.stem.replace("_idx_", "^")
            mtime = datetime.fromtimestamp(p.stat().st_mtime)
            stale_age = mtime < cutoff
            stale_off = (universe_set is not None) and (sym not in universe_set) \
                        and not sym.startswith("^") and sym != "_idx_NSEI"
            if stale_age or stale_off:
                p.unlink()
                n += 1
        except Exception:
            continue
    try:
        marker.touch()
    except Exception:
        pass
    if n:
        log.info("Evicted %d stale cache files", n)
    return n

