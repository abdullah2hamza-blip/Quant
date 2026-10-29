"""Independent CSV-versus-raw-archive reconciliation; no strategy evaluation.

The validation core uses only the standard library and does not reuse the
importer's decoder or audit. Run from the project root with `uv run python ...`.
"""
from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import hashlib
import io
import json
import math
from pathlib import Path
import sys
from zipfile import ZipFile


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def reconcile(data: Path, *, previous: Path | None = None, cache: Path | None = None) -> dict:
    manifest = json.loads(data.with_suffix(".manifest.json").read_text(encoding="utf-8"))
    if sha(data) != manifest["csv_sha256"]:
        raise ValueError("CSV SHA-256 mismatch")
    seconds = {"1h": 3600, "4h": 14400, "1d": 86400}[manifest["interval"]]
    with data.open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    normalized = {int(r["open_time_ms"]): r for r in rows}
    if len(normalized) != len(rows):
        raise ValueError("Duplicate normalized timestamps")
    times = list(normalized)
    if times != sorted(times):
        raise ValueError("Unsorted normalized data")
    begin = int(datetime.fromisoformat(manifest["requested_start"]).replace(tzinfo=timezone.utc).timestamp() * 1000)
    end = int(datetime.fromisoformat(manifest["requested_end"]).replace(tzinfo=timezone.utc).timestamp() * 1000) + 86400000
    expected = set(range(begin, end, seconds * 1000))
    if not set(times) <= expected:
        raise ValueError("Unexpected normalized timestamp outside the declared UTC grid")
    if times[0] != begin or times[-1] != end - seconds * 1000:
        raise ValueError("Dataset boundaries are incomplete")
    quarantined = {(q["archive_member"], q["row_number"]): q for q in manifest["quarantined_rows"]}
    visited, raw_times, seen_quarantine = set(), set(), set()
    archive_rows, hashes = 0, []
    for source in manifest["sources"]:
        filename = source["cache_path"].replace("\\", "/").rsplit("/", 1)[-1]
        path = cache / filename if cache is not None else Path(source["cache_path"])
        actual = sha(path)
        if actual != source["sha256"]:
            raise ValueError(f"Raw archive SHA-256 mismatch: {path}")
        checksum = path.with_suffix(path.suffix + ".CHECKSUM").read_text(encoding="ascii").split()
        if checksum != [actual, path.name]:
            raise ValueError(f"Archived checksum record mismatch: {path}")
        member = path.stem + ".csv"
        # Determine units from the documented archive date, independently of
        # the decoder's numerical magnitude heuristic.
        unit = 1000 if int(path.stem.split("-")[2]) >= 2025 else 1
        with ZipFile(path) as z:
            if z.namelist() != [member]:
                raise ValueError(f"Unexpected archive members: {path}")
            raw = list(csv.reader(io.StringIO(z.read(member).decode("utf-8-sig"))))
        for number, row in enumerate(raw, 1):
            if len(row) != 12:
                raise ValueError("Raw schema mismatch")
            opened = int(row[0]) // unit
            if not begin <= opened < end:
                continue
            archive_rows += 1
            if opened in raw_times:
                raise ValueError("Overlapping or duplicate raw archive rows")
            raw_times.add(opened)
            if (member, number) in quarantined:
                q = quarantined[(member, number)]
                if hashlib.sha256(",".join(row).encode()).hexdigest() != q["row_sha256"] or opened in normalized:
                    raise ValueError("Quarantine reconciliation failed")
                seen_quarantine.add((member, number))
                continue
            target = normalized.get(opened)
            if target is None:
                raise ValueError("Raw candle silently excluded without quarantine")
            if int(row[0]) % unit or (int(row[6]) + 1) % unit:
                raise ValueError("Ambiguous raw timestamp precision")
            closed = (int(row[6]) + 1) // unit - 1
            if closed != opened + seconds * 1000 - 1 or closed != int(target["close_time_ms"]):
                raise ValueError("Raw versus normalized close mismatch")
            prices = [float(row[i]) for i in (1, 2, 3, 4, 5)]
            if prices != [float(target[k]) for k in ("open", "high", "low", "close", "volume")]:
                raise ValueError("Raw prices or volume were modified")
            o, h, l, c, v = prices
            if not all(math.isfinite(x) for x in prices) or min(o, h, l, c, v) <= 0 or l > min(o, c) or h < max(o, c):
                raise ValueError("Invalid retained prices")
            visited.add(opened)
        hashes.append({"file": path.name, "sha256": actual})
    if visited != set(times) or seen_quarantine != set(quarantined):
        raise ValueError("Manifest/raw/normalized rows do not reconcile completely")
    prefix_unchanged = None
    if previous:
        with previous.open(newline="", encoding="utf-8") as f:
            old = list(csv.DictReader(f))
        prefix_unchanged = rows[:len(old)] == old
        if not prefix_unchanged:
            raise ValueError("Previously inspected normalized prefix changed")
    missing = sorted(expected - set(times))
    gap_groups = sum(b - a > seconds * 1000 for a, b in zip(times, times[1:]))
    return {"audit": "independent standard-library raw/CSV reconciliation; no P&L computed",
            "data": str(data), "csv_sha256": sha(data), "manifest_sha256": sha(data.with_suffix(".manifest.json")),
            "archives_verified": len(hashes), "raw_rows_in_requested_range": archive_rows,
            "retained_bars": len(rows), "quarantined_rows_verified": len(seen_quarantine),
            "missing_in_raw_archive": len(expected - raw_times), "missing_after_quarantine": len(missing),
            "gap_groups": gap_groups, "previous_prefix_unchanged": prefix_unchanged,
            "first_open_ms": times[0], "last_open_ms": times[-1], "last_missing_ms": missing[-1] if missing else None,
            "normalized_microsecond_archives": sum(int(s["cache_path"].replace("\\", "/").rsplit("/", 1)[-1].split("-")[2]) >= 2025 for s in manifest["sources"]),
            "archive_hashes": hashes}


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--data", type=Path, required=True)
    p.add_argument("--previous", type=Path)
    p.add_argument("--cache", type=Path, help="Relocate raw snapshots without changing the frozen manifest bytes")
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--ledger", type=Path, default=Path("runs/research.sqlite"))
    a = p.parse_args()
    from quant.ledger import Ledger, code_hash, utc_now
    ledger = Ledger(a.ledger)
    attempt = ledger.start("independent_data_audit", {"data": str(a.data), "previous": str(a.previous), "output": str(a.output), "script_sha256": sha(Path(__file__))}, code=code_hash(Path(__file__).resolve().parents[1]))
    try:
        if a.output.exists():
            raise ValueError("Output already exists; preserve prior audits")
        result = {"created_at": utc_now(), **reconcile(a.data, previous=a.previous, cache=a.cache)}
        a.output.parent.mkdir(parents=True, exist_ok=True)
        a.output.write_text(json.dumps(result, indent=2, allow_nan=False) + "\n", encoding="utf-8")
        ledger.finish(attempt, "completed", {"output": str(a.output), "sha256": sha(a.output)})
        print(json.dumps({k:v for k,v in result.items() if k != "archive_hashes"}, indent=2))
        return 0
    except (ValueError, OSError, KeyError) as e:
        ledger.finish(attempt, "failed", {"error": str(e)})
        print(str(e), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
