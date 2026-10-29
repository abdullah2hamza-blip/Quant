"""Archive corruption/relocation guards, without rerunning a research study."""
import hashlib
import json
from zipfile import ZipFile

import pytest

from quant.data import digest, json_write
from quant.ledger import Ledger
from scripts.package_replication import completed_report, safe_member, verify_archive


def write_fixture(path, *, payload=b"frozen bytes", expected=b"frozen bytes", extra=False):
    manifest = {"files":{"source.txt":{"bytes":len(expected),"sha256":hashlib.sha256(expected).hexdigest()}}}
    with ZipFile(path,"w") as zipped:
        zipped.writestr("source.txt",payload)
        zipped.writestr("REPLICATION-MANIFEST.json",json.dumps(manifest))
        if extra:
            zipped.writestr("unlisted.txt",b"extra")


def test_verified_archive_extracts_exact_bytes_and_preserves_existing_destination(tmp_path):
    archive,destination = tmp_path/"package.zip",tmp_path/"copy"
    write_fixture(archive)
    receipt = verify_archive(archive,extract=destination)
    assert receipt["files_verified"]==1
    assert (destination/"source.txt").read_bytes()==b"frozen bytes"
    with pytest.raises(ValueError,match="destination exists"):
        verify_archive(archive,extract=destination)


@pytest.mark.parametrize("corruption",["checksum","inventory"])
def test_corruption_rejected_before_extraction(tmp_path,corruption):
    archive,destination = tmp_path/"package.zip",tmp_path/"copy"
    write_fixture(archive,payload=b"changed" if corruption=="checksum" else b"frozen bytes",extra=corruption=="inventory")
    with pytest.raises(ValueError,match="checksum|inventory"):
        verify_archive(archive,extract=destination)
    assert not destination.exists()


@pytest.mark.parametrize("name",["../escape","a/../../escape","/absolute","C:/escape","a\\escape","a//b","./a"])
def test_unsafe_names_rejected(name):
    assert not safe_member(name)


def test_duplicate_members_rejected(tmp_path):
    archive = tmp_path/"duplicate.zip"
    write_fixture(archive)
    with pytest.warns(UserWarning,match="Duplicate"):
        with ZipFile(archive,"a") as zipped:
            zipped.writestr("source.txt",b"second")
    with pytest.raises(ValueError,match="duplicate"):
        verify_archive(archive)


def test_completed_receipt_requires_ledger_bound_bytes(tmp_path):
    ledger = Ledger(tmp_path/"ledger.sqlite")
    identifier = ledger.start("reproduction",{})
    path = tmp_path/"report.json"
    source = tmp_path/"workflow.sources.zip"
    with ZipFile(source,"w") as archive:
        archive.writestr("fixture.txt",b"frozen source")
    common = {"attempt_id":identifier,"mode":"fixture","workflow_source":{"path":source.name,"sha256":digest(source)}}
    json_write(path,{**common,"finished_at":"recorded"})
    with pytest.raises(ValueError,match="completed reproduction"):
        completed_report(path,ledger,kind="reproduction",mode="fixture")
    ledger.finish(identifier,"completed",{"report_sha256":digest(path)})
    assert completed_report(path,ledger,kind="reproduction",mode="fixture")["attempt_id"]==identifier
    json_write(path,{**common,"finished_at":"changed"})
    with pytest.raises(ValueError,match="completed reproduction"):
        completed_report(path,ledger,kind="reproduction",mode="fixture")
