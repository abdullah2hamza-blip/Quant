"""Secondary public venue data; no account, credentials or order interface."""
from __future__ import annotations

from datetime import date, datetime, timedelta
import hashlib
import json
import math
from pathlib import Path

import numpy as np

from .config import INTERVAL_SECONDS
from .data import Bars, UTC, _download, audit, timestamp, write_bars


def decode_bitstamp(payload: bytes, begin_seconds: int, end_seconds: int, interval: str,
                    quarantine: list[dict] | None = None) -> list[list]:
    response = json.loads(payload)
    market = response["data"]
    if market.get("pair", market.get("market")) != "BTC/USD":
        raise ValueError("Bitstamp returned a different or unidentified market")
    raw = market["ohlc"]
    if not isinstance(raw, list) or len(raw) > 1000:
        raise ValueError("Invalid Bitstamp response dimensions")
    result, seen = [], set()
    for number, row in enumerate(raw, 1):
        opened = int(row["timestamp"])
        if opened in seen:
            raise ValueError("Bitstamp response duplicates a timestamp")
        seen.add(opened)
        if not begin_seconds <= opened < end_seconds:
            raise ValueError("Bitstamp response is outside the requested page window")
        try:
            if opened % INTERVAL_SECONDS[interval]:
                raise ValueError("Bitstamp candle is off the UTC grid")
            values = [float(row[x]) for x in ("open", "high", "low", "close", "volume")]
            o, h, l, c, v = values
            if not all(math.isfinite(x) for x in values) or min(o, h, l, c, v) <= 0 or l > min(o, c) or h < max(o, c):
                raise ValueError("Invalid Bitstamp prices or nonpositive volume")
        except ValueError as error:
            if quarantine is None:
                raise
            quarantine.append({"row_number": number, "raw_open_time": row["timestamp"], "reason": str(error),
                               "row_sha256": hashlib.sha256(json.dumps(row, sort_keys=True, separators=(",", ":")).encode()).hexdigest()})
            continue
        result.append([opened * 1000, *values, (opened + INTERVAL_SECONDS[interval]) * 1000 - 1])
    # Native response ordering is not assumed. Preserve raw payload and record
    # this explicit ascending-order normalization; duplicates are never dropped.
    return sorted(result, key=lambda r: r[0])


def fetch_bitstamp(start: date, end: date, output: Path, *, interval: str = "4h", cache: Path = Path("data/raw/bitstamp"),
                   allow_gaps: bool = False, quarantine_invalid: bool = False, progress=print) -> dict:
    if interval not in INTERVAL_SECONDS or end < start or end >= datetime.now(UTC).date():
        raise ValueError("Need a supported interval and fully completed ordered UTC dates")
    if output.exists() or output.with_suffix(".manifest.json").exists():
        raise ValueError("Dataset output already exists; preserve the earlier snapshot")
    begin, finish = timestamp(start) // 1000, timestamp(end + timedelta(days=1)) // 1000
    step = INTERVAL_SECONDS[interval]
    cache.mkdir(parents=True, exist_ok=True)
    rows, sources, quarantine = [], [], []
    cursor = begin
    while cursor < finish:
        count = min(1000, (finish - cursor) // step)
        page_end = cursor + count * step
        url = f"https://www.bitstamp.net/api/v2/ohlc/btcusd/?step={step}&limit={count}&start={cursor}&exclude_current_candle=true"
        path = cache / f"BTCUSD-{interval}-{cursor}-{count}.json"
        if not path.exists():
            path.write_bytes(_download(url))
        payload = path.read_bytes()
        excluded = [] if quarantine_invalid else None
        decoded = decode_bitstamp(payload, cursor, page_end, interval, excluded)
        if excluded:
            quarantine.extend({"source_file": path.name, **q} for q in excluded)
        rows.extend(decoded)
        sources.append({"url": url, "sha256": hashlib.sha256(payload).hexdigest(), "cache_path": str(path.resolve()),
                        "requested_start_seconds": cursor, "requested_end_exclusive_seconds": page_end,
                        "nominal_candles": count, "retained_rows": len(decoded)})
        progress(f"Recorded Bitstamp {interval} window {cursor} ({len(decoded)} rows)")
        cursor = page_end
    bars = Bars(np.asarray([r[0] for r in rows], dtype=np.int64), np.asarray([r[1:6] for r in rows], dtype=float),
                np.asarray([r[6] for r in rows], dtype=np.int64), interval, {})
    quality = audit(bars, allow_gaps=allow_gaps)
    if bars.times[0] != begin * 1000 or bars.times[-1] != (finish - step) * 1000:
        raise ValueError("Bitstamp dataset does not cover the requested boundaries")
    manifest = {"schema_version": 1, "provider": "bitstamp-public-ohlc", "symbol": "BTCUSD", "instrument": "spot",
                "retrieved_at": datetime.now(UTC).isoformat(), "requested_start": str(start), "requested_end": str(end),
                "sources": sources, "quarantined_rows": quarantine, "quarantine_enabled": quarantine_invalid,
                "audit": quality, "ordering": "explicit ascending timestamp normalization; duplicates are errors",
                "close_timestamp": "nominal inclusive period end inferred from documented step; API provides opening timestamp only",
                "integrity_limit": "local SHA-256 snapshots; no independently published vendor checksum",
                "revision_policy": "immutable local response snapshot; no historical point-in-time revision guarantee",
                "comparison_limit": "BTC/USD at a different venue is a robustness check, not an independent Bitcoin history or USDT-equivalent market"}
    write_bars(output, bars, manifest)
    return {"output": str(output), "provider": manifest["provider"], "quarantined_rows": len(quarantine), **quality}
