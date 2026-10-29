"""Meaningful offline execution and untrusted-release boundary checks."""
from __future__ import annotations

import hashlib
import importlib.util
import io
import json
from pathlib import Path
import runpy
import stat
import warnings
from zipfile import ZipFile, ZipInfo, ZIP_DEFLATED

import numpy as np
import pytest

from scripts import kaggle_review as kr

ROOT = Path(__file__).resolve().parents[1]


def fixture_files():
    files = {"results/publication-v1/registry.json": b'{"study":"fixture"}',
             "LICENSE": b"Fixture original software license\n",
             "LICENSE-PAPER.md": b"Fixture original text license\n",
             "THIRD_PARTY.md": b"Fixture market material attribution\n"}
    files[kr.CSV_FILES["baseline"]] = (
        b"case,method,first_stream_power,first_stream_power_lower,first_stream_power_upper\n"
        b"effect05_equal_turnover,joint_linear,0.9,0.85,0.95\n"
        b"effect05_equal_turnover,separate_linear,0.1,0.05,0.15\n")
    files[kr.CSV_FILES["followup"]] = b"case,method,first_stream_rejection\nfixture,oracle_linear,0.1\n"
    files[kr.CSV_FILES["market"]] = b"case,cost_bps,policy,total_return\nbinance_primary_4h,25,fixed,0.1\n"
    files[kr.CSV_FILES["bot_extension"]] = b"cost_bps,book,total_return\n25,sma_20,0.1\n"
    out = io.BytesIO()
    np.savez(out, open_time_ms=np.array([1704067200000, 1704081600000], dtype=np.int64),
             cost25__fixed__nav=np.array([100., 110.]), cost25__adaptive__nav=np.array([100., 110.]),
             cost25__buy_hold__nav=np.array([101., 105.]))
    files[kr.PRIMARY + "/paths.npz"] = out.getvalue()
    report = {"scenarios": {"25": {"initial_state": {p: {"nav": 100.} for p in ("fixed", "adaptive", "buy_hold")},
        "metrics": {p: {"total_return": r} for p, r in (("fixed", .1), ("adaptive", .1), ("buy_hold", .05))}}}}
    files[kr.PRIMARY + "/report.json"] = json.dumps(report).encode()
    return files


def manifest_for(files):
    records = {name: {"sha256": hashlib.sha256(payload).hexdigest(), "bytes": len(payload)}
               for name, payload in files.items()}
    return {"schema_version": 1, "files": records,
            "scientific_registries": {"results/publication-v1/registry.json": records["results/publication-v1/registry.json"]["sha256"]}}


def archive_at(path, files=None, *, manifest=None, extra=(), symlink=None):
    files = fixture_files() if files is None else files
    manifest = manifest_for(files) if manifest is None else manifest
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        with ZipFile(path, "w", compression=ZIP_DEFLATED) as archive:
            archive.writestr(kr.MANIFEST, json.dumps(manifest))
            for name, payload in files.items():
                info = ZipInfo(name)
                if name == symlink:
                    info.create_system = 3
                    info.external_attr = (stat.S_IFLNK | 0o777) << 16
                archive.writestr(info, payload)
            for name, payload in extra:
                archive.writestr(name, payload)
    return path


def load_metadata_helper():
    spec = importlib.util.spec_from_file_location("quant_metadata_test", ROOT / "kaggle/prepare_metadata.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_archive_review_is_offline_and_reports_saved_scope(tmp_path, monkeypatch):
    import socket
    def forbidden(*args, **kwargs):
        raise AssertionError("Offline review attempted a network connection")
    monkeypatch.setattr(socket.socket, "connect", forbidden)
    archive = archive_at(tmp_path / "quant-research-release-v3.zip")
    output = tmp_path / "working/review"
    result = kr.review(archive=archive, output=output)
    assert result["exact_numerical_replay_performed"] is False
    assert result["primary"]["fixed_adaptive_rebased_arrays_equal"]
    assert result["primary"]["fixed_adaptive_rebased_max_abs_difference"] == 0
    assert result["csv_row_counts"] == {"baseline": 2, "followup": 1, "market": 1, "bot_extension": 1}
    assert result["runtime"]["numpy"] == np.__version__
    assert result["archive_sha256"] == kr.sha256(archive)
    assert json.loads((output / "review-summary.json").read_text()) == result
    assert all((output / f).stat().st_size > 1000 for f in result["figures"])
    assert (output / "ATTRIBUTION.md").is_file()
    with pytest.raises(ValueError, match="new output"):
        kr.review(archive=archive, output=output)


@pytest.mark.parametrize("name", ["../escape", "/absolute", "C:/escape", "x\\escape", "CON.txt", "a./file", "./file"])
def test_unsafe_members_are_rejected_before_extracting(tmp_path, name):
    files = fixture_files(); files[name] = b"forbidden"
    archive = archive_at(tmp_path / "unsafe.zip", files)
    output = tmp_path / "working"
    with pytest.raises(ValueError, match="Unsafe"):
        kr.review(archive=archive, output=output)
    assert not output.exists()


@pytest.mark.parametrize("extra", [[("LICENSE", b"duplicate")], [("license", b"alias")], [("LICENSE/child", b"collision")]])
def test_duplicate_alias_and_prefix_collisions_are_rejected(tmp_path, extra):
    archive = archive_at(tmp_path / "duplicate.zip", extra=extra)
    with pytest.raises(ValueError, match="Duplicate|collision"):
        kr.verify_archive(archive)


def test_symlink_and_unlisted_extra_payloads_are_rejected(tmp_path):
    with pytest.raises(ValueError, match="Symlink"):
        kr.verify_archive(archive_at(tmp_path / "link.zip", symlink="LICENSE"))
    with pytest.raises(ValueError, match="inventory differs"):
        kr.verify_archive(archive_at(tmp_path / "extra.zip", extra=[("unlisted.txt", b"extra")]))


def test_changed_hash_and_unanchored_registry_are_rejected(tmp_path):
    files = fixture_files(); manifest = manifest_for(files)
    files["LICENSE"] = b"X" * len(files["LICENSE"])
    with pytest.raises(ValueError, match="hash differs"):
        kr.verify_archive(archive_at(tmp_path / "corrupt.zip", files, manifest=manifest))
    manifest["scientific_registries"]["results/publication-v1/registry.json"] = "0" * 64
    with pytest.raises(ValueError, match="registry anchor"):
        kr.manifest_data(json.dumps(manifest).encode())


def test_duplicate_json_keys_and_excessive_sizes_fail():
    with pytest.raises(ValueError, match="Duplicate JSON"):
        kr.manifest_data(b'{"schema_version":1,"schema_version":1}')
    manifest = manifest_for(fixture_files())
    manifest["files"]["LICENSE"]["bytes"] = kr.MAX_FILE_BYTES + 1
    with pytest.raises(ValueError, match="file size"):
        kr.manifest_data(json.dumps(manifest).encode())
    manifest["schema_version"] = True
    with pytest.raises(ValueError, match="Unsupported"):
        kr.manifest_data(json.dumps(manifest).encode())


def test_read_only_root_is_not_modified_and_discovery_is_unambiguous(tmp_path):
    archive = archive_at(tmp_path / "quant-research-release-v3.zip")
    manifest = kr.verify_archive(archive)
    root = tmp_path / "attached/release"
    root.parent.mkdir()
    kr.extract_verified(archive, root, manifest)
    before = {str(p.relative_to(root)): kr.sha256(p) for p in root.rglob("*") if p.is_file()}
    assert kr.discover(root.parent) == ("root", root)
    with pytest.raises(ValueError, match="outside"):
        kr.review(root=root, output=root / "illegal-output")
    result = kr.review(root=root, output=tmp_path / "separate-working")
    assert result["source_kind"] == "directory"
    assert before == {str(p.relative_to(root)): kr.sha256(p) for p in root.rglob("*") if p.is_file()}
    archive_at(root.parent / "quant-research-release-v3.zip")
    with pytest.raises(ValueError, match="exactly one"):
        kr.discover(root.parent)


def test_runtime_gate_cannot_claim_new_replay(tmp_path, monkeypatch):
    archive = archive_at(tmp_path / "release.zip")
    monkeypatch.setattr(kr.platform, "python_version", lambda: "3.99.0")
    with pytest.raises(ValueError, match="Recorded frozen runtime"):
        kr.review(archive=archive, output=tmp_path / "strict", require_recorded_runtime=True)
    result = kr.review(archive=archive, output=tmp_path / "portable")
    assert not result["matches_recorded_python_numpy"] and not result["exact_numerical_replay_performed"]


def test_metadata_needs_explicit_kaggle_owner_and_preserves_mixed_rights(tmp_path, monkeypatch):
    helper = load_metadata_helper()
    files = fixture_files()
    files[helper.MANUSCRIPT_PATH] = b"%PDF-1.7\nFixture manuscript payload; no rendering claimed\n%%EOF\n"
    archive = archive_at(tmp_path / "release.zip", files)
    monkeypatch.delenv("KAGGLE_USERNAME", raising=False)
    with pytest.raises(ValueError, match="actual Kaggle username"):
        helper.prepare(archive=archive, output=tmp_path / "missing-owner")
    result = helper.prepare(archive=archive, output=tmp_path / "prepared", owner="actualowner")
    data = json.loads((tmp_path / "prepared/dataset/dataset-metadata.json").read_text())
    kernel = json.loads((tmp_path / "prepared/kernel/kernel-metadata.json").read_text())
    assert data["licenses"] == [{"name": "other"}]
    assert data["id"].startswith("actualowner/") and 6 <= len(data["title"]) <= 50
    assert kernel["is_private"] and not kernel["enable_gpu"] and not kernel["enable_internet"]
    assert kernel["dataset_sources"] == [data["id"]]
    assert (tmp_path / "prepared/dataset" / helper.ARCHIVE_NAME).read_bytes() == archive.read_bytes()
    assert helper.ARCHIVE_NAME == "quant-research-release-v4.zip"
    assert helper.AI_DISCLOSURE in data["description"]
    assert helper.REPORT_TITLE in data["description"] and "v1.0.0" in data["description"]
    assert (tmp_path / "prepared/dataset" / Path(helper.MANUSCRIPT_PATH).name).read_bytes() == files[helper.MANUSCRIPT_PATH]
    assert any(r["path"] == Path(helper.MANUSCRIPT_PATH).name for r in data["resources"])
    assert result["status"] == "prepared locally; not uploaded"


def test_shipped_notebook_embeds_current_launcher_and_executes_all_code_cells(tmp_path, monkeypatch):
    helper = load_metadata_helper()
    source = (ROOT / "scripts/kaggle_review.py").read_text(encoding="utf-8")
    notebook = json.loads((ROOT / "kaggle/review_saved_results.ipynb").read_text(encoding="utf-8"))
    assert notebook == helper.notebook(source), "Regenerate the notebook after launcher edits"
    narrative = "\n".join("".join(c["source"]) for c in notebook["cells"] if c["cell_type"] == "markdown")
    assert helper.AI_DISCLOSURE in narrative
    for heading in ("Research question and inputs", "Method and key recorded findings", "Limits", "Citation and full reproduction"):
        assert heading in narrative
    assert helper.REPRODUCTION_URL in narrative and helper.REPORT_TITLE in narrative
    archive = archive_at(tmp_path / "quant-research-release-v3.zip")
    output = tmp_path / "notebook-working"
    monkeypatch.setenv("QUANT_REVIEW_ARCHIVE", str(archive))
    monkeypatch.setenv("QUANT_REVIEW_OUTPUT", str(output))
    monkeypatch.delenv("QUANT_REVIEW_ROOT", raising=False)
    namespace = {"__name__": "__main__"}
    for cell in notebook["cells"]:
        if cell["cell_type"] == "code":
            exec(compile("".join(cell["source"]), "notebook-cell", "exec"), namespace)
    assert namespace["summary"]["status"] == "completed saved-results review"
    assert namespace["LAUNCHER_SOURCE"] == source
    assert (output / "review-summary.json").is_file()


def test_disclosure_is_complete_and_consistent_in_active_public_materials():
    helper = load_metadata_helper()
    normalized = lambda s: " ".join(s.split())
    for name in ("README.md", "paper/sections/declarations.tex", "docs/KAGGLE.md",
                 "docs/publication/COVER-LETTER.md", "docs/publication/SUBMIT.md"):
        assert helper.AI_DISCLOSURE in normalized((ROOT / name).read_text(encoding="utf-8")), name
    assert "Exact model versions were not consistently recorded" in helper.AI_DISCLOSURE
    assert "not independent human peer review" in helper.AI_DISCLOSURE
