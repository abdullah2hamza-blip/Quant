"""Preserve a completed, frozen v2 study and validate its saved-world summaries."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
from zipfile import ZipFile

import numpy as np

from quant.data import digest, json_write
from quant.followup import METHODS, SPEC
from quant.ledger import Ledger, code_hash, utc_now
from quant.publication import _seal, mean_interval, wilson


ROOT = Path(__file__).resolve().parents[1]


def _same(actual, expected, label):
    if isinstance(expected,dict):
        if not isinstance(actual,dict) or actual.keys()!=expected.keys():
            raise ValueError(f"Summary fields differ: {label}")
        for key,value in expected.items():
            _same(actual[key],value,label+"."+key)
    elif type(expected) is float:
        if type(actual) not in (float,int) or not np.isfinite(actual) or not np.isclose(actual,expected,atol=1e-12,rtol=1e-12):
            raise ValueError(f"Summary value differs: {label}")
    elif isinstance(expected,list):
        if not isinstance(actual,list) or len(actual)!=len(expected):
            raise ValueError(f"Summary interval differs: {label}")
        for i,value in enumerate(expected):
            _same(actual[i],value,label+f"[{i}]")
    elif actual!=expected or type(actual) is not type(expected):
        raise ValueError(f"Summary exact value differs: {label}")


def verify_followup(study: Path, freeze: Path, *, ledger: Ledger|None = None) -> tuple[dict,dict,dict]:
    manifest = json.loads((study/"manifest.json").read_text())
    if manifest["kind"] != "substantive" or not manifest.get("completed_at"):
        raise ValueError("Only a completed substantive follow-up can be collected")
    frozen = json.loads(freeze.read_text())
    payload = {k:v for k,v in frozen.items() if k!="freeze_sha256"}
    archive = freeze.parent/frozen["source_snapshot"]
    if frozen.get("kind")!="followup_v2_freeze" or _seal(payload)!=frozen["freeze_sha256"] or digest(archive)!=frozen["source_snapshot_sha256"]:
        raise ValueError("Changed follow-up freeze/source archive")
    if manifest["code_sha256"]!=frozen["code_sha256"] or manifest["spec_sha256"]!=frozen["spec_sha256"]:
        raise ValueError("Run and freeze fingerprints differ")
    if manifest["freeze"]!={"source_file":freeze.name,"file_sha256":digest(freeze),"payload":frozen}:
        raise ValueError("Run lacks its exact sealed freeze attachment")
    if any(manifest["runtime"][k]!=v for k,v in frozen["runtime"].items()):
        raise ValueError("Run and frozen runtime differ")
    with ZipFile(archive) as source:
        import hashlib
        def check_member(name,sha):
            if hashlib.sha256(source.read(name)).hexdigest()!=sha:
                raise ValueError("Archived document/specification hash differs")
        check_member(SPEC.as_posix(),frozen["spec_sha256"])
        if json.loads(source.read(SPEC.as_posix()))!=manifest["spec"]:
            raise ValueError("Manifest specification differs from actual archived input")
        for item in frozen["documents"]:
            check_member(item["path"],item["sha256"])
    cases = manifest["spec"]["cases"]
    ids = [case["id"] for case in cases]
    if len(cases)!=25 or len(set(ids))!=25 or [c["case_id"] for c in manifest["cases"]]!=ids:
        raise ValueError("Follow-up case set/order is incomplete")
    if {p.name for p in study.iterdir()}!={"manifest.json",*(cid+ext for cid in ids for ext in (".json",".npz"))}:
        raise ValueError("Unexpected or missing follow-up files")
    if ledger is not None:
        rows = {row["id"]:row for row in ledger.rows()}
        parent = rows.get(manifest["run_id"],{})
        if parent.get("status")!="completed" or parent.get("kind")!="followup_v2":
            raise ValueError("No completed parent follow-up ledger attempt")
        if (parent.get("code_hash")!=frozen["code_sha256"] or parent.get("details",{}).get("smoke") is not False
                or parent.get("details",{}).get("outcome",{}).get("manifest_sha256")!=digest(study/"manifest.json")):
            raise ValueError("Parent ledger receipt does not bind this manifest/source")
        attempts = [record["attempt_id"] for record in manifest["cases"]]
        if len(set(attempts))!=len(attempts):
            raise ValueError("Follow-up child ledger attempt IDs are not unique")
        for case,record in zip(cases,manifest["cases"],strict=True):
            row = rows.get(record["attempt_id"],{})
            details = row.get("details",{})
            if row.get("status")!="completed" or row.get("kind")!="followup_v2_case" or details.get("parent")!=manifest["run_id"]:
                raise ValueError("No matching completed child follow-up ledger attempt")
            if (row.get("code_hash")!=frozen["code_sha256"] or details.get("smoke") is not False
                    or _seal(details.get("case"))!=_seal(case)
                    or details.get("outcome",{}).get("report_sha256")!=record["report_sha256"]):
                raise ValueError("Child ledger receipt does not bind this exact case/source/report")
    reports = {}
    for case,record in zip(cases,manifest["cases"],strict=True):
        cid = case["id"]
        report_file,world_file = study/(cid+".json"),study/(cid+".npz")
        if digest(report_file)!=record["report_sha256"] or digest(world_file)!=record["arrays_sha256"]:
            raise ValueError("Changed follow-up case artifact")
        report = json.loads(report_file.read_text())
        if report["arrays_sha256"]!=record["arrays_sha256"] or report["case"]!=case or report["kind"]!="substantive" or (report["worlds"],report["steps"],report["hypotheses"])!=(4000,800,10):
            raise ValueError("Case identity/dimensions differ")
        with np.load(world_file,allow_pickle=False) as stored:
            arrays = {key:stored[key] for key in stored.files}
        required = {"hits","first_crossing","selected","materiality_adjusted_utility","true_null","cost_coverage_failed","cost_conflict","cost_conflict_after_final_unused_calibration","final_log_components"}
        if set(arrays)!=required or arrays["hits"].shape!=(10,4000,10) or arrays["hits"].dtype!=bool or arrays["first_crossing"].shape!=(10,4000,10):
            raise ValueError("Unexpected saved-world schema")
        hits,first = arrays["hits"],arrays["first_crossing"]
        if first.dtype.kind not in "iu" or np.any((first<1)|(first>801)) or not np.array_equal(hits,first<=800):
            raise ValueError("Crossing timing/events disagree")
        null = np.ones(10,dtype=bool)
        if not case["prefix_weak"] and case["effect"]>0:
            null[0] = False
        if not np.array_equal(null,arrays["true_null"]) or arrays["true_null"].dtype!=bool:
            raise ValueError("Known-truth mask differs")
        selected = np.where(hits.any(axis=2),first.argmin(axis=2),-1)
        if arrays["selected"].dtype.kind not in "iu" or not np.array_equal(arrays["selected"],selected):
            raise ValueError("Selected stream is not the first discovery")
        utility = arrays["materiality_adjusted_utility"]
        if utility.shape!=(10,4000) or not np.isfinite(utility).all() or np.any(utility[(first.min(axis=2)>=800)]!=0):
            raise ValueError("Utility shape, finiteness or activation timing differs")
        for key in ("cost_coverage_failed","cost_conflict","cost_conflict_after_final_unused_calibration"):
            if arrays[key].shape!=(4000,) or arrays[key].dtype!=bool:
                raise ValueError("Coverage/conflict world schema differs")
            label = "cost_coverage_failure" if key=="cost_coverage_failed" else key
            _same(report[label],wilson(arrays[key]),cid+"."+key)
        components = arrays["final_log_components"]
        if components.shape!=(10,4000,10,5) or not np.isfinite(components).all():
            raise ValueError("Component state differs")
        supported = ~arrays["cost_conflict"][:,None,None]
        if np.any((components[9]<components[7]-1e-9)&supported) or np.any((components[7]<components[8]-1e-9)&supported):
            raise ValueError("Matched cost-profile component ordering fails")
        covered = ~arrays["cost_coverage_failed"][:,None,None]
        for lower,upper in ((2,1),(1,0),(8,7),(7,9),(9,6)):
            if np.any((components[lower]>components[upper]+1e-9)&covered):
                raise ValueError("Fixed-component latent/profile ordering fails on coverage")
            if np.any(hits[lower]&~hits[upper]&covered[:,:,0]):
                raise ValueError("Fixed-component crossing inclusion fails on coverage")
        if any(not np.array_equal(components[i],np.repeat(components[i,...,:1],5,axis=-1)) for i in (3,4,5)):
            raise ValueError("Adaptive single-product slots differ")
        if set(report["methods"])!=set(METHODS):
            raise ValueError("Method family differs")
        for i,name in enumerate(METHODS):
            method = report["methods"][name]
            _same(method["null_family_rejection"],wilson(hits[i][:,null].any(axis=1)),cid+"."+name+".FWER")
            _same(method["first_stream_rejection"],wilson(hits[i,:,0]),cid+"."+name+".first")
            _same(method["restricted_first_stream_detection_time"],mean_interval(np.minimum(first[i,:,0],800)),cid+"."+name+".time")
            _same(method["materiality_adjusted_paper_utility"],mean_interval(utility[i]),cid+"."+name+".utility")
            if case["prefix_weak"] and "agrapa" in name and "unsupported" not in method["guarantee"]:
                raise ValueError("Adaptive betting has an unsupported weak-null claim")
        for left,right in ((4,1),(9,7),(7,8),(1,2),(4,5),(6,0)):
            key = METHODS[left]+"_minus_"+METHODS[right]
            _same(report["paired"][key]["first_stream_rejection_difference"],mean_interval(hits[left,:,0].astype(float)-hits[right,:,0]),cid+"."+key)
            _same(report["paired"][key]["utility_difference"],mean_interval(utility[left]-utility[right]),cid+"."+key+".utility")
        reports[cid] = report
    return manifest,frozen,reports


def collect(study: Path, freeze: Path, output: Path) -> dict:
    ledger = Ledger(ROOT/"runs/research.sqlite")
    identifier = ledger.start("followup_v2_collection",{"study":str(study),"freeze":str(freeze),"output":str(output)},code=code_hash(ROOT))
    try:
        manifest,frozen,reports = verify_followup(study,freeze,ledger=ledger)
        if output.exists():
            raise ValueError("Preserve earlier result collections")
        shutil.copytree(study,output/"study")
        snapshots = output/"source-snapshots"
        snapshots.mkdir()
        for path in (freeze,freeze.parent/frozen["source_snapshot"]):
            shutil.copy2(path,snapshots/path.name)
        with ledger.connect() as source:
            import sqlite3
            with sqlite3.connect(output/"research.sqlite") as destination:
                source.backup(destination)
        json_write(output/"attempt-ledger.json",Ledger(output/"research.sqlite").rows())
        registry = {"kind":"followup_v2_result_collection","created_at":utc_now(),"collection_attempt":identifier,
                    "followup":"study","followup_run_id":manifest["run_id"],"cases":len(reports),
                    "manifest_sha256":digest(output/"study/manifest.json"),"source_freezes":{"followup":"source-snapshots/"+freeze.name},
                    "ledger_json_sha256":digest(output/"attempt-ledger.json"),"ledger_sqlite_sha256":digest(output/"research.sqlite"),
                    "ledger_snapshot_timing":"Consistent pre-finalization snapshot; this collection's own row is still started. Terminal collection receipt is in the live ledger.",
                    "limits":"Mechanical summary/integrity validation; separate independent outcome review and full replay still required"}
        json_write(output/"registry.json",registry)
        ledger.finish(identifier,"completed",{"output":str(output),"registry_sha256":digest(output/"registry.json")})
        return registry
    except Exception as error:
        ledger.finish(identifier,"failed",{"error":str(error),"partial_output":str(output)})
        raise


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--study",type=Path,required=True)
    parser.add_argument("--freeze",type=Path,required=True)
    parser.add_argument("--output",type=Path,default=Path("results/publication-v2"))
    args = parser.parse_args()
    print(json.dumps(collect(args.study,args.freeze,args.output),indent=2))
