import json
from pathlib import Path

import numpy as np
import pytest
from zipfile import ZipFile

from quant.cost_evidence import bounded_cost_interval
from quant.ledger import Ledger
from quant.publication import METHODS, _calibration_bounds, check_study_freeze, freeze_study, load_spec, mean_interval, run_study, simulate_case, wilson
from tests.factories import ROOT


SPEC = ROOT / "configs/research/publication-study-v1.json"


def test_vectorized_calibration_equals_analytical_scalar_intervals():
    totals = np.array([0., .2, 7.2, 9.8, 10.])
    lower, upper = _calibration_bounds(totals, 50, .2, .01)
    for i, total in enumerate(totals):
        expected = bounded_cost_interval(float(total), 50, .2, .01)
        assert lower[i] == pytest.approx(expected.lower)
        assert upper[i] == pytest.approx(expected.upper)


def test_smoke_has_world_level_truth_and_pathwise_domination():
    s = load_spec(SPEC)
    result, arrays = simulate_case(s, s["cases"][4], worlds=64, calendar_steps=60)
    assert result["pathwise_event_inclusion_violations"] == 0
    assert arrays["rejected"].shape == (len(METHODS), 64, 10)
    np.testing.assert_array_equal(arrays["null_at_birth"][0], np.arange(10) % 2 == 1)
    assert not np.any(arrays["rejected"][2] & ~arrays["rejected"][1])
    for method, summary in result["methods"].items():
        assert summary["null_family_rejection"]["independent_worlds"] == 64
        if method in ("plugin_linear", "symmetric_upper_linear", "naive_peek_hoeffding"):
            assert summary["guarantee"].startswith("none:")


def test_delay_reduces_matured_observations_at_fixed_calendar_horizon():
    s = load_spec(SPEC)
    delayed = {"id": "test_delay", "effect": 0., "overlap": .5, "label_delay": 4}
    result, arrays = simulate_case(s, delayed, worlds=32, calendar_steps=61)
    assert result["matured_trials_by_hypothesis"] == [12] * 10
    times = arrays["first_crossing"]
    observed = times <= 61
    assert np.all(times[observed] % 5 == 0)


def test_births_start_with_fresh_evidence_and_select_without_replacement():
    s = load_spec(SPEC)
    case = {"id": "test_birth", "effect": .05, "overlap": .5, "adaptive_births": 5}
    result, arrays = simulate_case(s, case, worlds=32, calendar_steps=60)
    assert result["matured_trials_by_hypothesis"] == [60, 48, 36, 24, 12]
    selected = arrays["candidate_selected_at_birth"]
    assert all(len(set(row)) == 5 for row in selected)
    times = arrays["first_crossing"]
    for j in range(5):
        assert np.all(times[:, :, j] > j * 12)


def test_seeded_world_outcomes_repeat_exactly():
    s = load_spec(SPEC)
    a, aa = simulate_case(s, s["cases"][0], worlds=32, calendar_steps=25)
    b, bb = simulate_case(s, s["cases"][0], worlds=32, calendar_steps=25)
    assert a["methods"] == b["methods"]
    for key in aa:
        np.testing.assert_array_equal(aa[key], bb[key])


def test_equal_turnover_cancels_shared_cost_uncertainty_exactly():
    s = load_spec(SPEC)
    result, arrays = simulate_case(s, s["cases"][8], worlds=32, calendar_steps=30)
    np.testing.assert_array_equal(arrays["rejected"][0], arrays["rejected"][1])
    np.testing.assert_array_equal(arrays["first_crossing"][0], arrays["first_crossing"][1])


def test_zero_events_do_not_imply_zero_monte_carlo_uncertainty():
    s = load_spec(SPEC)
    result, _ = simulate_case(s, s["cases"][0], worlds=32, calendar_steps=20)
    paired = result["paired_method_comparisons"]["first_stream_joint_minus_separate_rejection_rate"]
    assert paired["estimate"] == 0 and paired["confidence_interval"][1] > 0
    degenerate = mean_interval(np.zeros(100))
    assert degenerate["sample_degenerate"] and degenerate["confidence_interval"] is None


def test_wilson_uses_worlds_and_has_nonzero_upper_bound_for_zero_events():
    r = wilson(np.zeros(100, dtype=bool))
    assert r["estimate"] == 0 and 0 < r["confidence_interval"][1] < .05
    with pytest.raises(ValueError):
        wilson(np.zeros((2, 100)))


def test_study_records_smoke_artifacts_hashes_and_case_attempts(tmp_path):
    ledger = Ledger(tmp_path / "ledger.sqlite")
    result = run_study(SPEC, tmp_path / "study", ledger, ROOT, smoke=True, case_id="null_half_overlap")
    folder = Path(result["output"])
    manifest = json.loads((folder / "manifest.json").read_text())
    assert manifest["kind"] == "smoke"
    assert manifest["completed"][0]["id"] == "null_half_overlap"
    assert (folder / "null_half_overlap.npz").exists()
    attempts = ledger.rows()
    assert len(attempts) == 2 and all(x["status"] == "completed" for x in attempts)


def test_missing_case_is_a_failed_attempt(tmp_path):
    ledger = Ledger(tmp_path / "ledger.sqlite")
    with pytest.raises(ValueError, match="absent"):
        run_study(SPEC, tmp_path / "study", ledger, ROOT, smoke=True, case_id="missing")
    assert ledger.rows()[0]["status"] == "failed"


@pytest.mark.parametrize("mutation", ["unknown_top", "unknown_case", "unsafe_id", "invalid_shift", "boolean_count"])
def test_study_configuration_rejects_silent_design_changes(tmp_path, mutation):
    spec = json.loads(SPEC.read_text())
    if mutation == "unknown_top":
        spec["effectt"] = 1
    elif mutation == "unknown_case":
        spec["cases"][0]["overlapp"] = 1
    elif mutation == "unsafe_id":
        spec["cases"][0]["id"] = "../outside"
    elif mutation == "invalid_shift":
        spec["cases"][0]["cost_shift"] = .18
    else:
        spec["worlds"] = True
    path = tmp_path / "invalid.json"
    path.write_text(json.dumps(spec))
    with pytest.raises(ValueError):
        load_spec(path)


def test_substantive_study_requires_a_freeze_and_failure_is_retained(tmp_path):
    ledger = Ledger(tmp_path / "ledger.sqlite")
    with pytest.raises(ValueError, match="requires"):
        run_study(SPEC, tmp_path / "study", ledger, ROOT)
    assert ledger.rows()[0]["status"] == "failed"


def test_study_freeze_pins_source_spec_review_protocol_and_runtime(tmp_path, monkeypatch):
    root = tmp_path / "project"
    (root / "src").mkdir(parents=True)
    source = root / "src/model.py"
    source.write_text("x = 1\n")
    original_source = source.read_bytes()
    protocol = root / "protocol.md"
    protocol.write_text("Prespecified study\n")
    reviews = root / "docs/publication/reviews"
    reviews.mkdir(parents=True)
    for name in ("mathematical-design-01.md", "cost-primitives-01.md", "simulation-runner-01.md"):
        (reviews / name).write_text("Unit-test fixture; this is not an actual scientific review\n")
    spec = root / "study.json"
    spec.write_bytes(SPEC.read_bytes())
    ledger = Ledger(tmp_path / "ledger.sqlite")
    freeze = tmp_path / "freeze.json"
    freeze_study(spec, protocol, freeze, ledger, root)
    assert check_study_freeze(freeze, spec, root)["kind"] == "publication_simulation_freeze"
    with ZipFile(freeze.with_suffix(".sources.zip")) as archive:
        assert archive.read("src/model.py") == original_source
        assert all(not name.startswith(("data/", "runs/", ".git/")) for name in archive.namelist())
    source.write_text("x = 2\n")
    with pytest.raises(ValueError, match="code_sha256"):
        check_study_freeze(freeze, spec, root)
    source.write_text("x = 1\n")
    protocol.write_text("Changed protocol\n")
    with pytest.raises(ValueError, match="document changed"):
        check_study_freeze(freeze, spec, root)
    protocol.write_text("Prespecified study\n")
    with monkeypatch.context() as m:
        m.setattr("quant.publication.platform.python_version", lambda: "changed")
        with pytest.raises(ValueError, match="runtime"):
            check_study_freeze(freeze, spec, root)
    payload = json.loads(freeze.read_text())
    payload["spec_sha256"] = "tampered"
    freeze.write_text(json.dumps(payload))
    with pytest.raises(ValueError, match="integrity"):
        check_study_freeze(freeze, spec, root)
