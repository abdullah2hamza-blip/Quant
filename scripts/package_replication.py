"""Create/check a local replication archive; never upload or grant data rights."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import sqlite3
import uuid
from zipfile import ZipFile, ZipInfo, ZIP_DEFLATED, ZIP_STORED

from pypdf import PdfReader

from quant.data import digest, json_write
from quant.ledger import Ledger, code_hash, utc_now
from scripts.build_publication_artifacts import verify_results
from scripts.build_followup_artifacts import verify_collection


ROOT = Path(__file__).resolve().parents[1]


def safe_member(name: str) -> bool:
    path = PurePosixPath(name)
    if not name or "\\" in name or path.is_absolute():
        return False
    devices = {"CON","PRN","AUX","NUL","CONIN$","CONOUT$"}
    devices.update(prefix+number for prefix in ("COM","LPT") for number in "123456789\u00b9\u00b2\u00b3")
    for part in name.split("/"):
        if (part in ("",".","..") or part.rstrip(" .")!=part
                or any(ord(char)<32 or char in '<>:"|?*' for char in part)
                or part.split(".")[0].rstrip(" .").upper() in devices):
            return False
    return True


def portable_inventory(names: list[str]) -> None:
    if any(not safe_member(name) for name in names):
        raise ValueError("Unsafe or nonportable archive members")
    normalized = {name.casefold() for name in names}
    if len(normalized)!=len(names):
        raise ValueError("Unsafe or duplicate/aliased archive members")
    for name in normalized:
        parts = name.split("/")
        if any("/".join(parts[:index]) in normalized for index in range(1,len(parts))):
            raise ValueError("Archive file/directory prefix collision")


def verify_archive(archive: Path, *, extract: Path|None = None) -> dict:
    """Verify inventory and actual bytes before optional safe extraction."""
    with ZipFile(archive) as zipped:
        names = zipped.namelist()
        portable_inventory(names)
        manifest = json.loads(zipped.read("REPLICATION-MANIFEST.json"))
        expected = manifest["files"]
        if "REPLICATION-MANIFEST.json" in expected:
            raise ValueError("Manifest cannot inventory itself")
        if set(names)!=set(expected)|{"REPLICATION-MANIFEST.json"}:
            raise ValueError("Archive inventory differs from its manifest")
        for name, record in expected.items():
            payload = zipped.read(name)
            if len(payload)!=record["bytes"] or hashlib.sha256(payload).hexdigest()!=record["sha256"]:
                raise ValueError("Replication member checksum mismatch: "+name)
        if extract is not None:
            if extract.exists():
                raise ValueError("Extraction destination exists; preserve prior copies")
            extract.mkdir(parents=True)
            for name in names:
                target = extract/name
                if not target.resolve().is_relative_to(extract.resolve()):
                    raise ValueError("Unsafe extraction target")
                target.parent.mkdir(parents=True,exist_ok=True)
                payload = zipped.read(name)
                target.write_bytes(payload)
                if target.stat().st_size!=len(payload) or digest(target)!=hashlib.sha256(payload).hexdigest():
                    raise ValueError("Extracted file differs from verified bytes: "+name)
    return {"archive_sha256":digest(archive),"files_verified":len(expected),"uncompressed_bytes":sum(r["bytes"] for r in expected.values()),
            "extracted_to":str(extract.resolve()) if extract else None,
            "limit":"Byte/inventory verification; separately execute the documented research verifier/reproduction workflow"}


def completed_report(path: Path, ledger: Ledger, *, kind: str, mode: str) -> dict:
    report = json.loads(path.read_text())
    row = next((r for r in ledger.rows() if r["id"]==report.get("attempt_id")),{})
    if (row.get("kind")!=kind or row.get("status")!="completed" or not report.get("finished_at")
            or report.get("mode")!=mode or row.get("details",{}).get("outcome",{}).get("report_sha256")!=digest(path)):
        raise ValueError("Missing matching completed reproduction receipt: "+str(path))
    source = report.get("workflow_source",{})
    if not source.get("path") or not source.get("sha256"):
        raise ValueError("Completed reproduction lacks its source archive receipt")
    archive = path.parent/source["path"]
    if not archive.resolve().is_relative_to(path.parent.resolve()) or digest(archive)!=source["sha256"]:
        raise ValueError("Reproduction source archive differs from its completed receipt")
    return report


def staged_paper(rebuild: Path, report: dict) -> dict[str,bytes]:
    """Bind compiled inputs and all declared transformations to the receipt."""
    paper = rebuild/"paper"
    expected = dict(report["manuscript_inputs"])
    bibliography = report["bibliography"]
    expected.update(bibliography["output_sha256"])
    structural = {"bibliography-manifest.json":bibliography}
    expected.pop("bibliography-manifest.json",None)
    for key,prefix in (("baseline_displays","generated"),("followup_displays","generated/followup"),
                       ("market_interval_diagnostics","generated/market-diagnostics"),
                       ("bot_extension_displays","generated/bot-extension")):
        if key not in report:
            continue
        trace = report[key]
        structural[prefix+"/traceability.json"] = trace
        expected.update({prefix+"/"+name:sha for name,sha in trace["output_sha256"].items()})
    names = list(set(expected)|set(structural))
    portable_inventory(names)
    actual = {p.relative_to(paper).as_posix():p for p in paper.rglob("*")
              if p.is_file() and not {"__pycache__","plot-cache"}.intersection(p.parts)
              and p.suffix not in (".pyc",".log",".aux",".out",".xdv")}
    if set(actual)!=set(names):
        raise ValueError("Staged paper inventory differs from the completed rebuild")
    payloads = {name:path.read_bytes() for name,path in actual.items()}
    for name,sha in expected.items():
        if hashlib.sha256(payloads[name]).hexdigest()!=sha:
            raise ValueError("Staged paper changed after completed rebuild: "+name)
    for name,value in structural.items():
        if json.loads(payloads[name])!=value:
            raise ValueError("Staged paper metadata differs from the completed rebuild: "+name)
    return {"paper/"+name:payload for name,payload in payloads.items()}


def create(output: Path, *, full: Path, rebuild: Path, qa: Path) -> dict:
    ledger = Ledger(ROOT/"runs/research.sqlite")
    identifier = ledger.start("local_replication_package",{"output":str(output),"full":str(full),"rebuild":str(rebuild),"qa":str(qa)},code=code_hash(ROOT))
    try:
        if output.exists() or output.with_suffix(".receipt.json").exists():
            raise ValueError("Choose a new archive path; previous packages are preserved")
        verify_results(ROOT/"results/publication-v1")
        verify_collection(ROOT/"results/publication-v2")
        full_report = completed_report(full/"reproduction.json",ledger,kind="complete_publication_reproduction",mode="full frozen replay and paper rebuild")
        rebuild_report = completed_report(rebuild/"reproduction.json",ledger,kind="complete_publication_reproduction",mode="paper rebuild from preserved substantive results")
        for report in (full_report,rebuild_report):
            for key,name in (("baseline_registry_sha256","publication-v1"),("followup_registry_sha256","publication-v2")):
                if report[key]!=digest(ROOT/"results"/name/"registry.json"):
                    raise ValueError("Reproduction receipt refers to a different result collection")
        checks = full_report["followup_replay"]
        if checks.get("cases_compared")!=25:
            raise ValueError("Completed full workflow must compare every v2 case")
        qa_record = json.loads(qa.read_text())
        pdf = ROOT/"output/pdf/cost-aware-bitcoin-research.pdf"
        count = qa_record["pages_rendered"]
        actual_count = len(PdfReader(pdf).pages)
        if (type(count) is not int or count<=0 or count!=actual_count
                or qa_record.get("pages_visually_inspected")!=list(range(1,count+1))
                or qa_record.get("observed_layout_defects")!=[] or qa_record.get("pdf_sha256")!=digest(pdf)
                or rebuild_report["pdf"]["sha256"]!=digest(pdf)):
            raise ValueError("Final PDF lacks complete matching page-by-page visual QA")
        files = {}
        for directory in ("src","scripts","tests","configs","docs",".github","results","data","output/pdf"):
            for path in (ROOT/directory).rglob("*"):
                if (path.is_file() and not {"__pycache__","plot-cache"}.intersection(path.parts)
                        and path.suffix not in (".pyc",".log",".aux",".out",".xdv")):
                    files[path.relative_to(ROOT).as_posix()] = path
        files.update(staged_paper(rebuild,rebuild_report))
        files["provenance/pdf-qa-final.json"] = qa
        for name in ("pyproject.toml","uv.lock",".python-version","README.md",".gitattributes",".gitignore"):
            if (ROOT/name).is_file():
                files[name] = ROOT/name
        stage = ROOT/"runs"/("replication-staging-"+str(uuid.uuid4()))
        stage.mkdir(parents=True)
        snapshot = stage/"research.sqlite"
        with ledger.connect() as original,sqlite3.connect(snapshot) as copied:
            original.backup(copied)
        rows = Ledger(snapshot).rows()
        json_write(stage/"research.json",rows)
        files["runs/research.sqlite"],files["provenance/research-ledger.json"] = snapshot,stage/"research.json"
        # Keep portable evidence receipts and logs, not duplicate replay arrays,
        # extracted sources, raw caches or historical rendering intermediates.
        workflows = {"complete-full":full,"final-rebuild":rebuild}
        earlier = full_report.get("baseline_replay",{}).get("original_report")
        if earlier:
            if digest(Path(earlier))!=full_report["baseline_replay"]["original_report_sha256"]:
                raise ValueError("Cached baseline provenance report differs from the completed full workflow")
            completed_report(Path(earlier),ledger,kind="publication_reproduction",mode="full frozen compute replay")
            workflows["baseline-full"] = Path(earlier).parent
        provenance_bindings = {}
        for label,folder in workflows.items():
            source_report = json.loads((folder/"reproduction.json").read_text())
            provenance_bindings[f"provenance/reproduction/{label}/reproduction.json"] = digest(folder/"reproduction.json")
            source_record = source_report["workflow_source"]
            provenance_bindings[f"provenance/reproduction/{label}/"+source_record["path"]] = source_record["sha256"]
            for path in folder.iterdir():
                if path.is_file() and path.suffix in (".json",".zip",".log",".sqlite"):
                    files[f"provenance/reproduction/{label}/{path.name}"] = path
        package_note = {
            "created_at":utc_now(),"package_attempt":identifier,
            "purpose":"Local replication package for human submission review; no external publication or data-rights grant",
            "workflow":"uv run --locked python -m scripts.reproduce_complete_study --verify-only --output runs/verify-extracted-copy",
            "full_workflow":"uv run --locked python -m scripts.reproduce_complete_study --full --output runs/replay-extracted-copy",
            "final_pdf_sha256":digest(pdf),"qa_sha256":digest(qa),
            "full_report_sha256":digest(full/"reproduction.json"),"rebuild_report_sha256":digest(rebuild/"reproduction.json"),
            "ledger_snapshot_timing":"Consistent pre-finalization snapshot includes this package attempt as started; terminal receipt is beside ZIP and in originating ledger",
            "limits":"No compiler/interpreter/cache bundled. Vendor data remains subject to its terms. Historical absolute paths are provenance, not required installation paths. All attempt rows retained; scratch/partial folders remain in originating workspace. Full compute uses source archives in results, not cached earlier replay paths. Hosted CI has not been executed."}
        manifest = {**package_note,"files":{}}
        portable_inventory([*files,"REPLICATION-MANIFEST.json"])
        output.parent.mkdir(parents=True,exist_ok=True)
        with ZipFile(output,"x") as zipped:
            for name,path in sorted(files.items()):
                if not safe_member(name):
                    raise ValueError("Unsafe replication member")
                payload = path if isinstance(path,bytes) else path.read_bytes()
                if name in provenance_bindings and hashlib.sha256(payload).hexdigest()!=provenance_bindings[name]:
                    raise ValueError("Provenance changed during packaging: "+name)
                info = ZipInfo(name,(1980,1,1,0,0,0))
                info.compress_type = ZIP_STORED if PurePosixPath(name).suffix in (".npz",".zip",".pdf",".png") else ZIP_DEFLATED
                info.external_attr = 0o100644 << 16
                zipped.writestr(info,payload)
                manifest["files"][name] = {"bytes":len(payload),"sha256":hashlib.sha256(payload).hexdigest()}
            zipped.writestr("REPLICATION-MANIFEST.json",json.dumps(manifest,indent=2,allow_nan=False)+"\n",compress_type=ZIP_DEFLATED)
        verified = verify_archive(output)
        receipt = {"attempt_id":identifier,"created_at":utc_now(),"archive":str(output.resolve()),**verified,
                   "next_gate":"Extract to a new folder and actually execute its integrity verifier; byte verification alone is insufficient"}
        json_write(output.with_suffix(".receipt.json"),receipt)
        ledger.finish(identifier,"completed",{"archive_sha256":digest(output),"receipt_sha256":digest(output.with_suffix(".receipt.json"))})
        return receipt
    except Exception as error:
        ledger.finish(identifier,"failed",{"error":str(error),"partial_output":str(output)})
        raise


if __name__=="__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive",type=Path)
    parser.add_argument("--verify",action="store_true")
    parser.add_argument("--extract",type=Path)
    parser.add_argument("--full",type=Path)
    parser.add_argument("--rebuild",type=Path)
    parser.add_argument("--qa",type=Path,default=ROOT/"docs/publication/pdf-qa-final.json")
    args = parser.parse_args()
    if args.verify:
        result = verify_archive(args.archive,extract=args.extract)
    else:
        if args.full is None or args.rebuild is None or args.extract is not None:
            parser.error("Creation requires --full and --rebuild; extraction is verification-only")
        result = create(args.archive.resolve(),full=args.full.resolve(),rebuild=args.rebuild.resolve(),qa=args.qa.resolve())
    print(json.dumps(result,indent=2))
