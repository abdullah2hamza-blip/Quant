"""One entry point for both synthetic studies, market evidence and final paper.

Default rebuilds from verified results. --full replays exact archived sources.
An explicit verified-baseline reuse option avoids recomputing that earlier replay.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import tempfile
import uuid
from zipfile import ZipFile

import numpy as np

from quant.data import digest, json_write
from quant.ledger import Ledger, code_hash, utc_now
from quant.publication import _snapshot_source
from scripts.audit_publication_data import reconcile as audit_binance
from scripts.audit_bitstamp_data import reconcile as audit_bitstamp
from scripts.build_bibliography import build as build_bibliography
from scripts.build_publication_artifacts import build as build_baseline, verify_results
from scripts.build_followup_artifacts import build as build_followup, verify_collection
from scripts.market_interval_diagnostics import build as build_market_diagnostics
from scripts.bot_extension_study import build as build_bot_extension, verify as verify_bot_extension
from scripts.reproduce_bot_extension import reproduce as replay_bot_extension
from scripts.reproduce_publication import _run, prepare_frozen_source
from scripts.verify_publication_replay import compare_replay
from scripts.verify_followup_replay import compare_followup


ROOT = Path(__file__).resolve().parents[1]


def compiler_path(explicit: str|None) -> str:
    compiler = explicit or os.environ.get("QUANT_TECTONIC") or shutil.which("tectonic")
    portable_root = Path(os.environ["LOCALAPPDATA"])/"Temp" if os.name=="nt" and "LOCALAPPDATA" in os.environ else Path(tempfile.gettempdir())
    portable = portable_root/"codex-quant-tools/tectonic/tectonic.exe"
    if compiler is None and portable.is_file():
        compiler = str(portable)
    if compiler is None:
        raise ValueError("Provide Tectonic 0.17.0 on PATH, QUANT_TECTONIC or --tectonic")
    version = subprocess.run([compiler,"--version"],capture_output=True,text=True,check=True).stdout.strip()
    if version!="Tectonic 0.17.0":
        raise ValueError("Recorded PDF workflow requires Tectonic 0.17.0")
    return str(Path(shutil.which(compiler) or compiler).resolve())


def audit_inputs(baseline: Path, registry: dict, markets: dict, *, input_root: Path|None = None) -> dict:
    input_root = input_root or ROOT
    frozen = json.loads((baseline/registry["source_freezes"]["market"]).read_text())
    for item in frozen["inputs"]:
        if item["kind"] in ("csv","manifest") and digest(input_root/item["path"])!=item["sha256"]:
            raise ValueError("Current market inputs differ from the preserved study freeze")
    audited = {}
    for report in markets.values():
        case = report["case"]
        if case["data"] in audited:
            continue
        bitstamp = case["provider"]=="bitstamp-public-ohlc"
        audited[case["data"]] = (audit_bitstamp if bitstamp else audit_binance)(input_root/case["data"],cache=input_root/"data/raw/bitstamp" if bitstamp else input_root/"data/raw")
    return audited


def stage_manuscript(source: Path, paper: Path, bibliography: Path) -> None:
    """Execute the actual captured bytes, never a later copy of live sources."""
    paper.mkdir(parents=True)
    with ZipFile(source) as archive:
        names = [name for name in archive.namelist() if name.startswith("paper/") and not name.endswith("/")]
        if "paper/main.tex" not in names:
            raise ValueError("Workflow snapshot lacks its main manuscript")
        for name in names:
            target = paper/name.removeprefix("paper/")
            if not target.resolve().is_relative_to(paper.resolve()):
                raise ValueError("Unsafe manuscript archive path")
            target.parent.mkdir(parents=True,exist_ok=True)
            target.write_bytes(archive.read(name))
        bibliography.write_bytes(archive.read("docs/publication/bibliography.json"))


def stage_data(baseline: Path, registry: dict, destination: Path) -> None:
    frozen = json.loads((baseline/registry["source_freezes"]["market"]).read_text())
    for item in frozen["inputs"]:
        if item["kind"] not in ("csv","manifest"):
            continue
        source,target = ROOT/item["path"],destination/item["path"]
        if digest(source)!=item["sha256"]:
            raise ValueError("Data changed before immutable staging")
        target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(source,target)
        if digest(target)!=item["sha256"]:
            raise ValueError("Data changed during immutable staging")
    shutil.copytree(ROOT/"data/raw",destination/"data/raw")


def _single_run(folder: Path) -> Path:
    paths = list(folder.iterdir())
    if len(paths)!=1 or not paths[0].is_dir():
        raise ValueError("Replay output must contain exactly one completed run directory")
    return paths[0]


def reverify_baseline(previous: Path, baseline: Path, registry: dict, ledger: Ledger) -> dict:
    report_path = previous/"reproduction.json"
    report = json.loads(report_path.read_text())
    rows = {row["id"]:row for row in ledger.rows()}
    row = rows.get(report["attempt_id"],{})
    if (report.get("mode")!="full frozen compute replay" or not report.get("finished_at")
            or report.get("input_registry_sha256")!=digest(baseline/"registry.json")
            or row.get("kind")!="publication_reproduction" or row.get("status")!="completed"
            or row.get("details",{}).get("outcome",{}).get("report_sha256")!=digest(report_path)):
        raise ValueError("Baseline reuse requires its completed full-replay ledger receipt and matching registry")
    source = previous/report["workflow_source"]["path"]
    if digest(source)!=report["workflow_source"]["sha256"]:
        raise ValueError("Earlier replay workflow source changed")
    return {"kind":"reverified earlier full baseline replay; no new baseline computation",
            "original_report":str(report_path.resolve()),"original_report_sha256":digest(report_path),
            "original_attempt_id":report["attempt_id"],"original_finished_at":report["finished_at"],
            "simulation":compare_replay(baseline/registry["simulation"],_single_run(previous/"simulation-replay"),market=False),
            "market":compare_replay(baseline/registry["market"],_single_run(previous/"market-replay"),market=True)}


def replay_baseline(baseline: Path, registry: dict, output: Path, *, input_root: Path|None = None) -> dict:
    result = {"kind":"fresh frozen baseline replay"}
    for key in ("simulation","market"):
        stage = output/(key+"-source")
        frozen,_ = prepare_frozen_source(input_root or ROOT,baseline,key,stage)
        replay = output/(key+"-replay")
        command = [sys.executable,"-u","-m","quant","publication-sim" if key=="simulation" else "market-study",
                   "--freeze",str(frozen.resolve()),"--ledger",str((output/"replay-ledger.sqlite").resolve()),"--output-root",str(replay.resolve())]
        if key=="market":
            command.append("--acknowledge-retrospective")
        env = {**os.environ,"PYTHONPATH":str((stage/"src").resolve()),"PYTHONUNBUFFERED":"1"}
        _run(command,stage,output/(key+"-replay.log"),environment=env)
        result[key] = compare_replay(baseline/registry[key],_single_run(replay),market=key=="market")
    return result


def replay_followup(followup: Path, registry: dict, output: Path) -> dict:
    stage = output/"followup-source"
    frozen,_ = prepare_frozen_source(ROOT,followup,"followup",stage)
    replay = output/"followup-replay"
    ledger = output/"followup-replay-ledger.sqlite"
    command = [sys.executable,"-u","-m","quant.followup","run","--freeze",str(frozen.resolve()),
               "--output",str(replay.resolve()),"--ledger",str(ledger.resolve())]
    env = {**os.environ,"PYTHONPATH":str((stage/"src").resolve()),"PYTHONUNBUFFERED":"1"}
    _run(command,stage,output/"followup-replay.log",environment=env)
    return compare_followup(followup/registry["followup"],replay,frozen,replay_ledger=ledger)


def reproduce(output: Path, *, baseline: Path|None = None, followup: Path|None = None,
              full: bool = False, verify_only: bool = False, tectonic: str|None = None,
              reuse_baseline: Path|None = None, results_only: bool = False) -> dict:
    ledger = Ledger(ROOT/"runs/research.sqlite")
    baseline,followup = baseline or ROOT/"results/publication-v1",followup or ROOT/"results/publication-v2"
    initial_code = code_hash(ROOT)
    identifier = ledger.start("complete_publication_reproduction",{"output":str(output),"baseline":str(baseline),"followup":str(followup),
                              "full":full,"verify_only":verify_only,"results_only":results_only,"reuse_baseline":str(reuse_baseline)},code=initial_code)
    try:
        if (full and verify_only or reuse_baseline is not None and not full
                or results_only and (full or verify_only)):
            raise ValueError("Results-only, integrity-only and full modes are exclusive; baseline reuse requires full mode")
        base_anchor,follow_anchor = digest(baseline/"registry.json"),digest(followup/"registry.json")
        base_registry,_,simulations,markets = verify_results(baseline)
        follow_registry,_,_,follow_reports = verify_collection(followup)
        extension = ROOT/"results/bot-extension-v1"
        extension_anchor = digest(extension/"registry.json") if (extension/"registry.json").is_file() else None
        if extension_anchor is not None:
            verify_bot_extension(extension)
        if output.exists():
            raise ValueError("Preserve earlier reproduction attempts; choose a new output directory")
        output.mkdir(parents=True)
        mode = ("integrity verification only" if verify_only else
                "full frozen replay and paper rebuild" if full else
                "results-only paper rebuild; no raw-data audit or computation" if results_only else
                "paper rebuild from preserved substantive results")
        record = {"attempt_id":identifier,"mode":mode,"started_at":utc_now(),"runtime":{"python":platform.python_version(),"numpy":np.__version__,"platform":platform.platform()},
                  "baseline_registry_sha256":base_anchor,"followup_registry_sha256":follow_anchor,
                  "case_counts":{"baseline_synthetic":len(simulations),"followup_synthetic":len(follow_reports),"market":len(markets)}}
        if extension_anchor is not None:
            record["bot_extension_registry_sha256"] = extension_anchor
        documents = [p for p in (ROOT/"docs/publication").rglob("*") if p.is_file()]
        documents += [p for p in (ROOT/"paper").rglob("*") if p.is_file() and "generated" not in p.parts and "__pycache__" not in p.parts]
        source = output/"workflow.sources.zip"
        record["workflow_source"] = {"path":source.name,"sha256":_snapshot_source(ROOT,source,documents),"code_sha256_at_start":initial_code}
        if code_hash(ROOT)!=initial_code:
            raise ValueError("Source changed while capturing the workflow snapshot")
        guard = sorted([*list((ROOT/"scripts").glob("*.py")),*list((ROOT/"src/quant").glob("*.py")),ROOT/"uv.lock",ROOT/"pyproject.toml"])
        helper_hashes = {p.relative_to(ROOT).as_posix():digest(p) for p in guard}
        record["executed_source_guard"] = helper_hashes
        json_write(output/"progress.json",record)
        if not verify_only:
            compiler = compiler_path(tectonic)
            compiler_sha = digest(Path(compiler))
            paper = output/"paper"
            bib = output/"bibliography-input.json"
            stage_manuscript(source,paper,bib)
            record["manuscript_inputs"] = {p.relative_to(paper).as_posix():digest(p) for p in sorted(paper.rglob("*")) if p.is_file()}
            record["bibliography_input_sha256"] = digest(bib)
            inputs = output/"inputs"
            staged_base,staged_follow = inputs/"publication-v1",inputs/"publication-v2"
            shutil.copytree(baseline,staged_base)
            shutil.copytree(followup,staged_follow)
            if extension_anchor is not None:
                staged_extension=inputs/"bot-extension-v1"
                shutil.copytree(extension,staged_extension)
                if digest(staged_extension/"registry.json")!=extension_anchor:
                    raise ValueError("Exploratory extension changed during staging")
                verify_bot_extension(staged_extension)
                extension=staged_extension
            if digest(staged_base/"registry.json")!=base_anchor or digest(staged_follow/"registry.json")!=follow_anchor:
                raise ValueError("Result registry changed during immutable staging")
            base_registry,_,_,markets = verify_results(staged_base)
            follow_registry,_,_,_ = verify_collection(staged_follow)
            baseline,followup = staged_base,staged_follow
            if results_only:
                record["raw_snapshots_reconciled"] = 0
                record["data_audit_scope"] = "Not performed: explicit results-only rebuild from preserved accepted outputs"
            else:
                stage_data(baseline,base_registry,inputs)
                audited = audit_inputs(baseline,base_registry,markets,input_root=inputs)
                json_write(output/"independent-data-audits.json",audited)
                record["raw_snapshots_reconciled"] = len(audited)
            if full:
                record["baseline_replay"] = reverify_baseline(reuse_baseline,baseline,base_registry,ledger) if reuse_baseline else replay_baseline(baseline,base_registry,output,input_root=inputs)
                json_write(output/"progress.json",record)
                record["followup_replay"] = replay_followup(followup,follow_registry,output)
                if extension_anchor is not None:
                    record["bot_extension_replay"] = replay_bot_extension(extension,output/"bot-extension-replay",input_root=inputs)
                json_write(output/"progress.json",record)
            if any(digest(ROOT/name)!=sha for name,sha in helper_hashes.items()):
                raise ValueError("An executed source file changed during reproduction; preserve this attempt")
            record["baseline_displays"] = build_baseline(baseline,paper/"generated")
            record["followup_displays"] = build_followup(followup,paper/"generated/followup")
            record["market_interval_diagnostics"] = build_market_diagnostics(baseline,paper/"generated/market-diagnostics")
            if extension_anchor is not None:
                record["bot_extension_displays"] = build_bot_extension(extension,paper/"generated/bot-extension")
            record["bibliography"] = build_bibliography(bib,paper)
            if digest(baseline/"registry.json")!=base_anchor or digest(followup/"registry.json")!=follow_anchor:
                raise ValueError("A staged result registry changed before display finalization")
            verify_results(baseline)
            verify_collection(followup)
            pdf = output/"pdf"
            pdf.mkdir()
            environment = {**os.environ,"TECTONIC_CACHE_DIR":str((ROOT/"runs/tectonic-cache").resolve())}
            if digest(Path(compiler))!=compiler_sha:
                raise ValueError("Compiler binary changed during reproduction")
            _run([compiler,"--untrusted","--keep-logs","--outdir",str(pdf.resolve()),"main.tex"],paper,output/"latex-build.log",environment=environment)
            final = pdf/"cost-aware-bitcoin-research.pdf"
            shutil.copy2(pdf/"main.pdf",final)
            record["pdf"] = {"path":str(final.resolve()),"sha256":digest(final),"compiler":compiler,"compiler_binary_sha256":compiler_sha,"version":"Tectonic 0.17.0",
                             "limit":"Numerical agreement and layout QA are separate; PDF bytes may vary with package/font/metadata details"}
        if any(digest(ROOT/name)!=sha for name,sha in helper_hashes.items()):
            raise ValueError("Executed source changed before finalization; preserve this attempt")
        if digest(baseline/"registry.json")!=base_anchor or digest(followup/"registry.json")!=follow_anchor:
            raise ValueError("A result registry changed before finalization")
        if extension_anchor is not None and digest(extension/"registry.json")!=extension_anchor:
            raise ValueError("Exploratory extension changed before finalization")
        record["finished_at"] = utc_now()
        json_write(output/"reproduction.json",record)
        ledger.finish(identifier,"completed",{"output":str(output.resolve()),"report_sha256":digest(output/"reproduction.json")})
        return record
    except Exception as error:
        ledger.finish(identifier,"failed",{"error":str(error),"partial_output":str(output)})
        raise


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output",type=Path,default=ROOT/"runs"/("complete-reproduction-"+str(uuid.uuid4())))
    parser.add_argument("--baseline",type=Path,default=ROOT/"results/publication-v1")
    parser.add_argument("--followup",type=Path,default=ROOT/"results/publication-v2")
    parser.add_argument("--full",action="store_true")
    parser.add_argument("--verify-only",action="store_true")
    parser.add_argument("--results-only",action="store_true",help="Build from verified saved results without raw vendor data; excludes raw audit and compute replay")
    parser.add_argument("--tectonic")
    parser.add_argument("--reuse-baseline-replay",type=Path)
    args = parser.parse_args()
    report = reproduce(args.output.resolve(),baseline=args.baseline.resolve(),followup=args.followup.resolve(),full=args.full,
                       verify_only=args.verify_only,tectonic=args.tectonic,
                       reuse_baseline=args.reuse_baseline_replay.resolve() if args.reuse_baseline_replay else None,
                       results_only=args.results_only)
    print(json.dumps({"attempt_id":report["attempt_id"],"mode":report["mode"],"output":str(args.output.resolve()),"finished_at":report["finished_at"]},indent=2))
