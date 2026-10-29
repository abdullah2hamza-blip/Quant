from datetime import date
import json

import numpy as np
import pytest

from quant.data import Bars, digest, json_write, read_bars, timestamp
from quant.engine import simulate
from quant.ledger import Ledger
from quant.market_study import (check_market_freeze, evaluate_market_case, freeze_market,
                                load_market_spec, log_attribution, run_market)
from tests.factories import ROOT, sample_bars, small_settings, write_fixture


def fixture(tmp_path):
    root = tmp_path / "project"
    config = root / "configs/research/btc-trend.toml"
    config.parent.mkdir(parents=True)
    text = (ROOT / "configs/research/btc-trend.toml").read_text()
    changes = {"fast_bars = 50": "fast_bars = 3", "slow_bars = 200": "slow_bars = 8", "warmup_bars = 2000": "warmup_bars = 60",
               "volatility_lookback_bars = 180": "volatility_lookback_bars = 10", "[[25, 100], [50, 200], [100, 400]]": "[[2, 5], [3, 8], [6, 12]]",
               "selection_interval_bars = 180": "selection_interval_bars = 20", "trailing_selection_bars = 4380": "trailing_selection_bars = 120",
               "minimum_history_before_scoring_bars = 6380": "minimum_history_before_scoring_bars = 180", "initial_pair = [50, 200]": "initial_pair = [3, 8]",
               "2017-09-01": "2020-01-01", "2022-12-31": "2020-02-09", "2023-01-01": "2020-02-10", "2024-12-31": "2020-02-19",
               "2025-01-01": "2020-02-20", "2026-10-20": "2020-02-29"}
    for a, b in changes.items():
        assert a in text
        text = text.replace(a, b)
    config.write_text(text)
    data = write_fixture(root / "data/input.csv")
    json_write(root / "docs/audit.json", {"csv_sha256": digest(data), "manifest_sha256": digest(data.with_suffix(".manifest.json")), "note": "Unit-test fixture, not a scientific audit"})
    for name in ("protocol", "review"):
        (root / "docs" / f"{name}.md").write_text("Unit-test fixture; no actual independent scientific review\n")
    spec = {"schema_version": 1, "study_id": "unit-test", "config": "configs/research/btc-trend.toml", "materiality_annual_log": .02,
            "base_cost_bps": 25, "costs_bps": [25, 0, 100], "bootstrap": {"draws": 100, "block_days": [1, 3, 6], "seed": 42, "confidence": .95},
            "cases": [{"id": "test", "data": "data/input.csv", "independent_audit": "docs/audit.json", "interval": "4h", "symbol": "BTCUSDT",
                       "provider": "synthetic-test", "start": "2020-02-01", "end": "2020-02-29", "role": "primary"}]}
    spec_path = root / "configs/research/market.json"
    json_write(spec_path, spec)
    ledger = Ledger(tmp_path / "ledger.sqlite")
    freeze = tmp_path / "freeze.json"
    return root, spec_path, spec, ledger, freeze


def make_frozen(root, spec_path, ledger, freeze):
    return freeze_market(spec_path, root / "docs/protocol.md", root / "docs/review.md", freeze, ledger, root)


def test_market_freeze_uses_features_without_evaluating_portfolios(tmp_path, monkeypatch):
    root, path, spec, ledger, freeze = fixture(tmp_path)
    def forbidden(*args, **kwargs):
        raise AssertionError("Freeze must not evaluate portfolio P&L")
    monkeypatch.setattr("quant.market_study.run_suite", forbidden)
    frozen = make_frozen(root, path, ledger, freeze)
    assert frozen["coverage"][0]["scored_bars"] == 174
    assert check_market_freeze(freeze, path, root)["freeze_sha256"] == frozen["freeze_sha256"]
    assert "no matching hourly" in frozen["gate"]


def test_market_gate_logs_failed_access_and_completes_all_artifacts(tmp_path):
    root, path, spec, ledger, freeze = fixture(tmp_path)
    make_frozen(root, path, ledger, freeze)
    with pytest.raises(ValueError, match="acknowledgement"):
        run_market(path, freeze, tmp_path / "runs", ledger, root)
    result = run_market(path, freeze, tmp_path / "runs", ledger, root, acknowledge_retrospective=True, progress=lambda _: None)
    assert result["retrospective_access_number"] == 2
    folder = tmp_path / "runs" / result["run_id"]
    manifest = json.loads((folder / "manifest.json").read_text())
    assert manifest["status"] == "completed"
    for name, expected in manifest["cases"][0]["sha256"].items():
        assert digest(folder / "test" / name) == expected
    report = json.loads((folder / "test/report.json").read_text())
    assert len(report["scenarios"]["25"]["metrics"]) == 9
    assert report["scenarios"]["25"]["adaptive_minus_fixed"]["bootstrap_by_block_days"]["1"]["available"]
    assert not report["scenarios"]["25"]["adaptive_minus_fixed"]["bootstrap_by_block_days"]["6"]["available"]
    attempts = [r for r in ledger.rows() if r["kind"] == "publication_market"]
    assert [r["status"] for r in attempts] == ["failed", "completed"]


@pytest.mark.parametrize("change,match", [("protocol", "protocol or review"), ("source", "code_sha256"), ("data", "Independent audit")])
def test_market_freeze_rejects_changed_inputs(tmp_path, change, match):
    root, path, spec, ledger, freeze = fixture(tmp_path)
    (root / "src").mkdir()
    (root / "src/model.py").write_text("original = True\n")
    make_frozen(root, path, ledger, freeze)
    if change == "protocol":
        (root / "docs/protocol.md").write_text("changed\n")
    elif change == "source":
        (root / "src/model.py").write_text("original = False\n")
    else:
        (root / "data/input.csv").write_bytes((root / "data/input.csv").read_bytes() + b"\n")
    with pytest.raises(ValueError, match=match):
        check_market_freeze(freeze, path, root)


def test_market_freeze_cannot_silently_shift_an_ineligible_start(tmp_path):
    root, path, spec, ledger, freeze = fixture(tmp_path)
    spec["cases"][0]["start"] = "2020-01-10"
    json_write(path, spec)
    with pytest.raises(ValueError, match="insufficient"):
        make_frozen(root, path, ledger, freeze)
    assert ledger.rows()[-1]["status"] == "failed"


def test_accounting_attribution_includes_gaps_and_inherited_holdings():
    bars = sample_bars()
    # Force different adjacent close/open values and an observation gap.
    keep = np.arange(len(bars)) != 200
    values = bars.values[keep].copy()
    values[100:, :4] *= 1.2
    changed = Bars(bars.times[keep], values, bars.close_times[keep], bars.interval, {})
    targets = np.full(len(changed), .65)
    targets[180:240], targets[240:] = .2, .8
    book = simulate(changed, targets, small_settings(), 100, "test")
    result, parts = log_attribution(book, changed, 150, 320)
    assert book.coins[149] > 0
    assert result["execution_cost"] < 0
    assert result["total_log_return"] == pytest.approx(np.log(book.nav[319] / book.nav[149]))
    np.testing.assert_allclose(sum(parts.values()), book.log_returns[150:320], atol=1e-12)


def test_market_results_are_deterministic_and_earlier_paths_ignore_future_prices(tmp_path):
    root, path, spec, ledger, freeze = fixture(tmp_path)
    case = spec["cases"][0]
    a = evaluate_market_case(spec, case, root, tmp_path / "a")
    b = evaluate_market_case(spec, case, root, tmp_path / "b")
    assert a["scenarios"] == b["scenarios"]
    bars = read_bars(root / "data/input.csv")
    changed = bars.values.copy()
    changed[300:, :4] *= 3
    write_fixture(root / "data/changed.csv", Bars(bars.times, changed, bars.close_times, bars.interval, {}))
    other = {**case, "data": "data/changed.csv"}
    evaluate_market_case(spec, other, root, tmp_path / "c")
    start = int(np.searchsorted(bars.times, timestamp(date.fromisoformat(case["start"]))))
    with np.load(tmp_path / "a/paths.npz") as original, np.load(tmp_path / "c/paths.npz") as mutated:
        for key in original.files:
            np.testing.assert_array_equal(original[key][:300-start], mutated[key][:300-start])


@pytest.mark.parametrize("field,value", [("base_cost_bps", True), ("costs_bps", [25, 25]), ("materiality_annual_log", float("nan"))])
def test_market_spec_rejects_invalid_financial_inputs(tmp_path, field, value):
    root, path, spec, ledger, freeze = fixture(tmp_path)
    spec[field] = value
    path.write_text(json.dumps(spec))
    with pytest.raises(ValueError):
        load_market_spec(path)


def test_daily_bootstrap_requires_at_least_two_candles_per_block(tmp_path):
    root, path, spec, ledger, freeze = fixture(tmp_path)
    spec["cases"][0]["interval"] = "1d"
    json_write(path, spec)
    with pytest.raises(ValueError, match="at least two candles"):
        load_market_spec(path)
