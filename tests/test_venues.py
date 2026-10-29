from datetime import date
import json

import pytest

from quant.data import read_bars, timestamp
from quant.venues import decode_bitstamp, fetch_bitstamp
from scripts.audit_bitstamp_data import reconcile


BEGIN = timestamp(date(2020, 1, 1)) // 1000


def payload(count=6):
    rows = [{"timestamp": str(BEGIN + i * 14400), "open": "100", "high": "110", "low": "90", "close": "105", "volume": "2"} for i in range(count)]
    return {"data": {"pair": "BTC/USD", "ohlc": rows}}


def test_bitstamp_nominal_timestamp_and_explicit_order_normalization():
    raw = payload()
    raw["data"]["ohlc"].reverse()
    rows = decode_bitstamp(json.dumps(raw).encode(), BEGIN, BEGIN + 86400, "4h")
    assert rows[0][0] == BEGIN * 1000
    assert rows[-1][-1] == (BEGIN + 86400) * 1000 - 1


def test_bitstamp_quarantine_preserves_hash_and_rejects_silent_deduplication():
    raw = payload()
    raw["data"]["ohlc"][2]["volume"] = "0"
    excluded = []
    rows = decode_bitstamp(json.dumps(raw).encode(), BEGIN, BEGIN + 86400, "4h", excluded)
    assert len(rows) == 5 and len(excluded) == 1
    assert len(excluded[0]["row_sha256"]) == 64
    raw["data"]["ohlc"].append(raw["data"]["ohlc"][0])
    with pytest.raises(ValueError, match="duplicates"):
        decode_bitstamp(json.dumps(raw).encode(), BEGIN, BEGIN + 86400, "4h", [])


def test_bitstamp_download_is_cached_and_provenance_discloses_limits(tmp_path, monkeypatch):
    calls = []
    def download(url):
        calls.append(url)
        return json.dumps(payload()).encode()
    monkeypatch.setattr("quant.venues._download", download)
    target = tmp_path / "data.csv"
    fetch_bitstamp(date(2020,1,1), date(2020,1,1), target, cache=tmp_path / "cache", progress=lambda _:None)
    bars = read_bars(target)
    assert len(bars) == 6 and bars.provenance["symbol"] == "BTCUSD"
    assert "no independently" in bars.provenance["integrity_limit"]
    assert reconcile(target)["retained_bars"] == 6
    fetch_bitstamp(date(2020,1,1), date(2020,1,1), tmp_path / "second.csv", cache=tmp_path / "cache", progress=lambda _:None)
    assert len(calls) == 1


def test_independent_bitstamp_reconciliation_accounts_for_quarantine(tmp_path, monkeypatch):
    raw = payload()
    raw["data"]["ohlc"][2]["volume"] = "0"
    monkeypatch.setattr("quant.venues._download", lambda _: json.dumps(raw).encode())
    target = tmp_path / "data.csv"
    fetch_bitstamp(date(2020,1,1), date(2020,1,1), target, cache=tmp_path / "cache", progress=lambda _:None, allow_gaps=True, quarantine_invalid=True)
    result = reconcile(target)
    assert result["quarantined_rows_verified"] == 1 and result["missing_after_quarantine"] == 1
    assert reconcile(target,cache=tmp_path / "cache")["retained_bars"] == result["retained_bars"]
    page = next((tmp_path / "cache").glob("*.json"))
    page.write_text("tampered")
    with pytest.raises(ValueError, match="Raw response hash"):
        reconcile(target)


def test_bitstamp_rejects_wrong_market_or_provider_window():
    raw = payload()
    raw["data"]["pair"] = "ETH/USD"
    with pytest.raises(ValueError, match="market"):
        decode_bitstamp(json.dumps(raw).encode(), BEGIN, BEGIN + 86400, "4h")
    raw = payload()
    with pytest.raises(ValueError, match="window"):
        decode_bitstamp(json.dumps(raw).encode(), BEGIN, BEGIN + 14400, "4h")
