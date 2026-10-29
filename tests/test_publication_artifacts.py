import json
from pathlib import Path
import shutil

import numpy as np
import pytest

from scripts.build_publication_artifacts import numerical_identity, verify_results
from scripts.collect_publication_results import collect
from scripts.reproduce_publication import prepare_frozen_source
from quant.ledger import Ledger, code_hash
from tests.factories import ROOT


RESULTS = ROOT / "results/publication-v1"


def test_preserved_substantive_results_cover_every_registered_case_and_method():
    registry, manifest, simulations, markets = verify_results(RESULTS)
    assert len(simulations) == 24 and len(markets) == 6
    assert all(r["worlds"] == 4000 for r in simulations.values())
    assert all(len(r["methods"]) == 9 for r in simulations.values())
    assert registry["simulation_run_id"] == manifest["run_id"]


def test_result_display_rejects_tampered_source_archive(tmp_path):
    target = tmp_path / "results"
    shutil.copytree(RESULTS,target)
    archive = next((target / "source-snapshots").glob("*baseline*.zip"))
    archive.write_bytes(archive.read_bytes() + b"changed")
    with pytest.raises(ValueError,match="source integrity"):
        verify_results(target)


def test_result_display_rejects_a_changed_case_even_if_json_is_parseable(tmp_path):
    target = tmp_path / "results"
    shutil.copytree(RESULTS,target)
    case = target / "simulation/null_no_overlap.json"
    values = json.loads(case.read_text())
    values["worlds"] = 1
    case.write_text(json.dumps(values))
    with pytest.raises(ValueError,match="artifact hash|result hash"):
        verify_results(target)


def test_numerical_identity_does_not_turn_roundoff_signs_into_economic_crossings():
    assert numerical_identity(np.asarray([-1e-16, 1e-16, 0]))
    assert not numerical_identity(np.asarray([-1e-4, 1e-4, 0]))


def test_frozen_replay_reconstructs_original_code_without_current_helpers(tmp_path):
    freeze, payload = prepare_frozen_source(ROOT,RESULTS,"simulation",tmp_path / "source")
    assert code_hash(tmp_path / "source") == payload["code_sha256"]
    assert freeze.exists()
    assert not (tmp_path / "source/scripts/reproduce_publication.py").exists()


def test_collection_logs_a_late_export_failure_instead_of_claiming_success(tmp_path, monkeypatch):
    ledger_file = tmp_path / "ledger.sqlite"
    shutil.copy2(RESULTS / "research.sqlite",ledger_file)
    ledger = Ledger(ledger_file)
    from scripts import collect_publication_results as module
    original = module.json_write
    def fail_export(path,value):
        if path.name == "attempt-ledger.json":
            raise OSError("injected export failure")
        return original(path,value)
    monkeypatch.setattr(module,"json_write",fail_export)
    with pytest.raises(OSError,match="injected export failure"):
        collect(RESULTS / "simulation",RESULTS / "market",RESULTS / "source-snapshots/publication-baseline-freeze-v1.json",
                RESULTS / "source-snapshots/market-freeze-v1.json",tmp_path / "partial",ledger,ROOT)
    latest = [r for r in ledger.rows() if r["kind"] == "publication_result_collection"][-1]
    assert latest["status"] == "failed"
    assert "injected export failure" in latest["details"]["outcome"]["error"]
