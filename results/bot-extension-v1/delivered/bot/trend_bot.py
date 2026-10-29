#!/usr/bin/env python3
"""Paper-aligned BTC spot bot: deterministic replay and paper/testnet execution."""
from __future__ import annotations

import argparse
from datetime import date
import json
from pathlib import Path
import sys

from bot_core import HOME, load_csv, save_backtest, settings, signal, verify_paper_core


def parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description="BTC spot EMA research bot; the paper establishes no adaptive trading edge")
    ap.add_argument("mode", choices=["doctor", "signal", "backtest", "sim", "alpaca", "binance"])
    ap.add_argument("--data", type=Path, help="Audited complete OHLCV history; default follows the selected policy")
    ap.add_argument("--interval", choices=["4h", "1h", "1d"])
    ap.add_argument("--policy", choices=["fixed", "adaptive", "ensemble", "legacy_daily"], default="fixed")
    ap.add_argument("--cash", type=float, default=10_000.)
    ap.add_argument("--start", type=date.fromisoformat, default=date(2025, 1, 1))
    ap.add_argument("--end", type=date.fromisoformat, default=date(2026, 10, 20))
    ap.add_argument("--output", type=Path, help="New replay directory; refuses overwrites")
    ap.add_argument("--case-id", help="Controls deterministic bootstrap seed; label changed studies honestly")
    ap.add_argument("--draws", type=int, default=5000)
    ap.add_argument("--state", type=Path, help="Separate state per mode/account/policy")
    ap.add_argument("--once", action="store_true")
    ap.add_argument("--offline", action="store_true", help="Local simulation only; requires explicit --as-of-ms and --price")
    ap.add_argument("--as-of-ms", type=int, help="Offline simulated clock; never used for broker orders")
    ap.add_argument("--price", type=float, help="Offline simulated executable price")
    ap.add_argument("--max-execution-delay-seconds", type=int, default=120)
    ap.add_argument("--kill-file", type=Path, default=HOME / "STOP")
    ap.add_argument("--allow-quote-basis", action="store_true", help="Explicitly acknowledge Binance USDT signals versus Alpaca USD fills")
    return ap


def main(argv=None) -> int:
    args = parser().parse_args(argv)
    try:
        verified = verify_paper_core()
        interval = args.interval or ("1d" if args.policy == "legacy_daily" else "4h")
        if args.policy == "legacy_daily":
            if interval != "1d":
                raise ValueError("legacy_daily requires --interval 1d")
            from legacy_daily import settings as legacy_settings
            s = legacy_settings(args.cash)
        else:
            s = settings(interval, args.cash)
        args.data = args.data or HOME / ("data/btc-1d.csv" if args.policy == "legacy_daily" else "data/btc-4h.csv")
        args.case_id = args.case_id or ("legacy_daily_exploratory" if args.policy == "legacy_daily" else "binance_primary_4h")
        args.state = args.state or HOME / ("state/legacy-daily.sqlite" if args.policy == "legacy_daily" else "state/paper.sqlite")
        if args.mode == "doctor":
            print(json.dumps({**verified, "policy": args.policy, "instrument": "unlevered BTC spot",
                "paper_matches": args.policy != "legacy_daily", "data_exists": args.data.is_file(), "adaptive_edge_established": False,
                "execution": "local simulated or broker paper/testnet only; no production endpoint"}, indent=2))
            return 0
        if args.mode in ("sim", "binance", "alpaca"):
            from bot_runtime import run
            return run(args, s)
        if args.as_of_ms is not None or args.price is not None:
            raise ValueError("Artificial clocks/prices are allowed only with sim --offline")
        bars = load_csv(args.data, s)
        if args.mode == "signal":
            print(json.dumps(signal(bars, s, args.policy), indent=2))
            return 0
        if args.output is None:
            raise ValueError("Backtest requires --output with a new directory")
        evaluator = None
        if args.policy == "legacy_daily":
            from legacy_daily import backtest as evaluator
        report = save_backtest(args.output, bars, s, args.start, args.end, draws=args.draws, case_id=args.case_id, evaluator=evaluator)
        metrics = report["scenarios"]["25"]["metrics"]
        if args.policy == "legacy_daily":
            print(json.dumps({"output": str(args.output.resolve()), "legacy_daily": metrics["legacy_daily"],
                "daily_ema_control": metrics["paper_ema_daily_reference"], "conclusion": report["interpretation"]}, indent=2))
            return 0
        print(json.dumps({"output": str(args.output.resolve()), "fixed": metrics["fixed"],
            "adaptive": metrics["adaptive"], "conclusion": report["interpretation"]}, indent=2))
        return 0
    except (ValueError, OSError, RuntimeError) as error:
        print(f"{type(error).__name__}: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
