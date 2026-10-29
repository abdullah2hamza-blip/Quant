import json

import pytest

from quant.ledger import Ledger
from scripts.collect_followup_results import _same, verify_followup


@pytest.mark.parametrize("kind,completed",[("smoke","2026-10-22"),("substantive",None)])
def test_smoke_or_partial_followup_cannot_enter_publication_collection(tmp_path,kind,completed):
    study = tmp_path/"study"
    study.mkdir()
    (study/"manifest.json").write_text(json.dumps({"kind":kind,"completed_at":completed}))
    with pytest.raises(ValueError,match="completed substantive"):
        verify_followup(study,tmp_path/"unused-freeze.json")


def test_summary_verifier_rejects_changed_interval_or_false_precision():
    expected = {"estimate":.25,"confidence_interval":[.2,.3],"independent_worlds":4000}
    _same(expected,expected,"example")
    with pytest.raises(ValueError,match="differs"):
        _same({**expected,"confidence_interval":[.19,.3]},expected,"example")
    with pytest.raises(ValueError,match="differs"):
        _same([0.,0.],None,"unavailable interval")


def test_rejected_collection_is_logged_without_exporting_an_accepted_registry(tmp_path,monkeypatch):
    from scripts import collect_followup_results as module
    monkeypatch.setattr(module,"ROOT",tmp_path)
    study = tmp_path/"study"
    study.mkdir()
    (study/"manifest.json").write_text(json.dumps({"kind":"smoke","completed_at":"now"}))
    output = tmp_path/"rejected"
    with pytest.raises(ValueError,match="completed substantive"):
        module.collect(study,tmp_path/"unused-freeze.json",output)
    rows = Ledger(tmp_path/"runs/research.sqlite").rows()
    assert len(rows) == 1 and rows[0]["status"] == "failed"
    assert not output.exists()
