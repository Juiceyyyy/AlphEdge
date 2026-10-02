# SPDX-FileCopyrightText: 2026 Joshua Menezes and AlphEdge contributors
# SPDX-License-Identifier: MIT
"""CLI: run the cross-sectional momentum rotation backtest."""
from __future__ import annotations
import argparse
import json
from pathlib import Path

from alpha_strategy.config import StrategyConfig, load_env
from alpha_strategy.logging_setup import setup_logging
from alpha_strategy.backtest_momentum import (
    run_momentum_backtest, MomentumConfig, _resolve_momentum_cfg,
)


def main() -> int:
    ap = argparse.ArgumentParser(description="Cross-sectional momentum backtest")
    ap.add_argument("--config", default="config.yaml")
    ap.add_argument("--years", type=int, default=None)
    ap.add_argument("--top-n", type=int, default=None,
                    help="ADTV universe size (overrides config)")
    ap.add_argument("--n-hold", type=int, default=None,
                    help="Number of stocks held (overrides config)")
    ap.add_argument("--out", default=None, help="Optional output JSON path")
    args = ap.parse_args()

    load_env()
    cfg = StrategyConfig.from_yaml(args.config) if Path(args.config).exists() else StrategyConfig()
    cfg.ensure_dirs()
    setup_logging(cfg.log_dir)

    mc = _resolve_momentum_cfg(cfg)
    if args.n_hold is not None:
        mc.n_hold = args.n_hold

    res = run_momentum_backtest(cfg, years=args.years, top_n=args.top_n, mc=mc)
    kpis = res.kpis()

    print()
    print("=" * 78)
    print("  Cross-Sectional Momentum Rotation - Backtest")
    print("=" * 78)
    print(f"  rebalance={mc.rebalance_freq}  n_hold={mc.n_hold}  "
          f"weighting={mc.weighting}  trend_filter={mc.use_trend_filter}")
    print(f"  momentum: w_short={mc.weight_short}*r{mc.lookback_short} + "
          f"w_long={mc.weight_long}*r{mc.lookback_long}, skip={mc.momentum_skip}")
    print()
    for k, v in kpis.items():
        if isinstance(v, float):
            print(f"  {k:30s} {v:>16,.3f}")
        else:
            print(f"  {k:30s} {v}")

    yr = res.yearly_returns()
    if not yr.empty:
        print("\nYearly returns:")
        print(yr.to_string(index=False, float_format="%.2f"))

    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump({
                "kpis": kpis,
                "yearly": yr.to_dict(orient="records") if not yr.empty else [],
                "config_used": res.config,
            }, f, indent=2, default=str)
        print(f"\nSaved JSON: {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

