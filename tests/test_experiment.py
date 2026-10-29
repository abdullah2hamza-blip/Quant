from dataclasses import replace
import json

import numpy as np
import pytest

from quant.cli import main
from quant.data import Bars, read_bars
from quant.experiment import backtest, check_freeze, make_freeze
from quant.ledger import Ledger, code_hash
from tests.factories import ROOT, sample_bars, small_settings, write_fixture


def run_small(tmp_path, phase="development", **kwargs):
    data = tmp_path / "data.csv"
    if not data.exists():
        write_fixture(data)
    ledger = Ledger(tmp_path / "research.sqlite")
    return backtest(small_settings(), data, phase, tmp_path / "runs", ledger, ROOT, plots=False, block_length=10, draws=100, **kwargs)


def test_end_to_end_report_and_artifacts(tmp_path):
    result = run_small(tmp_path)
    folder = tmp_path / "runs" / result["run_id"]
    assert {"report.json", "report.md", "equity.csv", "trades.csv", "selections.json", "config.toml"} <= {p.name for p in folder.iterdir()}
    report = json.loads((folder / "report.json").read_text())
    assert report["metadata"]["data_kind"] == "synthetic-test"
    assert report["metadata"]["phase"] == "development"
    assert report["paired_adaptive_minus_fixed"]["available"]
    rows = Ledger(tmp_path / "research.sqlite").rows()
    assert rows[0]["status"] == "completed"
    assert rows[0]["details"]["block_length"] == 10
    assert "outcome" in rows[0]["details"]


def test_future_reserved_values_cannot_change_development_results(tmp_path):
    original = sample_bars()
    values = original.values.copy()
    values[240:, :4] *= 50
    changed = Bars(original.times, values, original.close_times, original.interval, {})
    a, b = tmp_path / "a", tmp_path / "b"
    write_fixture(a / "data.csv", original)
    write_fixture(b / "data.csv", changed)
    first, second = run_small(a), run_small(b)
    assert first["fixed"] == second["fixed"]
    assert first["adaptive"] == second["adaptive"]


def test_reserved_access_requires_freeze_and_failures_are_logged(tmp_path):
    with pytest.raises(ValueError, match="requires"):
        run_small(tmp_path, "reserved")
    rows = Ledger(tmp_path / "research.sqlite").rows()
    assert rows[0]["status"] == "failed"
    assert rows[0]["details"]["reserved_access_number"] == 1


def test_freeze_then_reserved_run_and_repeat_disclosure(tmp_path):
    run_small(tmp_path, "selection")
    ledger = Ledger(tmp_path / "research.sqlite")
    freeze = tmp_path / "protocol.json"
    make_freeze(small_settings(), tmp_path / "data.csv", freeze, ledger, ROOT)
    first = run_small(tmp_path, "reserved", freeze=freeze, acknowledge_reserved=True)
    second = run_small(tmp_path, "reserved", freeze=freeze, acknowledge_reserved=True)
    for result, expected in [(first, 1), (second, 2)]:
        report = json.loads((tmp_path / "runs" / result["run_id"] / "report.json").read_text())
        assert report["metadata"]["reserved_access_number"] == expected


def test_freeze_requires_successful_selection_and_detects_changes(tmp_path):
    data = write_fixture(tmp_path / "data.csv")
    ledger = Ledger(tmp_path / "ledger.sqlite")
    freeze = tmp_path / "freeze.json"
    with pytest.raises(ValueError, match="selection"):
        make_freeze(small_settings(), data, freeze, ledger, ROOT)
    run_small(tmp_path, "selection")
    ledger = Ledger(tmp_path / "research.sqlite")
    make_freeze(small_settings(), data, freeze, ledger, ROOT)
    bars = read_bars(data)
    with pytest.raises(ValueError, match="config"):
        check_freeze(freeze, replace(small_settings(), sha256="changed"), bars, code_hash(ROOT))
    with pytest.raises(ValueError, match="code"):
        check_freeze(freeze, small_settings(), bars, "changed")
    altered = bars.values.copy()
    altered[0, 3] *= .99
    with pytest.raises(ValueError, match="prefix"):
        check_freeze(freeze, small_settings(), Bars(bars.times, altered, bars.close_times, bars.interval, {}), code_hash(ROOT))
    payload = json.loads(freeze.read_text())
    payload["base_cost_bps"] = 0
    freeze.write_text(json.dumps(payload))
    with pytest.raises(ValueError, match="integrity"):
        check_freeze(freeze, small_settings(), bars, code_hash(ROOT))


def test_report_handles_short_windows_without_cagr(tmp_path):
    data = write_fixture(tmp_path / "data.csv")
    result = backtest(small_settings(), data, "selection", tmp_path / "runs", Ledger(tmp_path / "ledger.sqlite"), ROOT, plots=False, block_length=180)
    assert result["fixed"]["cagr"] is None
    assert "unavailable" in (tmp_path / "runs" / result["run_id"] / "report.md").read_text()


def test_zero_volume_rejected_before_fill_simulation(tmp_path):
    bars = sample_bars()
    values = bars.values.copy()
    values[200, 4] = 0
    write_fixture(tmp_path / "data.csv", Bars(bars.times, values, bars.close_times, bars.interval, {}))
    with pytest.raises(ValueError, match="Zero-volume"):
        run_small(tmp_path)


def test_cli_help_and_incomplete_run_fail_cleanly(tmp_path, capsys):
    assert main([]) == 0
    data = write_fixture(tmp_path / "data.csv")
    assert main(["run", "--data", str(data), "--ledger", str(tmp_path / "ledger.sqlite"), "--no-plots"]) == 2
    assert "cover" in capsys.readouterr().err


def test_invalid_config_command_is_logged(tmp_path):
    ledger_path = tmp_path / "ledger.sqlite"
    assert main(["ledger", "--config", str(tmp_path / "missing.toml"), "--ledger", str(ledger_path)]) == 2
    rows = Ledger(ledger_path).rows()
    assert len(rows) == 1 and rows[0]["status"] == "failed"
    assert "missing.toml" in rows[0]["details"]["config"]


@pytest.mark.parametrize("kwargs", [{"block_length": 1}, {"draws": 1}, {"seed": -1}])
def test_invalid_inference_settings_rejected_even_for_short_windows(tmp_path, kwargs):
    data = write_fixture(tmp_path / "data.csv")
    ledger = Ledger(tmp_path / "ledger.sqlite")
    with pytest.raises(ValueError, match="integer"):
        backtest(small_settings(), data, "selection", tmp_path / "runs", ledger, ROOT, plots=False, **kwargs)
    assert ledger.rows()[0]["status"] == "failed"


def test_freeze_detects_runtime_drift(tmp_path, monkeypatch):
    run_small(tmp_path, "selection")
    ledger = Ledger(tmp_path / "research.sqlite")
    freeze = tmp_path / "freeze.json"
    make_freeze(small_settings(), tmp_path / "data.csv", freeze, ledger, ROOT)
    monkeypatch.setattr("quant.experiment.platform.python_version", lambda: "changed")
    with pytest.raises(ValueError, match="runtime"):
        check_freeze(freeze, small_settings(), read_bars(tmp_path / "data.csv"), code_hash(ROOT))
