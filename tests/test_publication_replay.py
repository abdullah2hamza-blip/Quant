import hashlib
import json
from pathlib import Path
import shutil

import numpy as np
import pytest

from scripts.verify_publication_replay import compare_replay


def write(path: Path, value):
    path.write_text(json.dumps(value, allow_nan=False), encoding="utf-8")


def read(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def sha(path: Path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def refresh(root: Path, market=False):
    manifest = read(root / "manifest.json")
    if market:
        for entry in manifest["cases"]:
            entry["sha256"] = {p.name: sha(p) for p in (root / entry["case_id"]).iterdir()}
    else:
        for entry in manifest["completed"]:
            entry["json_sha256"] = sha(root / (entry["id"] + ".json"))
            entry["worlds_sha256"] = sha(root / (entry["id"] + ".npz"))
    write(root / "manifest.json", manifest)


def fixture(tmp_path, market=False):
    original = tmp_path / "original"
    original.mkdir()
    if market:
        case = original / "unit"
        case.mkdir()
        manifest = {"status": "completed", "run_id": "old", "created_at": "old-time", "finished_at": "old-finish",
                    "retrospective_access_number": 1, "spec": {"cases": [{"id": "unit"}]},
                    "cases": [{"case_id": "unit", "elapsed_seconds": 1., "sha256": {}}]}
        write(case / "report.json", {"created_at": "old-time", "effective_settings": {"source": "/old/config", "sha256": "fixed"},
              "audit": {"as_of": "old-time", "missing_bars": 0}, "provenance": {"local_path": "/old/data", "provider": "fixed"},
              "scenarios": {"25": {"initial_state": {"nav": 1.}, "metrics": {"return": .01}, "interval": [-.1, .2]}}})
        write(case / "selections.json", [{"decision_time": "fixed-close", "selected_pair": [50, 200], "scores": [.1, .2]}])
        write(case / "base-cost-trades.json", {"adaptive": [{"execution_time": "fixed-open", "target": .5}]})
        np.savez(case / "paths.npz", nav=np.array([1., 1.1]), time=np.array([1, 2], dtype=np.int64))
    else:
        manifest = {"kind": "substantive", "run_id": "old", "created_at": "old-time", "runtime": {"platform": "old", "python": "3.13.7"},
                    "spec": {"cases": [{"id": "unit"}], "alpha": .05}, "case_ids": ["unit"], "completed": [{"id": "unit"}]}
        write(original / "unit.json", {"runtime_seconds": 1., "seed": 7, "trials": [20], "guarantee": "conditional", "power": .5,
                                      "interval": [.1, .9], "trace": [{"calendar_step": 20, "rate": .5}]})
        write(original / "counterexamples.json", {"bound": .9, "claim": "fixed"})
        np.savez(original / "unit.npz", rejected=np.array([True, False]), utility=np.array([0., .1]))
    write(original / "manifest.json", manifest)
    refresh(original, market)
    replay = tmp_path / "replay"
    shutil.copytree(original, replay)
    return original, replay


def test_simulation_compares_reports_auxiliary_and_arrays_with_only_operational_exclusions(tmp_path):
    original, replay = fixture(tmp_path)
    manifest = read(replay / "manifest.json")
    manifest.update(run_id="new", created_at="new-time", runtime={"platform": "new", "python": "3.13.7"})
    write(replay / "manifest.json", manifest)
    result = read(replay / "unit.json")
    result["runtime_seconds"] = 10.
    write(replay / "unit.json", result)
    refresh(replay)
    result = compare_replay(original, replay, market=False)
    assert result["cases_compared"] == 1 and result["arrays_compared"] == 2
    assert result["json_files_compared"] == 3 and result["all_bitwise_equal"]
    assert "unit.json:runtime_seconds" in result["ignored_operational_metadata_paths"]


@pytest.mark.parametrize("field,value", [("seed", 8), ("trials", [19]), ("guarantee", "none"), ("power", .6),
                                       ("interval", [.2, .9]), ("trace", [{"calendar_step": 19, "rate": .5}])])
def test_scientific_summary_changes_rejected_even_when_arrays_and_hashes_are_consistent(tmp_path, field, value):
    original, replay = fixture(tmp_path)
    result = read(replay / "unit.json")
    result[field] = value
    write(replay / "unit.json", result)
    refresh(replay)
    with pytest.raises(ValueError, match="Replay JSON"):
        compare_replay(original, replay, market=False)


def test_counterexample_output_is_compared(tmp_path):
    original, replay = fixture(tmp_path)
    write(replay / "counterexamples.json", {"bound": .8, "claim": "fixed"})
    with pytest.raises(ValueError, match="counterexamples"):
        compare_replay(original, replay, market=False)


def test_manifest_scientific_fields_and_runtime_version_are_not_ignored(tmp_path):
    original, replay = fixture(tmp_path)
    value = read(replay / "manifest.json")
    value["runtime"]["python"] = "other"
    write(replay / "manifest.json", value)
    with pytest.raises(ValueError, match="runtime.python"):
        compare_replay(original, replay, market=False)


@pytest.mark.parametrize("mutation", ["extra", "missing", "empty"])
def test_exact_case_artifact_inventory_and_nonempty_cases(tmp_path, mutation):
    original, replay = fixture(tmp_path)
    if mutation == "extra":
        np.savez(replay / "unexpected.npz", x=np.array([0.]))
    elif mutation == "missing":
        (replay / "unit.npz").unlink()
    else:
        m = read(replay / "manifest.json")
        m["spec"]["cases"], m["case_ids"], m["completed"] = [], [], []
        write(replay / "manifest.json", m)
    with pytest.raises(ValueError, match="file set|nonempty"):
        compare_replay(original, replay, market=False)


@pytest.mark.parametrize("kind", ["dtype", "event", "shape", "keys", "float"])
def test_array_changes_are_rejected(tmp_path, kind):
    original, replay = fixture(tmp_path)
    events, utility = np.array([True, False]), np.array([0., .1])
    if kind == "dtype": events = events.astype(np.uint8)
    elif kind == "event": events[0] = False
    elif kind == "shape": utility = utility[:, None]
    elif kind == "float": utility[1] += 1e-4
    if kind == "keys": np.savez(replay / "unit.npz", different=utility)
    else: np.savez(replay / "unit.npz", rejected=events, utility=utility)
    refresh(replay)
    with pytest.raises(ValueError, match="Replay .*array|Replay array"):
        compare_replay(original, replay, market=False)


def test_float_tolerance_does_not_claim_literal_bitwise_identity(tmp_path):
    original, replay = fixture(tmp_path)
    np.savez(replay / "unit.npz", rejected=np.array([True, False]), utility=np.array([-0., .1 + 1e-13]))
    refresh(replay)
    result = compare_replay(original, replay, market=False)
    assert not result["all_bitwise_equal"] and not result["all_array_values_exact"]
    assert 0 < result["largest_absolute_float_difference"] < 1e-12


def test_signed_zero_is_value_equal_but_not_element_bitwise_equal(tmp_path):
    original, replay = fixture(tmp_path)
    np.savez(replay / "unit.npz", rejected=np.array([True, False]), utility=np.array([-0., .1]))
    refresh(replay)
    result = compare_replay(original, replay, market=False)
    assert result["all_array_values_exact"] and not result["all_bitwise_equal"]


def test_nonfinite_arrays_are_rejected_even_if_both_contain_same_nan(tmp_path):
    original, replay = fixture(tmp_path)
    for root in (original, replay):
        np.savez(root / "unit.npz", rejected=np.array([True, False]), utility=np.array([np.nan, .1]))
        refresh(root)
    with pytest.raises(ValueError, match="nonfinite"):
        compare_replay(original, replay, market=False)


def test_wrong_manifest_hash_fails_before_comparison(tmp_path):
    original, replay = fixture(tmp_path)
    write(replay / "unit.json", {"replaced": True})
    with pytest.raises(ValueError, match="artifact hash"):
        compare_replay(original, replay, market=False)


def test_market_local_paths_and_audit_clock_may_change_but_full_scientific_outputs_are_checked(tmp_path):
    original, replay = fixture(tmp_path, market=True)
    p = replay / "unit/report.json"
    report = read(p)
    report["created_at"], report["audit"]["as_of"] = "new", "new"
    report["effective_settings"]["source"], report["provenance"]["local_path"] = "/new/config", "/new/data"
    write(p, report)
    refresh(replay, True)
    result = compare_replay(original, replay, market=True)
    assert result["json_files_compared"] == 4 and result["arrays_compared"] == 2
    assert "unit/report.json:audit.as_of" in result["ignored_operational_metadata_paths"]
    report["scenarios"]["25"]["initial_state"]["nav"] = 2.
    write(p, report)
    refresh(replay, True)
    with pytest.raises(ValueError, match="initial_state.nav"):
        compare_replay(original, replay, market=True)


@pytest.mark.parametrize("name,field,value", [("selections.json", "decision_time", "later-close"),
                                            ("selections.json", "selected_pair", [25, 100]),
                                            ("base-cost-trades.json", "execution_time", "later-open"),
                                            ("base-cost-trades.json", "target", .7)])
def test_market_selection_and_trade_fields_are_never_excluded(tmp_path, name, field, value):
    original, replay = fixture(tmp_path, market=True)
    path = replay / "unit" / name
    data = read(path)
    if name == "selections.json": data[0][field] = value
    else: data["adaptive"][0][field] = value
    write(path, data)
    refresh(replay, True)
    with pytest.raises(ValueError, match="Replay JSON"):
        compare_replay(original, replay, market=True)


@pytest.mark.parametrize("atol,rtol", [(-1, 0), (0, float("inf")), (True, 1e-12)])
def test_invalid_tolerances_rejected(tmp_path, atol, rtol):
    original, replay = fixture(tmp_path)
    with pytest.raises(ValueError, match="tolerance"):
        compare_replay(original, replay, market=False, atol=atol, rtol=rtol)
