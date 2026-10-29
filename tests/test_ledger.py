"""Attempt metadata must survive finalization, including failed holdout attempts."""
from datetime import datetime

import pytest

from quant.ledger import Ledger, code_hash


@pytest.fixture
def ledger(tmp_path):
    return Ledger(tmp_path / "nested" / "attempts.sqlite")


def test_started_attempt_records_all_provenance_fields(ledger):
    details = {"dataset": "immutable.csv", "report_dir": "reports/attempt", "allow_gaps": False}
    identifier = ledger.start("backtest", details, phase="reserved", config_hash="config", code="code", data_hash="prefix")
    row = ledger.rows()[0]
    assert row["id"] == identifier
    assert row["kind"] == "backtest"
    assert row["phase"] == "reserved"
    assert row["status"] == "started"
    assert row["finished"] is None
    assert row["config_hash"] == "config"
    assert row["code_hash"] == "code"
    assert row["data_prefix_hash"] == "prefix"
    assert row["details"] == details
    assert datetime.fromisoformat(row["created"]).utcoffset().total_seconds() == 0


@pytest.mark.parametrize("status", ["completed", "failed"])
def test_finalization_preserves_started_metadata_and_nests_outcome(ledger, status):
    initial = {"dataset": "original.csv", "report_dir": "reports/original", "requested_start": "2020-01-01"}
    identifier = ledger.start("backtest", initial, phase="reserved", config_hash="c", code="s", data_hash="d")
    started = ledger.rows()[0]
    outcome = {"dataset": "outcome must not replace input", "error": "example"} if status == "failed" else {"total_return": 0.1}
    ledger.finish(identifier, status, outcome)
    finished = ledger.rows()[0]
    for key in ("id", "created", "kind", "phase", "config_hash", "code_hash", "data_prefix_hash"):
        assert finished[key] == started[key]
    assert finished["status"] == status
    assert datetime.fromisoformat(finished["finished"]) >= datetime.fromisoformat(started["created"])
    assert finished["details"] == {**initial, "outcome": outcome}


@pytest.mark.parametrize("first,second", [("completed", "completed"), ("completed", "failed"), ("failed", "completed"), ("failed", "failed")])
def test_attempt_cannot_be_finalized_twice(ledger, first, second):
    identifier = ledger.start("backtest", {"dataset": "fixture.csv"})
    ledger.finish(identifier, first, {"first": True})
    saved = ledger.rows()
    with pytest.raises(ValueError, match="already finalized"):
        ledger.finish(identifier, second, {"replacement": True})
    assert ledger.rows() == saved


def test_invalid_or_unknown_finalization_leaves_other_attempts_untouched(ledger):
    identifier = ledger.start("backtest", {})
    original = ledger.rows()
    with pytest.raises(ValueError, match="terminal attempt status"):
        ledger.finish(identifier, "started", {})
    with pytest.raises(ValueError, match="Unknown or already finalized"):
        ledger.finish("unknown", "failed", {})
    assert ledger.rows() == original


def test_nonfinite_details_do_not_create_or_finalize_an_attempt(ledger):
    with pytest.raises(ValueError):
        ledger.start("backtest", {"score": float("nan")})
    assert ledger.rows() == []
    identifier = ledger.start("backtest", {"dataset": "fixture.csv"})
    before = ledger.rows()
    with pytest.raises(ValueError):
        ledger.finish(identifier, "completed", {"score": float("inf")})
    assert ledger.rows() == before


def test_selection_requires_completed_attempt_with_exact_fingerprints(ledger):
    identifier = ledger.start("backtest", {}, phase="selection", config_hash="cfg", code="src", data_hash="data")
    assert not ledger.matching_selection("cfg", "src", "data")
    ledger.finish(identifier, "completed", {})
    assert ledger.matching_selection("cfg", "src", "data")
    assert not ledger.matching_selection("different", "src", "data")
    assert not ledger.matching_selection("cfg", "different", "data")
    assert not ledger.matching_selection("cfg", "src", "different")


@pytest.mark.parametrize("kind,phase,status", [("audit", "selection", "completed"), ("backtest", "development", "completed"), ("backtest", "selection", "failed")])
def test_other_attempts_cannot_substitute_for_completed_selection(ledger, kind, phase, status):
    identifier = ledger.start(kind, {}, phase=phase, config_hash="cfg", code="src", data_hash="data")
    ledger.finish(identifier, status, {})
    assert not ledger.matching_selection("cfg", "src", "data")


def test_reserved_budget_counts_started_completed_and_failed_attempts(ledger):
    for status in ("started", "completed", "failed"):
        identifier = ledger.start("backtest", {"fixture": status}, phase="reserved")
        if status != "started":
            ledger.finish(identifier, status, {})
    ledger.start("backtest", {}, phase="selection")
    ledger.start("audit", {}, phase="reserved")
    assert ledger.reserved_count() == 3
    assert len(ledger.rows()) == 5


@pytest.mark.parametrize("relative", ["src/quant/example.py", "tests/test_example.py", "pyproject.toml", "uv.lock"])
def test_code_hash_tracks_source_tests_and_dependency_inputs(tmp_path, relative):
    target = tmp_path / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("initial\n")
    initial = code_hash(tmp_path)
    assert code_hash(tmp_path) == initial
    target.write_text("changed\n")
    assert code_hash(tmp_path) != initial


def test_code_hash_ignores_outputs_and_tracks_relative_file_names(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    path = src / "a.py"
    path.write_text("same content\n")
    initial = code_hash(tmp_path)
    output = tmp_path / "reports" / "summary.json"
    output.parent.mkdir()
    output.write_text('{"metric": 1}')
    assert code_hash(tmp_path) == initial
    path.rename(src / "b.py")
    assert code_hash(tmp_path) != initial
