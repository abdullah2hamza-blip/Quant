"""One workflow: audit inputs, optionally replay frozen studies, rebuild paper/PDF.

Use `uv run --locked python -m scripts.reproduce_publication --help`.
The full replay uses the archived study sources, not later working-tree code.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import uuid
from zipfile import ZipFile

from quant.data import digest, json_write
from quant.ledger import Ledger, code_hash, utc_now
from quant.publication import _snapshot_source
from scripts.audit_publication_data import reconcile as audit_binance
from scripts.audit_bitstamp_data import reconcile as audit_bitstamp
from scripts.build_bibliography import build as build_bibliography
from scripts.build_publication_artifacts import build as build_displays, verify_results
from scripts.verify_publication_replay import compare_replay


ROOT = Path(__file__).resolve().parents[1]


def _run(command: list[str], cwd: Path, log: Path, *, environment: dict | None = None) -> None:
    with log.open("w", encoding="utf-8", newline="\n") as file:
        with subprocess.Popen(command, cwd=cwd, env=environment, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace") as process:
            for line in process.stdout:
                file.write(line)
                file.flush()
                text = line.rstrip()
                try:
                    print(text, flush=True)
                except UnicodeEncodeError:
                    encoding = getattr(sys.stdout, "encoding", None) or "utf-8"
                    print(text.encode(encoding, errors="backslashreplace").decode(encoding), flush=True)
            if process.wait() != 0:
                raise RuntimeError(f"Reproduction subprocess failed; see {log}")


def prepare_frozen_source(root: Path, results: Path, key: str, target: Path) -> tuple[Path, dict]:
    registry = json.loads((results / "registry.json").read_text())
    source_freeze = results / registry["source_freezes"][key]
    frozen = json.loads(source_freeze.read_text())
    archive = source_freeze.parent / frozen["source_snapshot"]
    if digest(archive) != frozen["source_snapshot_sha256"] or target.exists():
        raise ValueError("Changed archive or nonempty replay destination")
    target.mkdir(parents=True)
    with ZipFile(archive) as zipped:
        if any(not (target / name).resolve().is_relative_to(target.resolve()) for name in zipped.namelist()):
            raise ValueError("Unsafe archive member")
        zipped.extractall(target)
    if code_hash(target) != frozen["code_sha256"]:
        raise ValueError("Extracted study source does not reproduce its frozen fingerprint")
    run_dir = target / "runs"
    run_dir.mkdir()
    copied_freeze = run_dir / source_freeze.name
    shutil.copy2(source_freeze, copied_freeze)
    shutil.copy2(archive, run_dir / archive.name)
    if key == "market":
        for item in frozen["inputs"]:
            if item["kind"] in ("csv", "manifest"):
                original, copied = root / item["path"], target / item["path"]
                if digest(original) != item["sha256"]:
                    raise ValueError("Frozen market input changed")
                copied.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(original,copied)
    return copied_freeze, frozen


def reproduce(results: Path, output: Path, *, full: bool = False, tectonic: str | None = None, verify_only: bool = False) -> dict:
    ledger = Ledger(ROOT / "runs/research.sqlite")
    identifier = ledger.start("publication_reproduction", {"results":str(results),"output":str(output),"full":full,"verify_only":verify_only}, code=code_hash(ROOT))
    try:
        registry, sm, simulations, markets = verify_results(results)
        if output.exists():
            raise ValueError("Reproduction output exists; preserve earlier attempts")
        output.mkdir(parents=True)
        record = {"attempt_id":identifier,"started_at":utc_now(),"input_registry_sha256":digest(results / "registry.json"),
                  "mode":"full frozen compute replay" if full else "rebuild from preserved substantive results", "simulation_cases":len(simulations),"market_cases":len(markets)}
        # Preserve the executed workflow and manuscript inputs before a long replay.
        # Later development may add new studies without changing these inputs.
        documents = list((ROOT / "docs/publication").rglob("*"))
        documents += list((ROOT / "paper").rglob("*.tex"))
        documents = [p for p in documents if p.is_file() and "generated" not in p.parts]
        snapshot = output / "workflow.sources.zip"
        record["workflow_source"] = {"path":snapshot.name,"sha256":_snapshot_source(ROOT,snapshot,documents),
                                     "code_sha256_at_start":code_hash(ROOT)}
        helpers = [Path(__file__).resolve(), *(ROOT / "scripts" / name for name in
                   ("build_publication_artifacts.py","build_bibliography.py","verify_publication_replay.py",
                    "audit_publication_data.py","audit_bitstamp_data.py"))]
        helper_hashes = {p.relative_to(ROOT).as_posix():digest(p) for p in helpers}
        record["executed_helpers"] = helper_hashes
        if verify_only:
            record["mode"] = "integrity verification only; no data audit, compute replay or PDF rebuild"
        else:
            paper = output / "paper"
            shutil.copytree(ROOT / "paper",paper,ignore=shutil.ignore_patterns("generated","__pycache__"))
            bibliography = output / "bibliography-input.json"
            shutil.copy2(ROOT / "docs/publication/bibliography.json",bibliography)
            record["manuscript_inputs"] = {p.relative_to(paper).as_posix():digest(p) for p in sorted(paper.rglob("*")) if p.is_file()}
            record["bibliography_input_sha256"] = digest(bibliography)
            # A fresh audit of changed inputs cannot validate the old result set.
            market_freeze = json.loads((results / registry["source_freezes"]["market"]).read_text())
            for item in market_freeze["inputs"]:
                if item["kind"] in ("csv", "manifest") and digest(ROOT / item["path"]) != item["sha256"]:
                    raise ValueError("Current data do not match the preserved market freeze")
            audited = {}
            for case in markets.values():
                name = case["case"]["data"]
                if name not in audited:
                    is_bitstamp = case["case"]["provider"] == "bitstamp-public-ohlc"
                    function = audit_bitstamp if is_bitstamp else audit_binance
                    audited[name] = function(ROOT / name, cache=ROOT / "data/raw" / "bitstamp" if is_bitstamp else ROOT / "data/raw")
            json_write(output / "independent-data-audits.json",audited)
            record["raw_snapshots_reconciled"] = len(audited)
            if full:
                for key in ("simulation","market"):
                    stage = output / (key + "-source")
                    freeze,_ = prepare_frozen_source(ROOT,results,key,stage)
                    out_runs = output / (key + "-replay")
                    command = [sys.executable,"-u","-m","quant","publication-sim" if key == "simulation" else "market-study",
                               "--freeze",str(freeze.resolve()),"--ledger",str((output / "replay-ledger.sqlite").resolve()),"--output-root",str(out_runs.resolve())]
                    if key == "market":
                        command.append("--acknowledge-retrospective")
                    env = {**os.environ,"PYTHONPATH":str((stage / "src").resolve()),"PYTHONUNBUFFERED":"1"}
                    _run(command,stage,output / (key + "-replay.log"),environment=env)
                    candidates = list(out_runs.iterdir())
                    if len(candidates) != 1:
                        raise ValueError("Ambiguous replay output")
                    record[key + "_replay"] = compare_replay(results / registry[key],candidates[0],market=key == "market")
            if any(digest(ROOT / name) != sha for name,sha in helper_hashes.items()):
                raise ValueError("A running workflow helper changed; preserve this attempt and rerun from its source snapshot")
            record["displays"] = build_displays(results,paper / "generated")
            record["bibliography"] = build_bibliography(bibliography,paper)
            compiler = tectonic or os.environ.get("QUANT_TECTONIC") or shutil.which("tectonic")
            portable_root = Path(os.environ["LOCALAPPDATA"]) / "Temp" if os.name == "nt" and "LOCALAPPDATA" in os.environ else Path(tempfile.gettempdir())
            portable = portable_root / "codex-quant-tools/tectonic/tectonic.exe"
            if compiler is None and portable.is_file():
                compiler = str(portable)
            if compiler is None:
                raise ValueError("Install Tectonic 0.17.0 or pass --tectonic; the generated sources/displays are retained")
            version = subprocess.run([compiler,"--version"],check=True,capture_output=True,text=True).stdout.strip()
            if version != "Tectonic 0.17.0":
                raise ValueError("The recorded workflow requires Tectonic 0.17.0")
            pdf_dir = output / "pdf"
            pdf_dir.mkdir()
            env = {**os.environ,"TECTONIC_CACHE_DIR":str((ROOT / "runs/tectonic-cache").resolve())}
            _run([compiler,"--untrusted","--keep-logs","--outdir",str(pdf_dir.resolve()),"main.tex"],paper,output / "latex-build.log",environment=env)
            final = pdf_dir / "cost-aware-bitcoin-research.pdf"
            shutil.copy2(pdf_dir / "main.pdf",final)
            record["pdf"] = {"path":str(final.resolve()),"sha256":digest(final),"compiler":compiler,"compiler_version":version,
                             "limit":"Numeric/data reproduction is checked; PDF bytes may vary with compiler/package/font metadata"}
        record["finished_at"] = utc_now()
        json_write(output / "reproduction.json",record)
        ledger.finish(identifier,"completed",{"output":str(output.resolve()),"report_sha256":digest(output / "reproduction.json")})
        return record
    except Exception as error:
        ledger.finish(identifier,"failed",{"error":str(error),"partial_output":str(output)})
        raise


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results",type=Path,default=ROOT / "results/publication-v1")
    parser.add_argument("--output",type=Path,default=ROOT / "runs" / ("reproduction-" + str(uuid.uuid4())))
    parser.add_argument("--full",action="store_true",help="Rerun all 24+6 cases from exact frozen archives and compare every saved array (~45+ minutes on the original host)")
    parser.add_argument("--tectonic",help="Path to Tectonic 0.17.0")
    parser.add_argument("--verify-only",action="store_true",help="Verify preserved result/source/ledger integrity only")
    args=parser.parse_args()
    if args.full and args.verify_only:
        parser.error("--full and --verify-only are mutually exclusive")
    print(json.dumps(reproduce(args.results.resolve(),args.output.resolve(),full=args.full,tectonic=args.tectonic,verify_only=args.verify_only),indent=2))
