"""Portable archive/final-paper gates using fictional artifacts only.

Some guards intentionally expose the pre-review package-helper findings. The
helper may only be repaired after the live reproduction source guard ends.
No test starts a study or modifies the frozen scientific implementation.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from zipfile import ZipFile

import pytest

from quant.data import digest, json_write
from quant.ledger import Ledger, code_hash
from scripts import package_replication as package


def archive_fixture(path, entries):
    manifest = {"files": {name: {"bytes": len(payload), "sha256": hashlib.sha256(payload).hexdigest()}
                          for name, payload in entries.items()}}
    with ZipFile(path, "w") as archive:
        for name, payload in entries.items():
            archive.writestr(name, payload)
        archive.writestr("REPLICATION-MANIFEST.json", json.dumps(manifest))


@pytest.mark.parametrize("name", [
    "CON", "con.txt", "folder/NUL.csv", "aux.txt", "COM1", "lpt9.log",
    "trailing.", "trailing ", "folder./file.txt", "folder /file.txt",
])
def test_nonportable_windows_device_or_normalized_names_are_rejected(name):
    assert not package.safe_member(name)


@pytest.mark.parametrize("names", [
    ("A.txt", "a.txt"), ("Directory/source.txt", "directory/SOURCE.txt"),
    ("file", "file/child.txt"),
])
def test_alias_or_file_directory_collision_rejected_before_extraction(tmp_path, names):
    archive = tmp_path / "ambiguous.zip"
    destination = tmp_path / "extracted"
    archive_fixture(archive, {names[0]: b"first", names[1]: b"second"})
    with pytest.raises(ValueError):
        package.verify_archive(archive, extract=destination)
    assert not destination.exists()


def test_written_extraction_bytes_are_checked_not_only_zip_payloads(tmp_path, monkeypatch):
    archive, destination = tmp_path / "fixture.zip", tmp_path / "extracted"
    archive_fixture(archive, {"source.txt": b"expected exact bytes"})
    original_write = Path.write_bytes
    def damaged_write(path, payload):
        if path == destination / "source.txt":
            return original_write(path, b"injected write corruption")
        return original_write(path, payload)
    monkeypatch.setattr(Path, "write_bytes", damaged_write)
    with pytest.raises(ValueError):
        package.verify_archive(archive, extract=destination)


def two_page_pdf():
    """A minimal valid two-page PDF; no PDF/plotting dependency needed here."""
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R 4 0 R] /Count 2 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 100 100] /Resources << >> /Contents 5 0 R >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 100 100] /Resources << >> /Contents 5 0 R >>",
        b"<< /Length 0 >>\nstream\n\nendstream",
    ]
    data = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for index, obj in enumerate(objects, 1):
        offsets.append(len(data))
        data.extend(f"{index} 0 obj\n".encode() + obj + b"\nendobj\n")
    xref = len(data)
    data.extend(f"xref\n0 {len(offsets)}\n0000000000 65535 f \n".encode())
    for offset in offsets[1:]:
        data.extend(f"{offset:010d} 00000 n \n".encode())
    data.extend(f"trailer\n<< /Size {len(offsets)} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode())
    return bytes(data)


def package_fixture(tmp_path, monkeypatch, *, inspected_pages=2, cached_baseline=False):
    root = tmp_path / "project"
    root.mkdir()
    monkeypatch.setattr(package, "ROOT", root)
    monkeypatch.setattr(package, "verify_results", lambda path: None)
    monkeypatch.setattr(package, "verify_collection", lambda path: None)
    for name in ("publication-v1", "publication-v2"):
        path = root / "results" / name
        path.mkdir(parents=True)
        json_write(path / "registry.json", {"fictional": name})
    pdf = root / "output/pdf/cost-aware-bitcoin-research.pdf"
    pdf.parent.mkdir(parents=True)
    pdf.write_bytes(two_page_pdf())
    live_paper = root / "paper"
    live_paper.mkdir()
    (live_paper / "main.tex").write_bytes(b"later-edited live source")
    (live_paper / "uncompiled-extra.tex").write_bytes(b"not part of final compiled source")
    full, rebuild = tmp_path / "completed-full", tmp_path / "completed-rebuild"
    full.mkdir()
    rebuild.mkdir()
    staged = rebuild / "paper"
    staged.mkdir()
    (staged / "main.tex").write_bytes(b"actual final rebuild source")
    (staged / "generated").mkdir()
    (staged / "generated/numbers.tex").write_bytes(b"actual final rebuild numbers")
    (staged / "generated/followup").mkdir()
    (staged / "generated/followup/numbers.tex").write_bytes(b"actual final followup numbers")
    (staged / "main.log").write_bytes(b"transient TeX log")
    (staged / "references.tex").write_bytes(b"regenerated references")
    (staged / "references.bib").write_bytes(b"regenerated BibTeX")
    bibliography_source = b'{"records":[]}'
    bibliography = {
        "source_sha256": hashlib.sha256(bibliography_source).hexdigest(), "records": 0, "keys": [],
        "output_sha256": {name: digest(staged / name) for name in ("references.tex", "references.bib")},
    }
    json_write(staged / "bibliography-manifest.json", bibliography)
    displays = {
        "input_registry_sha256": digest(root / "results/publication-v1/registry.json"),
        "output_sha256": {"numbers.tex": digest(staged / "generated/numbers.tex")},
    }
    followup_displays = {
        "input_registry_sha256": digest(root / "results/publication-v2/registry.json"),
        "output_sha256": {"numbers.tex": digest(staged / "generated/followup/numbers.tex")},
    }
    json_write(staged / "generated/traceability.json", displays)
    json_write(staged / "generated/followup/traceability.json", followup_displays)
    inputs = {"main.tex": (staged / "main.tex").read_bytes(),
              "references.tex": b"input references before regeneration",
              "references.bib": b"input BibTeX before regeneration",
              "bibliography-manifest.json": b"{}"}
    ledger = Ledger(root / "runs/research.sqlite")
    common = {
        "finished_at": "fictional-completed",
        "baseline_registry_sha256": digest(root / "results/publication-v1/registry.json"),
        "followup_registry_sha256": digest(root / "results/publication-v2/registry.json"),
    }
    cached_receipt = None
    if cached_baseline:
        previous = tmp_path / "completed-baseline"
        previous.mkdir()
        source = previous / "workflow.sources.zip"
        with ZipFile(source, "w") as archive:
            archive.writestr("paper/main.tex", b"previous baseline input")
        cached_id = ledger.start("publication_reproduction", {"full": True}, code=code_hash(root))
        cached_report = {
            "attempt_id": cached_id, "finished_at": "fictional-previous-completion",
            "mode": "full frozen compute replay",
            "input_registry_sha256": common["baseline_registry_sha256"],
            "workflow_source": {"path": source.name, "sha256": digest(source), "code_sha256_at_start": code_hash(root)},
        }
        cached_path = previous / "reproduction.json"
        json_write(cached_path, cached_report)
        ledger.finish(cached_id, "completed", {"report_sha256": digest(cached_path)})
        cached_receipt = {"original_report": str(cached_path), "original_report_sha256": digest(cached_path),
                          "original_attempt_id": cached_id, "original_finished_at": cached_report["finished_at"]}
    for folder, mode in ((full, "full frozen replay and paper rebuild"),
                         (rebuild, "paper rebuild from preserved substantive results")):
        source = folder / "workflow.sources.zip"
        with ZipFile(source, "w") as archive:
            for name, payload in inputs.items():
                archive.writestr("paper/" + name, payload)
            archive.writestr("docs/publication/bibliography.json", bibliography_source)
        identifier = ledger.start("complete_publication_reproduction", {"output": str(folder)}, code=code_hash(root))
        report = {**common, "attempt_id": identifier, "mode": mode,
                  "followup_replay": {"cases_compared": 25}, "pdf": {"path": str(pdf), "sha256": digest(pdf)},
                  "workflow_source": {"path": source.name, "sha256": digest(source), "code_sha256_at_start": code_hash(root)},
                  "manuscript_inputs": {name: hashlib.sha256(payload).hexdigest() for name, payload in inputs.items()},
                  "bibliography_input_sha256": hashlib.sha256(bibliography_source).hexdigest(),
                  "bibliography": bibliography, "baseline_displays": displays,
                  "followup_displays": followup_displays}
        if folder == full and cached_receipt:
            report["baseline_replay"] = cached_receipt
        json_write(folder / "reproduction.json", report)
        ledger.finish(identifier, "completed", {"report_sha256": digest(folder / "reproduction.json")})
    qa = tmp_path / "outside-project-qa.json"
    json_write(qa, {
        "pages_rendered": inspected_pages,
        "pages_visually_inspected": list(range(1, inspected_pages + 1)),
        "observed_layout_defects": [], "pdf_sha256": digest(pdf),
    })
    return root, full, rebuild, qa, tmp_path / "package.zip"


def test_partial_page_inspection_cannot_be_called_complete(tmp_path, monkeypatch):
    _, full, rebuild, qa, output = package_fixture(tmp_path, monkeypatch, inspected_pages=1)
    with pytest.raises(ValueError):
        package.create(output, full=full, rebuild=rebuild, qa=qa)
    assert not output.exists()


def test_package_uses_final_rebuild_paper_and_retains_explicit_qa_record(tmp_path, monkeypatch):
    _, full, rebuild, qa, output = package_fixture(tmp_path, monkeypatch)
    package.create(output, full=full, rebuild=rebuild, qa=qa)
    with ZipFile(output) as archive:
        assert archive.read("paper/main.tex") == (rebuild / "paper/main.tex").read_bytes()
        assert archive.read("paper/generated/numbers.tex") == (rebuild / "paper/generated/numbers.tex").read_bytes()
        assert "paper/uncompiled-extra.tex" not in archive.namelist()
        assert "paper/main.log" not in archive.namelist()
        assert archive.read("provenance/pdf-qa-final.json") == qa.read_bytes()


def test_changed_staged_manuscript_cannot_override_completed_rebuild_receipt(tmp_path, monkeypatch):
    _, full, rebuild, qa, output = package_fixture(tmp_path, monkeypatch)
    (rebuild / "paper/main.tex").write_bytes(b"changed after the completed rebuild")
    with pytest.raises(ValueError):
        package.create(output, full=full, rebuild=rebuild, qa=qa)
    assert not output.exists()


@pytest.mark.parametrize("fault", ["source_archive", "generated_export", "trace_receipt", "reference_export"])
def test_changed_rebuild_source_or_export_receipt_rejected(tmp_path, monkeypatch, fault):
    _, full, rebuild, qa, output = package_fixture(tmp_path, monkeypatch)
    if fault == "source_archive":
        (full / "workflow.sources.zip").write_bytes(b"changed source snapshot")
    elif fault == "generated_export":
        (rebuild / "paper/generated/numbers.tex").write_bytes(b"changed generated number")
    elif fault == "trace_receipt":
        json_write(rebuild / "paper/generated/traceability.json", {"changed": True})
    else:
        (rebuild / "paper/references.tex").write_bytes(b"changed exported reference")
    with pytest.raises(ValueError):
        package.create(output, full=full, rebuild=rebuild, qa=qa)
    assert not output.exists()


@pytest.mark.parametrize("fault", ["cached_report", "cached_source_zip"])
def test_copied_baseline_cache_evidence_still_matches_its_receipts(tmp_path, monkeypatch, fault):
    _, full, rebuild, qa, output = package_fixture(tmp_path, monkeypatch, cached_baseline=True)
    previous = tmp_path / "completed-baseline"
    if fault == "cached_report":
        saved = json.loads((previous / "reproduction.json").read_text())
        saved["finished_at"] = "changed after the master verified it"
        json_write(previous / "reproduction.json", saved)
    else:
        (previous / "workflow.sources.zip").write_bytes(b"changed previous source archive")
    with pytest.raises(ValueError):
        package.create(output, full=full, rebuild=rebuild, qa=qa)
    assert not output.exists()


def test_valid_cached_baseline_chain_is_preserved_and_portably_extracts(tmp_path, monkeypatch):
    _, full, rebuild, qa, output = package_fixture(tmp_path, monkeypatch, cached_baseline=True)
    package.create(output, full=full, rebuild=rebuild, qa=qa)
    destination = tmp_path / "relocated-copy"
    checked = package.verify_archive(output, extract=destination)
    previous = tmp_path / "completed-baseline"
    assert checked["files_verified"] > 0
    for name in ("reproduction.json", "workflow.sources.zip"):
        assert (destination / "provenance/reproduction/baseline-full" / name).read_bytes() == (previous / name).read_bytes()
    assert (destination / "provenance/pdf-qa-final.json").read_bytes() == qa.read_bytes()
