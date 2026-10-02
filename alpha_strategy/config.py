# SPDX-FileCopyrightText: 2026 Joshua Menezes and AlphEdge contributors
# SPDX-License-Identifier: MIT
"""Configuration loader for the momentum strategy."""
from __future__ import annotations
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any
import os
import yaml
from dotenv import load_dotenv


@dataclass
class StrategyConfig:
    # Capital
    starting_capital: float = 1_000_000.0

    # Universe
    index_universe: str = "combined"           # combined | nifty100 | nifty200
    top_n_by_adtv: int = 250
    adtv_lookback_days: int = 63
    universe_refresh_days: int = 30
    data_lookback_years: int = 16
    benchmark_ticker: str = "^NSEI"

    # Momentum signal
    n_hold: int = 10
    rebalance_freq: str = "M"
    lookback_short: int = 126
    lookback_long: int = 252
    momentum_skip: int = 21
    weight_short: float = 0.3
    weight_long: float = 0.7
    weighting: str = "inverse_vol"
    vol_window: int = 63

    # Filters
    require_above_ma: bool = True
    long_ma_window: int = 200
    min_momentum: float = 0.0
    use_trend_filter: bool = True
    trend_filter_window: int = 200
    target_total_exposure: float = 1.0

    # Execution costs
    slippage_bps: float = 5.0
    commission_bps: float = 3.0

    # Paths
    data_cache_dir: str = "cache/ohlcv"
    state_dir: str = "state"
    log_dir: str = "logs"

    @classmethod
    def from_yaml(cls, path: str | Path) -> "StrategyConfig":
        path = Path(path)
        if not path.exists():
            return cls()
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        valid = {f.name for f in cls.__dataclass_fields__.values()}
        clean = {k: v for k, v in data.items() if k in valid}
        return cls(**clean)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def ensure_dirs(self) -> None:
        for d in (self.data_cache_dir, self.state_dir, self.log_dir):
            Path(d).mkdir(parents=True, exist_ok=True)


def load_env(env_path: str | Path = ".env") -> None:
    p = Path(env_path)
    if p.exists():
        load_dotenv(p, override=False)


def get_env(key: str, default: str | None = None) -> str | None:
    return os.environ.get(key, default)

