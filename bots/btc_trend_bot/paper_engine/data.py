"""Audited Binance archives and a strict, normalized UTC candle format."""
from __future__ import annotations

import calendar
import csv
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
import hashlib
import io
import json
import math
from pathlib import Path
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from zipfile import ZipFile

import numpy as np

from .config import INTERVAL_SECONDS

UTC = timezone.utc
COLUMNS = ["open_time_ms", "open", "high", "low", "close", "volume", "close_time_ms"]


def timestamp(day: date) -> int:
    return int(datetime.combine(day, datetime.min.time(), UTC).timestamp() * 1000)


def iso(ms: int) -> str:
    return datetime.fromtimestamp(int(ms) / 1000, UTC).isoformat()


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def json_write(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    temporary.replace(path)


@dataclass(frozen=True)
class Bars:
    times: np.ndarray
    values: np.ndarray  # open, high, low, close, volume
    close_times: np.ndarray
    interval: str
    provenance: dict

    def __len__(self) -> int:
        return len(self.times)

    def take(self, mask: np.ndarray) -> Bars:
        return Bars(self.times[mask], self.values[mask], self.close_times[mask], self.interval, self.provenance)

    def prefix_hash(self, end: date) -> str:
        selected = self.times < timestamp(end + timedelta(days=1))
        h = hashlib.sha256()
        h.update(self.interval.encode())
        h.update(np.asarray(self.times[selected], dtype="<i8").tobytes())
        h.update(np.asarray(self.values[selected], dtype="<f8").tobytes())
        h.update(np.asarray(self.close_times[selected], dtype="<i8").tobytes())
        return h.hexdigest()


def audit(bars: Bars, *, as_of_ms: int | None = None, allow_gaps: bool = False) -> dict:
    if bars.interval not in INTERVAL_SECONDS or len(bars) < 2 or bars.values.shape != (len(bars), 5) or bars.close_times.shape != bars.times.shape:
        raise ValueError("Need at least two correctly shaped candles with a supported interval")
    step = INTERVAL_SECONDS[bars.interval] * 1000
    if np.any(bars.times % step) or np.any(bars.close_times != bars.times + step - 1):
        raise ValueError("Candle alignment or close time does not match UTC interval")
    diffs = np.diff(bars.times)
    if np.any(diffs <= 0):
        raise ValueError("Duplicate or out-of-order candle timestamps")
    if np.any(diffs % step):
        raise ValueError("Candle spacing is not an integer multiple of the interval")
    p = bars.values
    if not np.all(np.isfinite(p)) or np.any(p[:, :4] <= 0) or np.any(p[:, 4] < 0):
        raise ValueError("Non-finite or invalid OHLCV values")
    if np.any(p[:, 1] < np.maximum(p[:, 0], p[:, 3])) or np.any(p[:, 2] > np.minimum(p[:, 0], p[:, 3])) or np.any(p[:, 1] < p[:, 2]):
        raise ValueError("OHLC prices are inconsistent")
    now_ms = int(datetime.now(UTC).timestamp() * 1000) if as_of_ms is None else as_of_ms
    if np.any(bars.close_times >= now_ms):
        raise ValueError("Incomplete or future candle")
    gaps = [{"after": iso(bars.times[i]), "before": iso(bars.times[i + 1]), "missing_bars": int(diffs[i] // step - 1)} for i in np.flatnonzero(diffs != step)]
    result = {"bars": len(bars), "interval": bars.interval, "first_open": iso(bars.times[0]), "last_close": iso(bars.close_times[-1]),
              "gaps": gaps, "missing_bars": sum(x["missing_bars"] for x in gaps), "zero_volume_bars": int(np.sum(p[:, 4] == 0)),
              "large_close_return_bars": int(np.sum(np.abs(np.diff(np.log(p[:, 3]))) > .20)),
              "gap_policy": "carry_and_freeze" if allow_gaps else "error", "as_of": iso(now_ms)}
    if gaps and not allow_gaps:
        raise ValueError(f"Missing {result['missing_bars']} bars in {len(gaps)} gaps; inspect with audit --allow-gaps, then explicitly choose carry_and_freeze")
    return result


def read_bars(path: str | Path, *, interval: str | None = None, verify_manifest: bool = True) -> Bars:
    path = Path(path)
    metadata_path = path.with_suffix(".manifest.json")
    metadata = json.loads(metadata_path.read_text(encoding="utf-8")) if metadata_path.exists() else {}
    if verify_manifest and metadata.get("csv_sha256") and digest(path) != metadata["csv_sha256"]:
        raise ValueError("Dataset hash does not match its provenance manifest")
    recorded = metadata.get("interval")
    if interval and recorded and interval != recorded:
        raise ValueError("Requested interval differs from the dataset manifest")
    chosen = interval or recorded
    if chosen not in INTERVAL_SECONDS:
        raise ValueError("Pass --interval or provide a manifest with the candle interval")
    with path.open(newline="", encoding="utf-8") as file:
        reader = csv.reader(file)
        if next(reader, None) != COLUMNS:
            raise ValueError(f"Normalized CSV header must be {COLUMNS}")
        rows = list(reader)
    if any(len(row) != 7 for row in rows):
        raise ValueError("Normalized candles must have exactly seven columns")
    try:
        times = np.asarray([int(r[0]) for r in rows], dtype=np.int64)
        values = np.asarray([[float(x) for x in r[1:6]] for r in rows], dtype=float).reshape(-1, 5)
        closes = np.asarray([int(r[6]) for r in rows], dtype=np.int64)
    except (ValueError, OverflowError) as error:
        raise ValueError("Invalid normalized CSV number") from error
    return Bars(times, values, closes, chosen, {**metadata, "local_path": str(path.resolve()), "csv_sha256": digest(path)})


def write_bars(path: Path, bars: Bars, metadata: dict) -> None:
    if path.exists() or path.with_suffix(".manifest.json").exists():
        raise ValueError("Dataset output already exists; use a new path to preserve provenance")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f, lineterminator="\n")
        writer.writerow(COLUMNS)
        for t, row, close in zip(bars.times, bars.values, bars.close_times, strict=True):
            writer.writerow([int(t), *(format(float(x), ".17g") for x in row), int(close)])
    json_write(path.with_suffix(".manifest.json"), {**metadata, "interval": bars.interval, "csv_sha256": digest(path)})


def decode_archive(payload: bytes, expected_name: str, interval: str, quarantine: list[dict] | None = None) -> list[list]:
    step = INTERVAL_SECONDS[interval] * 1000
    with ZipFile(io.BytesIO(payload)) as archive:
        if archive.namelist() != [expected_name] or archive.getinfo(expected_name).file_size > 100_000_000:
            raise ValueError("Unexpected archive member or oversized CSV")
        content = archive.read(expected_name).decode("utf-8-sig")
    result = []
    for row_number, row in enumerate(csv.reader(io.StringIO(content)), 1):
        if len(row) != 12:
            raise ValueError("Binance spot kline rows must have 12 columns")
        opened, closed = int(row[0]), int(row[6])
        unit = 1000 if opened > 100_000_000_000_000 else 1
        try:
            if opened % unit or (closed + 1) % unit:
                raise ValueError("Timestamp precision cannot be normalized without ambiguity")
            opened, closed = opened // unit, (closed + 1) // unit - 1
            if opened % step or closed != opened + step - 1:
                raise ValueError("Archive close timestamp has incorrect interval or units")
            values = [float(row[i]) for i in (1, 2, 3, 4, 5)]
            o, h, l, c, v = values
            if not all(math.isfinite(x) for x in values) or min(o, h, l, c) <= 0 or v <= 0 or h < max(o, c) or l > min(o, c) or h < l:
                raise ValueError("Invalid OHLC or nonpositive volume; execution price is not observable")
        except ValueError as error:
            if quarantine is None:
                raise
            quarantine.append({"archive_member": expected_name, "row_number": row_number, "raw_open_time": row[0], "reason": str(error),
                               "row_sha256": hashlib.sha256(",".join(row).encode()).hexdigest()})
            continue
        result.append([opened, *values, closed])
    if any(result[i][0] >= result[i + 1][0] for i in range(len(result) - 1)):
        raise ValueError("Archive contains duplicate or out-of-order rows")
    return result


def archive_plan(start: date, end: date) -> list[tuple[str, str]]:
    if end < start:
        raise ValueError("End must be on or after start")
    result = []
    cursor = start
    while cursor <= end:
        last = date(cursor.year, cursor.month, calendar.monthrange(cursor.year, cursor.month)[1])
        if cursor.day == 1 and last <= end:
            result.append(("monthly", cursor.strftime("%Y-%m")))
            cursor = last + timedelta(days=1)
        else:
            result.append(("daily", cursor.isoformat()))
            cursor += timedelta(days=1)
    return result


def _download(url: str) -> bytes:
    for attempt in range(3):
        try:
            with urlopen(Request(url, headers={"User-Agent": "QuantResearch/0.1 (public archive audit)"}), timeout=30) as response:
                payload = response.read(100_000_001)
                if len(payload) > 100_000_000:
                    raise ValueError("Download exceeds size limit")
                return payload
        except HTTPError as error:
            if error.code not in (429, 500, 502, 503, 504) or attempt == 2:
                raise ValueError(f"Archive HTTP {error.code}: {url}") from error
        except (URLError, TimeoutError) as error:
            if attempt == 2:
                raise ValueError(f"Archive download failed: {url}: {error}") from error
        time.sleep(2 ** attempt)
    raise AssertionError("unreachable")


def fetch_binance(start: date, end: date, output: Path, *, interval: str = "4h", cache: Path = Path("data/raw"), allow_gaps: bool = False, quarantine_invalid: bool = False, progress=print) -> dict:
    if interval not in INTERVAL_SECONDS:
        raise ValueError("Unsupported interval")
    if end >= datetime.now(UTC).date():
        raise ValueError("Fetch only fully closed UTC dates before today")
    if output.exists() or output.with_suffix(".manifest.json").exists():
        raise ValueError("Dataset output already exists")
    cache.mkdir(parents=True, exist_ok=True)
    rows, sources, quarantined = [], [], []
    for frequency, part in archive_plan(start, end):
        stem = f"BTCUSDT-{interval}-{part}"
        url = f"https://data.binance.vision/data/spot/{frequency}/klines/BTCUSDT/{interval}/{stem}.zip"
        checksum_path, local = cache / (stem + ".zip.CHECKSUM"), cache / (stem + ".zip")
        if not checksum_path.exists():
            checksum_path.write_bytes(_download(url + ".CHECKSUM"))
        checksum_fields = checksum_path.read_text(encoding="ascii").strip().split()
        if len(checksum_fields) != 2 or checksum_fields[1].lstrip("*") != stem + ".zip" or len(checksum_fields[0]) != 64:
            raise ValueError("Invalid archive checksum record")
        if not local.exists():
            local.write_bytes(_download(url))
        payload = local.read_bytes()
        actual = hashlib.sha256(payload).hexdigest()
        if actual.lower() != checksum_fields[0].lower():
            raise ValueError(f"Checksum mismatch: {local}; quarantine it and investigate")
        decoded = decode_archive(payload, stem + ".csv", interval, quarantined if quarantine_invalid else None)
        rows.extend(row for row in decoded if timestamp(start) <= row[0] < timestamp(end + timedelta(days=1)))
        sources.append({"url": url, "sha256": actual, "checksum_url": url + ".CHECKSUM", "cache_path": str(local.resolve())})
        progress(f"Verified {stem}")
    if not rows:
        raise ValueError("No rows in requested date range")
    # Chronological archive planning must not silently deduplicate overlaps.
    bars = Bars(np.asarray([r[0] for r in rows], dtype=np.int64), np.asarray([r[1:6] for r in rows], dtype=float), np.asarray([r[6] for r in rows], dtype=np.int64), interval, {})
    summary = audit(bars, allow_gaps=allow_gaps)
    expected_last = timestamp(end + timedelta(days=1)) - INTERVAL_SECONDS[interval] * 1000
    if int(bars.times[0]) != timestamp(start) or int(bars.times[-1]) != expected_last:
        raise ValueError("Requested date boundaries are missing from archive data")
    manifest = {"schema_version": 1, "symbol": "BTCUSDT", "instrument": "spot", "provider": "binance-public-data", "retrieved_at": datetime.now(UTC).isoformat(), "requested_start": str(start), "requested_end": str(end), "sources": sources, "audit": summary, "quarantine_enabled": quarantine_invalid, "quarantined_rows": quarantined, "revision_policy": "immutable local snapshot; checksums are integrity evidence, not proof of point-in-time availability"}
    write_bars(output, bars, manifest)
    return {"output": str(output), "quarantined_rows": len(quarantined), **summary}


def resample(bars: Bars, interval: str) -> Bars:
    if interval not in INTERVAL_SECONDS or INTERVAL_SECONDS[interval] % INTERVAL_SECONDS[bars.interval]:
        raise ValueError("Can only aggregate to an integer multiple of the source interval")
    factor = INTERVAL_SECONDS[interval] // INTERVAL_SECONDS[bars.interval]
    step = INTERVAL_SECONDS[interval] * 1000
    groups = bars.times // step
    rows, times, ends = [], [], []
    for group in np.unique(groups):
        indices = np.flatnonzero(groups == group)
        if len(indices) != factor or bars.times[indices[0]] != group * step or np.any(np.diff(bars.times[indices]) != INTERVAL_SECONDS[bars.interval] * 1000):
            raise ValueError("Cannot aggregate an incomplete target candle")
        block = bars.values[indices]
        rows.append([block[0, 0], block[:, 1].max(), block[:, 2].min(), block[-1, 3], block[:, 4].sum()])
        times.append(int(group * step))
        ends.append(int(group * step + step - 1))
    return Bars(np.asarray(times, dtype=np.int64), np.asarray(rows), np.asarray(ends, dtype=np.int64), interval, {"derived_from": bars.provenance, "aggregation": "complete UTC candles only"})
