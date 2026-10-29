"""Small integration-guard fixtures, never study simulations or live results."""
from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from zipfile import ZipFile

import numpy as np
import pytest

from quant.data import digest, json_write
from quant.ledger import Ledger
from scripts import reproduce_complete_study as master
from scripts import verify_followup_replay as comparator


def replay_pair(tmp_path, monkeypatch):
    folders = [tmp_path / name for name in ("original", "replayed")]
    for index, folder in enumerate(folders):
        folder.mkdir()
        arrays = folder / "fixture.npz"
        np.savez_compressed(arrays, hits=np.array([True, False]),
                            first_crossing=np.array([1, 801], dtype=np.int64),
                            utility=np.array([.125, -.25]))
        report = {"runtime_seconds": float(index + 1), "arrays_sha256": digest(arrays),
                  "guarantee": "fixture conditional null only",
                  "metric": {"estimate": .125, "confidence_interval": [.1, .15]},
                  "trace": [{"label": 1, "calibration_n": 32}]}
        json_write(folder / "fixture.json", report)
        manifest = {
            "run_id": f"run-{index}", "created_at": f"created-{index}",
            "completed_at": f"finished-{index}",
            "runtime": {"python": "fixture", "numpy": "fixture", "platform": f"host-{index}"},
            "code_sha256": "same-source", "spec_sha256": "same-spec",
            "freeze": {"file_sha256": "same-freeze"},
            "spec": {"cases": [{"id": "fixture", "effect": .05}]},
            "cases": [{"case_id": "fixture", "attempt_id": f"case-{index}",
                       "report_sha256": digest(folder / "fixture.json"),
                       "arrays_sha256": digest(arrays)}],
        }
        json_write(folder / "manifest.json", manifest)
    calls = []
    def verified(path, freeze, *, ledger=None):
        # Structural/hash/receipt validation is tested independently. Here the
        # narrow comparison must enforce every field outside its exclusions.
        calls.append((path, ledger))
        return json.loads((path / "manifest.json").read_text()), {}, {}
    monkeypatch.setattr(comparator, "verify_followup", verified)
    return *folders, tmp_path / "freeze.json", tmp_path / "replay.sqlite", calls


def test_followup_replay_excludes_only_expected_operational_changes(tmp_path, monkeypatch):
    left, right, freeze, ledger, calls = replay_pair(tmp_path, monkeypatch)
    result = comparator.compare_followup(left, right, freeze, replay_ledger=ledger)
    assert result["cases_compared"] == 1
    assert result["arrays_compared"] == 3
    assert result["json_files_compared"] == 2
    assert result["all_array_values_exact"] and result["all_bitwise_equal"]
    assert calls[0][1] is None and isinstance(calls[1][1], Ledger)
    ignored = result["ignored_operational_metadata_paths"]
    assert "fixture.json:runtime_seconds" in ignored
    assert "manifest.json:cases.0.attempt_id" in ignored
    assert not any("guarantee" in item or "trace" in item for item in ignored)


@pytest.mark.parametrize("fault", ["source", "effect", "guarantee", "interval", "trace"])
def test_followup_replay_keeps_scientific_json_fields_strict(tmp_path, monkeypatch, fault):
    left, right, freeze, ledger, _ = replay_pair(tmp_path, monkeypatch)
    filename = "manifest.json" if fault in ("source", "effect") else "fixture.json"
    saved = json.loads((right / filename).read_text())
    if fault == "source":
        saved["code_sha256"] = "different-source"
    elif fault == "effect":
        saved["spec"]["cases"][0]["effect"] = .02
    elif fault == "guarantee":
        saved["guarantee"] = "incorrect unconditional guarantee"
    elif fault == "interval":
        saved["metric"]["confidence_interval"][0] = .09
    else:
        saved["trace"][0]["label"] = 2
    json_write(right / filename, saved)
    with pytest.raises(ValueError):
        comparator.compare_followup(left, right, freeze, replay_ledger=ledger)


@pytest.mark.parametrize("fault", ["dtype", "crossing", "truth"])
def test_followup_replay_requires_exact_event_time_and_dtype(tmp_path, monkeypatch, fault):
    left, right, freeze, ledger, _ = replay_pair(tmp_path, monkeypatch)
    with np.load(right / "fixture.npz") as saved:
        arrays = {key: saved[key] for key in saved.files}
    if fault == "dtype":
        arrays["first_crossing"] = arrays["first_crossing"].astype(np.int32)
    elif fault == "crossing":
        arrays["first_crossing"][0] = 2
    else:
        arrays["hits"][1] = True
    np.savez_compressed(right / "fixture.npz", **arrays)
    with pytest.raises(ValueError):
        comparator.compare_followup(left, right, freeze, replay_ledger=ledger)


@pytest.mark.parametrize("tolerance", [-1., float("inf"), float("nan"), True])
def test_followup_replay_rejects_invalid_tolerance_before_reading(tmp_path, tolerance):
    with pytest.raises(ValueError, match="tolerances"):
        comparator.compare_followup(tmp_path / "left", tmp_path / "right", tmp_path / "freeze",
                                    replay_ledger=tmp_path / "ledger", atol=tolerance)


def baseline_receipt(tmp_path, fault="none"):
    baseline, previous = tmp_path / "baseline", tmp_path / "previous"
    baseline.mkdir()
    previous.mkdir()
    registry = {"simulation": "simulation", "market": "market"}
    json_write(baseline / "registry.json", registry)
    ledger = Ledger(tmp_path / "ledger.sqlite")
    identifier = ledger.start("publication_reproduction", {"full": True}, code="fixture")
    source = previous / "workflow.sources.zip"
    source.write_bytes(b"fictional workflow archive")
    report = {
        "attempt_id": identifier, "finished_at": "fixture-completed",
        "mode": "full frozen compute replay", "input_registry_sha256": digest(baseline / "registry.json"),
        "workflow_source": {"path": source.name, "sha256": digest(source)},
    }
    if fault == "wrong_mode":
        report["mode"] = "rebuild from preserved substantive results"
    report_path = previous / "reproduction.json"
    json_write(report_path, report)
    if fault != "unfinished":
        ledger.finish(identifier, "completed", {"report_sha256": digest(report_path)})
    for key in ("simulation", "market"):
        (previous / (key + "-replay") / "fixture-run").mkdir(parents=True)
    if fault == "changed_report":
        report["finished_at"] = "changed-after-completion"
        json_write(report_path, report)
    elif fault == "changed_registry":
        json_write(baseline / "registry.json", {**registry, "changed": True})
    elif fault == "changed_archive":
        source.write_bytes(b"changed workflow archive")
    elif fault == "ambiguous_output":
        (previous / "market-replay" / "another-run").mkdir()
    return previous, baseline, registry, ledger


@pytest.mark.parametrize("fault", [
    "wrong_mode", "unfinished", "changed_report", "changed_registry", "changed_archive", "ambiguous_output",
])
def test_baseline_cache_requires_bound_full_receipt_and_unambiguous_outputs(tmp_path, monkeypatch, fault):
    previous, baseline, registry, ledger = baseline_receipt(tmp_path, fault)
    monkeypatch.setattr(master, "compare_replay", lambda *args, **kwargs: {"fixture": True})
    with pytest.raises(ValueError):
        master.reverify_baseline(previous, baseline, registry, ledger)


def test_valid_baseline_cache_is_recompared_for_both_studies(tmp_path, monkeypatch):
    previous, baseline, registry, ledger = baseline_receipt(tmp_path)
    calls = []
    def compare(left, right, *, market):
        calls.append((left, right, market))
        return {"fixture": True}
    monkeypatch.setattr(master, "compare_replay", compare)
    report = master.reverify_baseline(previous, baseline, registry, ledger)
    assert [entry[2] for entry in calls] == [False, True]
    assert "no new baseline computation" in report["kind"]
    assert report["original_report_sha256"] == digest(previous / "reproduction.json")


@pytest.mark.parametrize("full,verify_only,reuse", [(True, True, None), (False, False, "cached")])
def test_invalid_master_modes_record_failure_without_creating_output(tmp_path, monkeypatch, full, verify_only, reuse):
    monkeypatch.setattr(master, "ROOT", tmp_path)
    output = tmp_path / "output"
    with pytest.raises(ValueError):
        master.reproduce(output, full=full, verify_only=verify_only,
                         reuse_baseline=tmp_path / reuse if reuse else None)
    rows = Ledger(tmp_path / "runs/research.sqlite").rows()
    assert len(rows) == 1 and rows[0]["status"] == "failed"
    assert rows[0]["kind"] == "complete_publication_reproduction"
    assert not output.exists()


def test_wrong_compiler_version_fails_at_preflight(tmp_path, monkeypatch):
    calls = []
    def version(command, **kwargs):
        calls.append((command, kwargs))
        return SimpleNamespace(stdout="Tectonic 0.16.0\n")
    monkeypatch.setattr(master.subprocess, "run", version)
    with pytest.raises(ValueError, match="0.17.0"):
        master.compiler_path(str(tmp_path / "fixture-tectonic.exe"))
    assert calls[0][0][-1] == "--version" and calls[0][1]["check"] is True


def test_manuscript_staging_uses_exact_archived_paper_and_bibliography(tmp_path):
    snapshot = tmp_path / "workflow.zip"
    entries = {
        "paper/main.tex": b"archived-main",
        "paper/sections/methods.tex": b"archived-methods",
        "paper/images/fixture.bin": b"\x00\x01\x02",
        "docs/publication/bibliography.json": b'{"archived":true}',
        "docs/unrelated.txt": b"not manuscript input",
    }
    with ZipFile(snapshot, "w") as archive:
        for name, content in entries.items():
            archive.writestr(name, content)
    paper, bibliography = tmp_path / "staged-paper", tmp_path / "bib.json"
    master.stage_manuscript(snapshot, paper, bibliography)
    assert (paper / "main.tex").read_bytes() == entries["paper/main.tex"]
    assert (paper / "sections/methods.tex").read_bytes() == entries["paper/sections/methods.tex"]
    assert (paper / "images/fixture.bin").read_bytes() == entries["paper/images/fixture.bin"]
    assert bibliography.read_bytes() == entries["docs/publication/bibliography.json"]
    assert not (paper / "docs").exists()


def test_manuscript_staging_rejects_archive_path_escape(tmp_path):
    snapshot = tmp_path / "unsafe.zip"
    with ZipFile(snapshot, "w") as archive:
        archive.writestr("paper/main.tex", b"main")
        archive.writestr("paper/../escape.tex", b"must not be written")
        archive.writestr("docs/publication/bibliography.json", b"{}")
    with pytest.raises(ValueError, match="Unsafe manuscript"):
        master.stage_manuscript(snapshot, tmp_path / "paper", tmp_path / "bib.json")
    assert not (tmp_path / "escape.tex").exists()


def data_staging_fixture(tmp_path, monkeypatch):
    root = tmp_path / "repository"
    source = root / "data/processed/fixture.csv"
    manifest = root / "data/processed/fixture.manifest.json"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"fixture,original\n")
    manifest.write_bytes(b'{"fixture":true}')
    raw = root / "data/raw/fixture.zip"
    raw.parent.mkdir(parents=True)
    raw.write_bytes(b"fixture immutable raw bytes")
    baseline = tmp_path / "preserved"
    baseline.mkdir()
    frozen = {"inputs": [{"kind": kind, "path": path.relative_to(root).as_posix(), "sha256": digest(path)}
                          for kind, path in (("csv", source), ("manifest", manifest))]}
    json_write(baseline / "freeze.json", frozen)
    registry = {"source_freezes": {"market": "freeze.json"}}
    monkeypatch.setattr(master, "ROOT", root)
    return root, baseline, registry, tmp_path / "inputs"


def test_data_staging_copies_only_hash_matching_input_and_raw_bytes(tmp_path, monkeypatch):
    root, baseline, registry, destination = data_staging_fixture(tmp_path, monkeypatch)
    master.stage_data(baseline, registry, destination)
    for name in ("data/processed/fixture.csv", "data/processed/fixture.manifest.json", "data/raw/fixture.zip"):
        assert digest(root / name) == digest(destination / name)


def test_data_staging_rejects_changed_source_before_copy(tmp_path, monkeypatch):
    root, baseline, registry, destination = data_staging_fixture(tmp_path, monkeypatch)
    (root / "data/processed/fixture.csv").write_bytes(b"changed")
    with pytest.raises(ValueError, match="before immutable staging"):
        master.stage_data(baseline, registry, destination)
    assert not (destination / "data/processed/fixture.csv").exists()


def test_data_staging_rejects_copy_changed_in_transit(tmp_path, monkeypatch):
    _, baseline, registry, destination = data_staging_fixture(tmp_path, monkeypatch)
    copy_file = master.shutil.copy2
    def damaged_copy(source, target):
        copied = copy_file(source, target)
        if Path(target).suffix == ".csv":
            Path(target).write_bytes(b"injected copy damage")
        return copied
    monkeypatch.setattr(master.shutil, "copy2", damaged_copy)
    with pytest.raises(ValueError, match="during immutable staging"):
        master.stage_data(baseline, registry, destination)
