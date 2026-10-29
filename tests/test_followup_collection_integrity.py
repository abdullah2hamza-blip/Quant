"""Receipt failures must be rejected before any world arrays are inspected.

These are intentionally tiny placeholder artifacts, never simulation results.
The final reports are invalid on purpose: reaching them reveals that the early
ledger-integrity guard failed to reject the injected inconsistency.
"""
from __future__ import annotations

from pathlib import Path
from zipfile import ZipFile

import pytest

from quant.data import digest, json_write
from quant.followup import ROOT, SPEC, load_spec
from quant.ledger import Ledger
from quant.publication import _seal
from scripts.collect_followup_results import verify_followup


def receipt_fixture(tmp_path: Path, fault: str) -> tuple[Path, Path, Ledger]:
    spec = load_spec(ROOT / SPEC)
    study = tmp_path / "study"
    study.mkdir()
    ledger = Ledger(tmp_path / "ledger.sqlite")
    code = "synthetic-frozen-code"
    freeze = tmp_path / "freeze.json"
    archive = tmp_path / "freeze.sources.zip"
    spec_bytes = (ROOT / SPEC).read_bytes()
    with ZipFile(archive, "w") as source:
        source.writestr(SPEC.as_posix(), spec_bytes)
    frozen = {
        "kind": "followup_v2_freeze",
        "code_sha256": code,
        "spec_sha256": digest(ROOT / SPEC),
        "source_snapshot": archive.name,
        "source_snapshot_sha256": digest(archive),
        "runtime": {"python": "fixture", "numpy": "fixture"},
        "documents": [],
    }
    frozen["freeze_sha256"] = _seal(frozen)
    json_write(freeze, frozen)
    parent = ledger.start(
        "followup_v2",
        {"output": str(study), "smoke": False, "freeze": str(freeze)},
        code=code if fault != "parent_code" else "another-code",
    )
    records = []
    for index, case in enumerate(spec["cases"]):
        report_file = study / (case["id"] + ".json")
        array_file = study / (case["id"] + ".npz")
        report_file.write_text("{}", encoding="utf-8")
        array_file.write_bytes(b"placeholder-not-an-NPZ")
        details = {"parent": parent, "case": case, "smoke": False}
        if index == 0 and fault == "child_case":
            details["case"] = spec["cases"][1]
        if index == 0 and fault == "child_smoke":
            details["smoke"] = True
        child = ledger.start(
            "followup_v2_case", details,
            code=code if not (index == 0 and fault == "child_code") else "another-code",
        )
        report_hash = digest(report_file)
        ledger.finish(child, "completed", {
            "report": str(report_file),
            "report_sha256": report_hash if not (index == 0 and fault == "child_report_receipt") else "0" * 64,
        })
        records.append({
            "case_id": case["id"], "attempt_id": child,
            "report_sha256": report_hash, "arrays_sha256": digest(array_file),
        })
    if fault == "duplicate_child":
        records[1]["attempt_id"] = records[0]["attempt_id"]
    manifest = {
        "run_id": parent, "kind": "substantive", "completed_at": "fixture-completed",
        "code_sha256": code, "spec_sha256": frozen["spec_sha256"], "spec": spec,
        "freeze": {"source_file": freeze.name, "file_sha256": digest(freeze), "payload": frozen},
        "runtime": {**frozen["runtime"], "platform": "fixture"}, "cases": records,
    }
    json_write(study / "manifest.json", manifest)
    ledger.finish(parent, "completed", {
        "output": str(study),
        "manifest_sha256": digest(study / "manifest.json") if fault != "parent_manifest_receipt" else "0" * 64,
    })
    return study, freeze, ledger


@pytest.mark.parametrize("fault", [
    "parent_manifest_receipt", "parent_code", "child_report_receipt",
    "child_code", "child_case", "child_smoke", "duplicate_child",
])
def test_receipt_or_case_mismatch_fails_before_reading_worlds(tmp_path, fault):
    study, freeze, ledger = receipt_fixture(tmp_path, fault)
    with pytest.raises(ValueError):
        verify_followup(study, freeze, ledger=ledger)


def test_consistent_receipts_reach_the_deliberately_invalid_report(tmp_path):
    study, freeze, ledger = receipt_fixture(tmp_path, "none")
    with pytest.raises(KeyError):
        verify_followup(study, freeze, ledger=ledger)


def test_float_summary_cannot_be_silently_replaced_by_boolean():
    from scripts.collect_followup_results import _same
    with pytest.raises(ValueError):
        _same({"estimate": True}, {"estimate": 1.0}, "fixture")


def test_flatten_preserves_raw_rate_and_unavailable_paired_interval():
    from scripts.build_followup_artifacts import flatten
    record = {
        "estimate": .125, "standard_error": .01,
        "confidence_interval": [.1, .15], "sample_degenerate": False,
    }
    absent = {"estimate": 0., "standard_error": 0., "confidence_interval": None,
              "sample_degenerate": True}
    report = {
        "case": {"id": "fixture", "effect": .05, "prefix_weak": False},
        "worlds": 4000, "steps": 800,
        "methods": {"joint_linear": {
            **{field: record for field in (
                "null_family_rejection", "first_stream_rejection",
                "restricted_first_stream_detection_time", "materiality_adjusted_paper_utility")},
            "guarantee": "fixture",
        }},
        "paired": {"joint_coherent_eb_minus_joint_local_eb": {
            "first_stream_rejection_difference": absent, "utility_difference": absent}},
        "runtime_seconds": .5, "algorithm_state_bytes": 100,
        "maximum_support_utility_observed": .5,
        **{field: record for field in (
            "cost_coverage_failure", "cost_conflict", "cost_conflict_after_final_unused_calibration")},
    }
    methods, pairs, _ = flatten({"fixture": report})
    assert methods[0]["first_stream_rejection"] == .125
    assert pairs[0]["first_stream_rejection_difference"] == 0.
    assert pairs[0]["first_stream_rejection_difference_lower"] is None
    assert pairs[0]["first_stream_rejection_difference_upper"] is None
