"""Command line research workflows. Nothing here can submit a live order."""
from __future__ import annotations

import argparse
from datetime import date, timedelta
import json
from pathlib import Path
import sys

import numpy as np

from .config import INTERVAL_SECONDS, load_settings
from .data import Bars, audit, fetch_binance, json_write, read_bars, resample, timestamp, write_bars
from .experiment import backtest, make_freeze
from .ledger import Ledger, code_hash, utc_now
from .stats import simulate_evidence
from .publication import freeze_study, run_study
from .venues import fetch_bitstamp
from .market_study import freeze_market, run_market


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Auditable BTC spot trend research; no live exchange orders")
    commands = parser.add_subparsers(dest="command")
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--config", type=Path, default=Path("configs/research/btc-trend.toml"))
    common.add_argument("--ledger", type=Path, default=Path("runs/research.sqlite"))
    common.add_argument("--interval", choices=INTERVAL_SECONDS, help="Preserve indicator clock durations at this robustness interval")
    fetch = commands.add_parser("fetch", parents=[common], help="Download and SHA-256-verify public Binance archives")
    fetch.add_argument("--start", type=date.fromisoformat)
    fetch.add_argument("--end", type=date.fromisoformat)
    fetch.add_argument("--output", type=Path, required=True)
    fetch.add_argument("--cache", type=Path, default=Path("data/raw"))
    fetch.add_argument("--allow-gaps", action="store_true", help="Save audited data with disclosed gaps; no filling")
    fetch.add_argument("--quarantine-invalid", action="store_true", help="Exclude malformed/zero-volume rows with raw row hashes and reasons; never repair prices")
    secondary = commands.add_parser("fetch-bitstamp", parents=[common], help="Acquire secondary BTC/USD spot history with explicit venue/quote differences")
    secondary.add_argument("--start", type=date.fromisoformat)
    secondary.add_argument("--end", type=date.fromisoformat)
    secondary.add_argument("--output", type=Path, required=True)
    secondary.add_argument("--cache", type=Path, default=Path("data/raw/bitstamp"))
    secondary.add_argument("--allow-gaps", action="store_true")
    secondary.add_argument("--quarantine-invalid", action="store_true")
    check = commands.add_parser("audit", parents=[common], help="Validate normalized candles and report gaps")
    check.add_argument("--data", type=Path, required=True)
    check.add_argument("--allow-gaps", action="store_true")
    check.add_argument("--output", type=Path)
    demo = commands.add_parser("demo-data", parents=[common], help="Create a labeled deterministic synthetic fixture")
    demo.add_argument("--output", type=Path, required=True)
    demo.add_argument("--end", type=date.fromisoformat)
    demo.add_argument("--seed", type=int, default=7)
    aggregate = commands.add_parser("resample", parents=[common], help="Aggregate complete UTC candles; never interpolate")
    aggregate.add_argument("--data", type=Path, required=True)
    aggregate.add_argument("--to", choices=INTERVAL_SECONDS, required=True)
    aggregate.add_argument("--output", type=Path, required=True)
    run = commands.add_parser("run", parents=[common], help="Backtest prespecified policies and cost scenarios")
    run.add_argument("--data", type=Path, required=True)
    run.add_argument("--phase", choices=["development", "selection", "reserved"], default="development")
    run.add_argument("--output-root", type=Path, default=Path("runs"))
    run.add_argument("--allow-gaps", action="store_true", help="Carry holdings, cancel gap-crossing orders, reset features and pause selection")
    run.add_argument("--freeze", type=Path)
    run.add_argument("--acknowledge-retrospective", action="store_true")
    run.add_argument("--block-length", type=int, default=180)
    run.add_argument("--bootstrap-draws", type=int, default=1000)
    run.add_argument("--seed", type=int, default=7)
    run.add_argument("--no-plots", action="store_true")
    freeze = commands.add_parser("freeze", parents=[common], help="Pin a previously evaluated selection protocol before reserved use")
    freeze.add_argument("--data", type=Path, required=True)
    freeze.add_argument("--output", type=Path, required=True)
    freeze.add_argument("--minimum-annual-log-improvement", type=float, default=.02)
    evidence = commands.add_parser("evidence", parents=[common], help="Known-null sequential-evidence simulation; not a BTC guarantee")
    evidence.add_argument("--worlds", type=int, default=2000)
    evidence.add_argument("--steps", type=int, default=500)
    evidence.add_argument("--hypotheses", type=int, default=20)
    evidence.add_argument("--seed", type=int, default=7)
    evidence.add_argument("--alpha", type=float, default=.05)
    evidence.add_argument("--output", type=Path, required=True)
    study = commands.add_parser("publication-sim", parents=[common], help="Registered paired-cost study; smoke runs are labeled separately")
    study.add_argument("--spec", type=Path, default=Path("configs/research/publication-study-v1.json"))
    study.add_argument("--output-root", type=Path, default=Path("runs/publication"))
    study.add_argument("--case", help="Run one prespecified case; every attempted case is logged")
    study.add_argument("--freeze", type=Path, help="Required for substantive study runs")
    study.add_argument("--smoke", action="store_true", help="128 worlds and 60 steps; does not count as a substantive study")
    publication_freeze = commands.add_parser("publication-freeze", parents=[common], help="Pin the reviewed simulation protocol, source, runtime and specification")
    publication_freeze.add_argument("--spec", type=Path, default=Path("configs/research/publication-study-v1.json"))
    publication_freeze.add_argument("--protocol", type=Path, default=Path("docs/publication/protocol-v1.md"))
    publication_freeze.add_argument("--output", type=Path, required=True)
    market_freeze = commands.add_parser("market-freeze", parents=[common], help="Freeze a reviewed retrospective publication market application")
    market_freeze.add_argument("--spec", type=Path, default=Path("configs/research/market-study-v1.json"))
    market_freeze.add_argument("--protocol", type=Path, default=Path("docs/publication/market-protocol-v1.md"))
    market_freeze.add_argument("--review", type=Path, default=Path("docs/publication/reviews/market-study-01.md"))
    market_freeze.add_argument("--output", type=Path, required=True)
    market = commands.add_parser("market-study", parents=[common], help="Run all frozen market comparisons without selecting winners")
    market.add_argument("--spec", type=Path, default=Path("configs/research/market-study-v1.json"))
    market.add_argument("--freeze", type=Path, required=True)
    market.add_argument("--output-root", type=Path, default=Path("runs/market"))
    market.add_argument("--acknowledge-retrospective", action="store_true")
    commands.add_parser("ledger", parents=[common], help="Show attempted commands, outcomes, failures, and reserved accesses")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command is None:
        parser.print_help()
        return 0
    identifier, ledger = None, None
    try:
        ledger = Ledger(args.ledger)
        identifier = ledger.start("command", {"argv": list(argv) if argv is not None else sys.argv[1:], "config": str(args.config), "requested_interval": args.interval})
        settings = load_settings(args.config)
        if args.interval:
            settings = settings.at_interval(args.interval)
        root = settings.source.parents[2]
        if not (root / "src/quant").is_dir():
            raise ValueError("Configuration must reside in this project's configs/research directory")
        with ledger.connect() as db:
            db.execute("UPDATE attempts SET config_hash=?,code_hash=? WHERE id=?", (settings.sha256, code_hash(root), identifier))
        if args.command == "fetch":
            result = fetch_binance(args.start or settings.dev_start, args.end or settings.dev_end, args.output, interval=settings.interval, cache=args.cache, allow_gaps=args.allow_gaps, quarantine_invalid=args.quarantine_invalid)
        elif args.command == "fetch-bitstamp":
            result = fetch_bitstamp(args.start or settings.dev_start, args.end or settings.dev_end, args.output, interval=settings.interval, cache=args.cache, allow_gaps=args.allow_gaps, quarantine_invalid=args.quarantine_invalid)
        elif args.command == "audit":
            bars = read_bars(args.data, interval=args.interval)
            result = {**audit(bars, allow_gaps=args.allow_gaps), "provenance": bars.provenance}
            if args.output:
                if args.output.exists():
                    raise ValueError("Audit output already exists")
                json_write(args.output, result)
        elif args.command == "demo-data":
            end = args.end or settings.selection_end
            times = np.arange(timestamp(settings.dev_start), timestamp(end + timedelta(days=1)), settings.seconds * 1000, dtype=np.int64)
            if len(times) < 2:
                raise ValueError("Synthetic range is empty")
            rng = np.random.default_rng(args.seed)
            phases = (np.arange(len(times)) // max(100, settings.annualization // 2)) % 4
            drifts = np.asarray([.0007, -.0005, 0., .0002])[phases] * settings.seconds / 14400
            increments = drifts + rng.normal(0, .009 * np.sqrt(settings.seconds / 14400), len(times))
            closes = 5000 * np.exp(np.cumsum(increments))
            opens = np.r_[5000., closes[:-1]]
            high = np.maximum(opens, closes) * (1 + rng.uniform(.001, .005, len(times)))
            low = np.minimum(opens, closes) * (1 - rng.uniform(.001, .005, len(times)))
            bars = Bars(times, np.column_stack([opens, high, low, closes, rng.uniform(100, 2000, len(times))]), times + settings.seconds * 1000 - 1, settings.interval, {})
            quality = audit(bars)
            write_bars(args.output, bars, {"provider": "synthetic", "symbol": settings.symbol, "instrument": "spot", "seed": args.seed, "created_at": utc_now(), "audit": quality})
            result = {"output": str(args.output), "provider": "synthetic", **quality}
        elif args.command == "resample":
            bars = read_bars(args.data, interval=args.interval)
            audit(bars)
            aggregate = resample(bars, args.to)
            result = audit(aggregate)
            write_bars(args.output, aggregate, {"provider": bars.provenance.get("provider", "unverified local input"), "symbol": settings.symbol, "instrument": "spot", "derivation": aggregate.provenance, "audit": result})
            result = {"output": str(args.output), **result}
        elif args.command == "run":
            result = backtest(settings, args.data, args.phase, args.output_root, ledger, root, allow_gaps=args.allow_gaps, freeze=args.freeze,
                              acknowledge_reserved=args.acknowledge_retrospective, block_length=args.block_length, draws=args.bootstrap_draws,
                              seed=args.seed, plots=not args.no_plots)
        elif args.command == "freeze":
            result = make_freeze(settings, args.data, args.output, ledger, root, minimum_improvement=args.minimum_annual_log_improvement)
        elif args.command == "evidence":
            if args.output.exists():
                raise ValueError("Evidence output already exists")
            result = simulate_evidence(worlds=args.worlds, steps=args.steps, hypotheses=args.hypotheses, seed=args.seed, alpha=args.alpha)
            json_write(args.output, {"created_at": utc_now(), "config_sha256": settings.sha256, "code_sha256": code_hash(root), "simulation": result})
        elif args.command == "publication-sim":
            result = run_study(args.spec, args.output_root, ledger, root, smoke=args.smoke, case_id=args.case, freeze=args.freeze)
        elif args.command == "publication-freeze":
            result = freeze_study(args.spec, args.protocol, args.output, ledger, root)
        elif args.command == "market-freeze":
            result = freeze_market(args.spec, args.protocol, args.review, args.output, ledger, root)
        elif args.command == "market-study":
            result = run_market(args.spec, args.freeze, args.output_root, ledger, root, acknowledge_retrospective=args.acknowledge_retrospective)
        else:
            result = ledger.rows()
        ledger.finish(identifier, "completed", {"output": str(getattr(args, "output", "")), "phase": getattr(args, "phase", "")})
        print(json.dumps(result, indent=2, allow_nan=False))
        return 0
    except (ValueError, OSError, KeyError, TypeError) as error:
        if identifier and ledger:
            ledger.finish(identifier, "failed", {"error": str(error)})
        print(f"quant: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
