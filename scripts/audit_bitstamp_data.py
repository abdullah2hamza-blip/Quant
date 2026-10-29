"""Independent standard-library reconciliation of Bitstamp snapshots; no P&L."""
from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import sys


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def reconcile(data: Path, *, cache: Path | None = None) -> dict:
    manifest_path = data.with_suffix(".manifest.json")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest["provider"] != "bitstamp-public-ohlc" or manifest["symbol"] != "BTCUSD" or manifest["instrument"] != "spot":
        raise ValueError("Unexpected venue or instrument")
    if sha(data) != manifest["csv_sha256"]:
        raise ValueError("CSV hash mismatch")
    step = {"1h": 3600, "4h": 14400, "1d": 86400}[manifest["interval"]]
    with data.open(newline="", encoding="utf-8") as f:
        records = list(csv.DictReader(f))
    rows = {int(r["open_time_ms"]): r for r in records}
    if len(rows) != len(records) or list(rows) != sorted(rows):
        raise ValueError("Duplicate or unsorted normalized records")
    start = int(datetime.fromisoformat(manifest["requested_start"]).replace(tzinfo=timezone.utc).timestamp())
    finish = int(datetime.fromisoformat(manifest["requested_end"]).replace(tzinfo=timezone.utc).timestamp()) + 86400
    expected = set(range(start * 1000, finish * 1000, step * 1000))
    if not set(rows) <= expected or min(rows) != start * 1000 or max(rows) != (finish - step) * 1000:
        raise ValueError("Incomplete or inconsistent normalized boundaries")
    exclusions = {(q["source_file"], q["row_number"]): q for q in manifest["quarantined_rows"]}
    if len(exclusions) != len(manifest["quarantined_rows"]):
        raise ValueError("Duplicate quarantine records")
    visited, raw_times, excluded, hashes = set(), set(), set(), []
    cursor = start
    raw_count = 0
    for source in manifest["sources"]:
        filename = source["cache_path"].replace("\\", "/").rsplit("/", 1)[-1]
        path = cache / filename if cache is not None else Path(source["cache_path"])
        if sha(path) != source["sha256"]:
            raise ValueError("Raw response hash mismatch")
        begin, end = source["requested_start_seconds"], source["requested_end_exclusive_seconds"]
        if begin != cursor or end != begin + step * source["nominal_candles"] or not 1 <= source["nominal_candles"] <= 1000:
            raise ValueError("Noncontiguous or invalid request windows")
        cursor = end
        payload = json.loads(path.read_text(encoding="utf-8"))["data"]
        if payload.get("pair", payload.get("market")) != "BTC/USD":
            raise ValueError("Wrong raw market")
        if len(payload["ohlc"]) > source["nominal_candles"]:
            raise ValueError("Response exceeds its requested candle count")
        kept = 0
        for number, raw in enumerate(payload["ohlc"], 1):
            raw_count += 1
            opened = int(raw["timestamp"])
            if not begin <= opened < end or opened in raw_times:
                raise ValueError("Overlapping, duplicated or out-of-window raw rows")
            raw_times.add(opened)
            key = (path.name, number)
            values = [float(raw[k]) for k in ("open", "high", "low", "close", "volume")]
            o, h, l, c, v = values
            invalid = (opened % step != 0 or not all(math.isfinite(x) for x in values)
                       or min(values) <= 0 or l > min(o, c) or h < max(o, c))
            if key in exclusions:
                q = exclusions[key]
                encoded = json.dumps(raw, sort_keys=True, separators=(",", ":")).encode()
                if not invalid or hashlib.sha256(encoded).hexdigest() != q["row_sha256"] or opened * 1000 in rows:
                    raise ValueError("Invalid quarantine reconciliation")
                excluded.add(key)
                continue
            if invalid:
                raise ValueError("Invalid raw row retained without quarantine")
            target = rows.get(opened * 1000)
            if target is None or values != [float(target[k]) for k in ("open", "high", "low", "close", "volume")]:
                raise ValueError("Raw-to-normalized OHLCV mismatch or silent exclusion")
            if int(target["close_time_ms"]) != (opened + step) * 1000 - 1:
                raise ValueError("Incorrect inferred nominal close timestamp")
            visited.add(opened * 1000)
            kept += 1
        if kept != source["retained_rows"]:
            raise ValueError("Page retained count mismatch")
        hashes.append({"file": path.name, "sha256": source["sha256"]})
    if cursor != finish or visited != set(rows) or excluded != set(exclusions):
        raise ValueError("Unreconciled pages, rows or quarantine records")
    missing = sorted(expected - set(rows))
    return {"audit": "independent standard-library Bitstamp JSON/CSV reconciliation; no P&L computed",
            "data": str(data), "csv_sha256": sha(data), "manifest_sha256": sha(manifest_path),
            "pages_verified": len(hashes), "raw_rows_in_requested_range": raw_count, "retained_bars": len(rows),
            "quarantined_rows_verified": len(excluded), "missing_in_raw_response": len(expected - {t * 1000 for t in raw_times}),
            "missing_after_quarantine": len(missing), "last_missing_ms": missing[-1] if missing else None,
            "first_open_ms": min(rows), "last_open_ms": max(rows), "response_hashes": hashes,
            "limits": ["Local response hashes have no independent vendor checksum", "Close timestamps are nominal inferred endpoints",
                       "Current snapshots do not prove historical point-in-time availability", "BTC/USD and BTC/USDT histories are not independent markets"]}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--ledger", type=Path, default=Path("runs/research.sqlite"))
    parser.add_argument("--cache", type=Path, help="Relocate raw snapshots without modifying the historical manifest")
    args = parser.parse_args()
    from quant.ledger import Ledger, code_hash, utc_now
    ledger = Ledger(args.ledger)
    identifier = ledger.start("independent_bitstamp_data_audit", {"data": str(args.data), "output": str(args.output),
                              "script_sha256": sha(Path(__file__))}, code=code_hash(Path(__file__).resolve().parents[1]))
    try:
        if args.output.exists():
            raise ValueError("Audit output exists; preserve previous evidence")
        result = {"created_at": utc_now(), **reconcile(args.data, cache=args.cache)}
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2, allow_nan=False) + "\n", encoding="utf-8")
        ledger.finish(identifier, "completed", {"output": str(args.output), "sha256": sha(args.output)})
        print(json.dumps({k: v for k, v in result.items() if k != "response_hashes"}, indent=2))
        return 0
    except (ValueError, OSError, KeyError) as error:
        ledger.finish(identifier, "failed", {"error": str(error)})
        print(str(error), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
