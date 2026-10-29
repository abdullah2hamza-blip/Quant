"""Data-integrity tests use tiny local archives; no exchange calls are made."""
from datetime import date, timedelta
import csv
import hashlib
import io
import json
from zipfile import ZipFile

import numpy as np
import pytest

from quant import data


DAY = date(2020, 1, 2)
STEP = 4 * 60 * 60 * 1000


def make_bars(offsets=(0, 1, 2), *, interval="4h"):
    step = data.INTERVAL_SECONDS[interval] * 1000
    times = data.timestamp(DAY) + np.asarray(offsets, dtype=np.int64) * step
    prices = np.asarray([[100 + i, 110 + i, 90 + i, 105 + i, 2 + i] for i in range(len(times))], dtype=float)
    return data.Bars(times, prices, times + step - 1, interval, {"fixture": "local"})


def archive_rows(count=6, *, microseconds=False):
    rows = []
    for i in range(count):
        opened = data.timestamp(DAY) + i * STEP
        closed = opened + STEP - 1
        if microseconds:
            opened, closed = opened * 1000, (closed + 1) * 1000 - 1
        rows.append([str(x) for x in [opened, 100, 110, 90, 105, 2, closed, 0, 1, 0, 0, 0]])
    return rows


def archive_bytes(rows, member="BTCUSDT-4h-2020-01-02.csv"):
    content = io.StringIO(newline="")
    csv.writer(content, lineterminator="\n").writerows(rows)
    buffer = io.BytesIO()
    with ZipFile(buffer, "w") as archive:
        archive.writestr(member, content.getvalue())
    return buffer.getvalue()


def mock_download(monkeypatch, payload):
    stem = "BTCUSDT-4h-2020-01-02.zip"
    calls = []

    def download(url):
        calls.append(url)
        if url.endswith(stem + ".CHECKSUM"):
            return f"{hashlib.sha256(payload).hexdigest()}  {stem}\n".encode()
        if url.endswith(stem):
            return payload
        raise AssertionError(f"Unexpected archive request: {url}")

    monkeypatch.setattr(data, "_download", download)
    return calls


def test_millisecond_and_microsecond_archives_normalize_identically():
    member = "BTCUSDT-4h-2020-01-02.csv"
    millis = data.decode_archive(archive_bytes(archive_rows()), member, "4h")
    micros = data.decode_archive(archive_bytes(archive_rows(microseconds=True)), member, "4h")
    assert millis == micros
    assert millis[0] == [data.timestamp(DAY), 100, 110, 90, 105, 2, data.timestamp(DAY) + STEP - 1]
    assert millis[-1][0] == data.timestamp(DAY) + 5 * STEP


@pytest.mark.parametrize("field,value,reason", [(6, "0", "incorrect interval"), (5, "0", "nonpositive volume"), (4, "nan", "Invalid OHLC"), (1, "-1", "Invalid OHLC")])
def test_invalid_archive_rows_require_explicit_quarantine(field, value, reason):
    rows = archive_rows(3)
    rows[1][field] = value
    payload = archive_bytes(rows)
    member = "BTCUSDT-4h-2020-01-02.csv"
    with pytest.raises(ValueError, match=reason):
        data.decode_archive(payload, member, "4h")

    quarantine = []
    accepted = data.decode_archive(payload, member, "4h", quarantine)
    assert [row[0] for row in accepted] == [int(rows[0][0]), int(rows[2][0])]
    assert len(quarantine) == 1
    assert quarantine[0]["archive_member"] == member
    assert quarantine[0]["row_number"] == 2
    assert quarantine[0]["raw_open_time"] == rows[1][0]
    assert reason in quarantine[0]["reason"]
    assert quarantine[0]["row_sha256"] == hashlib.sha256(",".join(rows[1]).encode()).hexdigest()


def test_microsecond_precision_is_not_silently_rounded():
    rows = archive_rows(2, microseconds=True)
    rows[0][6] = str(int(rows[0][6]) - 1)
    with pytest.raises(ValueError, match="without ambiguity"):
        data.decode_archive(archive_bytes(rows), "BTCUSDT-4h-2020-01-02.csv", "4h")


@pytest.mark.parametrize("order", [(0, 0), (1, 0)])
def test_archive_and_normalized_audit_reject_duplicates_or_reordering(order):
    rows = archive_rows(2)
    with pytest.raises(ValueError, match="duplicate or out-of-order"):
        data.decode_archive(archive_bytes([rows[i] for i in order]), "BTCUSDT-4h-2020-01-02.csv", "4h", [])
    with pytest.raises(ValueError, match="Duplicate or out-of-order"):
        data.audit(make_bars(order))


def test_archive_requires_exact_member_and_column_count():
    with pytest.raises(ValueError, match="Unexpected archive member"):
        data.decode_archive(archive_bytes(archive_rows(2), "unexpected.csv"), "expected.csv", "4h")
    rows = archive_rows(2)
    rows[0].pop()
    with pytest.raises(ValueError, match="12 columns"):
        data.decode_archive(archive_bytes(rows), "BTCUSDT-4h-2020-01-02.csv", "4h", [])


def test_audit_requires_explicit_gap_policy_and_reports_missing_intervals():
    bars = make_bars((0, 1, 4, 5))
    with pytest.raises(ValueError, match="Missing 2 bars"):
        data.audit(bars)
    summary = data.audit(bars, allow_gaps=True)
    assert summary["missing_bars"] == 2
    assert summary["gap_policy"] == "carry_and_freeze"
    assert summary["gaps"] == [{"after": data.iso(bars.times[1]), "before": data.iso(bars.times[2]), "missing_bars": 2}]


@pytest.mark.parametrize("clock_offset", [0, -1, -STEP])
def test_audit_rejects_incomplete_and_future_candles(clock_offset):
    bars = make_bars()
    with pytest.raises(ValueError, match="Incomplete or future"):
        data.audit(bars, as_of_ms=int(bars.close_times[-1]) + clock_offset)
    assert data.audit(bars, as_of_ms=int(bars.close_times[-1]) + 1)["bars"] == len(bars)


def test_audit_reports_zero_volume_for_an_explicit_dataset_review():
    bars = make_bars()
    bars.values[1, 4] = 0
    assert data.audit(bars)["zero_volume_bars"] == 1


@pytest.mark.parametrize("bad_close", [False, True])
def test_audit_rejects_misaligned_open_or_close(bad_close):
    bars = make_bars()
    (bars.close_times if bad_close else bars.times)[1] += 1
    with pytest.raises(ValueError, match="alignment or close time"):
        data.audit(bars)


@pytest.mark.parametrize("field,value,reason", [(4, -1, "invalid OHLCV"), (0, np.nan, "invalid OHLCV"), (1, 99, "inconsistent")])
def test_audit_rejects_invalid_prices_or_negative_volume(field, value, reason):
    bars = make_bars()
    bars.values[0, field] = value
    with pytest.raises(ValueError, match=reason):
        data.audit(bars)


def test_normalized_round_trip_and_declared_manifest_hash(tmp_path):
    original = make_bars()
    path = tmp_path / "bars.csv"
    data.write_bars(path, original, {"provider": "local fixture"})
    restored = data.read_bars(path)
    np.testing.assert_array_equal(restored.times, original.times)
    np.testing.assert_array_equal(restored.values, original.values)
    np.testing.assert_array_equal(restored.close_times, original.close_times)
    assert restored.provenance["csv_sha256"] == data.digest(path)
    assert restored.provenance["provider"] == "local fixture"
    assert restored.provenance["local_path"] == str(path.resolve())
    assert data.audit(restored)["missing_bars"] == 0


@pytest.mark.parametrize("tamper_csv", [True, False])
def test_csv_or_manifest_declared_hash_tampering_is_detected(tmp_path, tamper_csv):
    path = tmp_path / "bars.csv"
    data.write_bars(path, make_bars(), {})
    if tamper_csv:
        path.write_text(path.read_text().replace(",105,", ",106,", 1))
    else:
        manifest = path.with_suffix(".manifest.json")
        metadata = json.loads(manifest.read_text())
        metadata["csv_sha256"] = "0" * 64
        manifest.write_text(json.dumps(metadata))
    with pytest.raises(ValueError, match="provenance manifest"):
        data.read_bars(path)


def test_manifest_interval_must_match_explicit_interval(tmp_path):
    path = tmp_path / "bars.csv"
    data.write_bars(path, make_bars(), {})
    with pytest.raises(ValueError, match="differs from the dataset manifest"):
        data.read_bars(path, interval="1h")


@pytest.mark.parametrize("existing", ["csv", "manifest"])
def test_dataset_snapshots_cannot_be_overwritten(tmp_path, existing):
    path = tmp_path / "bars.csv"
    occupied = path if existing == "csv" else path.with_suffix(".manifest.json")
    occupied.write_text("preserve me")
    with pytest.raises(ValueError, match="already exists"):
        data.write_bars(path, make_bars(), {})
    assert occupied.read_text() == "preserve me"


def test_prefix_hash_ignores_future_but_detects_changes_inside_prefix():
    bars = make_bars(tuple(range(12)))
    initial = bars.prefix_hash(DAY)
    bars.values[7, 3] += 1
    assert bars.prefix_hash(DAY) == initial
    bars.values[3, 3] += 1
    assert bars.prefix_hash(DAY) != initial


def test_resampling_uses_complete_utc_blocks_with_ohlcv_aggregation():
    bars = make_bars(tuple(range(8)), interval="1h")
    result = data.resample(bars, "4h")
    np.testing.assert_array_equal(result.times, bars.times[[0, 4]])
    np.testing.assert_array_equal(result.close_times, bars.close_times[[3, 7]])
    np.testing.assert_array_equal(result.values, [[100, 113, 90, 108, 14], [104, 117, 94, 112, 30]])
    assert result.provenance["derived_from"] == bars.provenance
    assert result.provenance["aggregation"] == "complete UTC candles only"


@pytest.mark.parametrize("indices", [(0, 1, 2), (1, 2, 3), (0, 1, 3), (0, 1, 2, 3, 4)])
def test_resampling_rejects_partial_boundaries_and_internal_missing_candles(indices):
    with pytest.raises(ValueError, match="incomplete target candle"):
        data.resample(make_bars(indices, interval="1h"), "4h")


def test_resampling_cannot_invent_finer_candles():
    with pytest.raises(ValueError, match="integer multiple"):
        data.resample(make_bars(), "1h")


def test_fetch_verifies_and_reuses_cached_archive_without_network(tmp_path, monkeypatch):
    payload = archive_bytes(archive_rows())
    calls = mock_download(monkeypatch, payload)
    cache = tmp_path / "cache"
    output = tmp_path / "first.csv"
    summary = data.fetch_binance(DAY, DAY, output, cache=cache, progress=lambda _: None)
    assert len(calls) == 2
    assert summary["bars"] == 6
    assert summary["quarantined_rows"] == 0
    metadata = json.loads(output.with_suffix(".manifest.json").read_text())
    assert metadata["sources"][0]["sha256"] == hashlib.sha256(payload).hexdigest()
    assert metadata["quarantine_enabled"] is False
    assert metadata["quarantined_rows"] == []

    def forbid_download(url):
        raise AssertionError(f"Network is forbidden: {url}")

    monkeypatch.setattr(data, "_download", forbid_download)
    second = tmp_path / "second.csv"
    data.fetch_binance(DAY, DAY, second, cache=cache, progress=lambda _: None)
    assert second.read_bytes() == output.read_bytes()


def test_fetch_rejects_cached_checksum_mismatch_before_writing_output(tmp_path, monkeypatch):
    cache = tmp_path / "cache"
    cache.mkdir()
    stem = "BTCUSDT-4h-2020-01-02.zip"
    (cache / stem).write_bytes(archive_bytes(archive_rows()))
    (cache / (stem + ".CHECKSUM")).write_text(f"{'0' * 64}  {stem}\n")

    def forbid_download(url):
        raise AssertionError(f"Network is forbidden: {url}")

    monkeypatch.setattr(data, "_download", forbid_download)
    output = tmp_path / "bars.csv"
    with pytest.raises(ValueError, match="Checksum mismatch"):
        data.fetch_binance(DAY, DAY, output, cache=cache, progress=lambda _: None)
    assert not output.exists()
    assert not output.with_suffix(".manifest.json").exists()


@pytest.mark.parametrize("field,value", [(5, "0"), (6, "0")])
def test_fetch_explicit_quarantine_records_invalid_row_and_resulting_gap(tmp_path, monkeypatch, field, value):
    rows = archive_rows()
    rows[2][field] = value
    mock_download(monkeypatch, archive_bytes(rows))
    cache = tmp_path / "cache"
    strict = tmp_path / "strict.csv"
    with pytest.raises(ValueError):
        data.fetch_binance(DAY, DAY, strict, cache=cache, progress=lambda _: None)
    assert not strict.exists()

    output = tmp_path / "quarantined.csv"
    summary = data.fetch_binance(DAY, DAY, output, cache=cache, allow_gaps=True, quarantine_invalid=True, progress=lambda _: None)
    assert summary["bars"] == 5
    assert summary["missing_bars"] == 1
    assert summary["quarantined_rows"] == 1
    metadata = json.loads(output.with_suffix(".manifest.json").read_text())
    assert metadata["quarantine_enabled"] is True
    assert metadata["audit"]["gap_policy"] == "carry_and_freeze"
    assert metadata["quarantined_rows"][0]["row_number"] == 3
    assert metadata["quarantined_rows"][0]["row_sha256"] == hashlib.sha256(",".join(rows[2]).encode()).hexdigest()
    assert len(data.read_bars(output)) == 5


def test_quarantine_does_not_silently_relax_gap_or_requested_boundary_controls(tmp_path, monkeypatch):
    rows = archive_rows()
    rows[2][5] = "0"
    mock_download(monkeypatch, archive_bytes(rows))
    with pytest.raises(ValueError, match="Missing 1 bars"):
        data.fetch_binance(DAY, DAY, tmp_path / "gap.csv", cache=tmp_path / "a", quarantine_invalid=True, progress=lambda _: None)
    rows = archive_rows()
    rows[0][5] = "0"
    mock_download(monkeypatch, archive_bytes(rows))
    with pytest.raises(ValueError, match="date boundaries are missing"):
        data.fetch_binance(DAY, DAY, tmp_path / "boundary.csv", cache=tmp_path / "b", allow_gaps=True, quarantine_invalid=True, progress=lambda _: None)


def test_archive_plan_uses_full_months_and_nonoverlapping_boundary_days():
    assert data.archive_plan(date(2020, 1, 31), date(2020, 3, 1)) == [("daily", "2020-01-31"), ("monthly", "2020-02"), ("daily", "2020-03-01")]
    with pytest.raises(ValueError, match="End must"):
        data.archive_plan(DAY, DAY - timedelta(days=1))
