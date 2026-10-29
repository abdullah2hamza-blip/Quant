"""Acquire auditable native Binance spot history without silently filling gaps."""
from lab import HOME
import argparse
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from paper_engine.data import fetch_binance

def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", type=date.fromisoformat, default=date(2017, 9, 1))
    parser.add_argument("--end", type=date.fromisoformat, default=datetime.now(timezone.utc).date() - timedelta(days=1))
    parser.add_argument("--output", type=Path)
    parser.add_argument("--cache", type=Path, default=HOME / "data/raw")
    parser.add_argument("--interval", choices=["4h", "1d"], default="4h")
    args = parser.parse_args(argv)
    args.output = args.output or HOME / f"data/btc-{args.interval}.csv"
    if args.end >= datetime.now(timezone.utc).date():
        parser.error("End must precede the current UTC day")
    fetch_binance(args.start, args.end, args.output, interval=args.interval, cache=args.cache, allow_gaps=True, quarantine_invalid=True)
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
