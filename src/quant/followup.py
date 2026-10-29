"""Separately specified v2 diagnostic: variance adaptation and cost coherence.

Established methods only. Strong-null aGRAPA and prefix-weak fixed mixtures
have different guarantees. No financial-return or new-theorem guarantee.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import platform
import time

import numpy as np

from quant.data import digest, json_write
from quant.ledger import Ledger, code_hash, utc_now
from quant.publication import _calibration_bounds, _mixture, _seal, _snapshot_source, mean_interval, wilson


ROOT = Path(__file__).resolve().parents[2]
SPEC = Path("configs/research/followup-study-v2.json")
PROTOCOL = Path("docs/publication/followup-protocol-v2.md")
REVIEW = Path("docs/publication/reviews/followup-methods-01.md")
METHODS = ("oracle_linear", "joint_linear", "separate_linear", "oracle_agrapa", "joint_agrapa", "separate_agrapa",
           "oracle_eb", "joint_local_eb", "separate_local_eb", "joint_coherent_eb")


def load_spec(path: Path) -> dict:
    spec = json.loads(path.read_text(encoding="utf-8"))
    expected = {"schema_version", "study_id", "worlds", "steps", "hypotheses", "seed", "alpha", "delta", "bound", "true_cost", "cost_cap", "initial_calibration", "materiality", "linear_grid", "eb_grid", "methods", "cases"}
    if set(spec) != expected or spec["schema_version"] != 2 or spec["study_id"] != "variance-and-coherence-v2":
        raise ValueError("Unsupported v2 specification")
    fixed = {"worlds":4000,"steps":800,"hypotheses":10,"seed":20261023,"alpha":.05,"delta":.01,"bound":1.,
             "true_cost":.08,"cost_cap":.2,"initial_calibration":32,"materiality":.01,
             "linear_grid":[.05,.1,.2,.4,.8],"eb_grid":[.025,.05,.1,.2,.4]}
    if any(type(spec[key]) is bool or spec[key] != value or (type(value) is int and type(spec[key]) is not int)
           for key,value in fixed.items()) or tuple(spec["methods"]) != METHODS:
        raise ValueError("Changed fixed v2 design; use a new version")
    factorial = {(vol,cost,pattern,effect,False) for vol in (1.,.4) for cost in ("static_initial","contracting")
                 for pattern in ("positive","alternating") for effect in (0.,.02,.05)}
    factorial.add((1.,"contracting","positive",0.,True))
    found = set()
    ids = set()
    for case in spec["cases"]:
        if set(case) != {"id","effect","turnover_pattern","cost_information","volatility_scale","prefix_weak"} or not isinstance(case["prefix_weak"],bool):
            raise ValueError("Invalid v2 case")
        if any(type(case[key]) not in (int,float) or not math.isfinite(case[key]) for key in ("effect","volatility_scale")):
            raise ValueError("Case numerical fields must be finite numbers, not booleans")
        if not isinstance(case["id"],str) or not case["id"] or any(ch not in "abcdefghijklmnopqrstuvwxyz0123456789_" for ch in case["id"]) or case["id"] in ids:
            raise ValueError("Invalid or duplicate v2 identifier")
        ids.add(case["id"])
        found.add((case["volatility_scale"],case["cost_information"],case["turnover_pattern"],case["effect"],case["prefix_weak"]))
    if len(spec["cases"]) != 25 or found != factorial:
        raise ValueError("Incomplete or changed v2 factorial")
    return spec


def eb_log_factor(utility, center, lambdas):
    """Established centered empirical-Bernstein factor; deliberately nonmonotone."""
    utility, center, lambdas = np.asarray(utility),np.asarray(center),np.asarray(lambdas)
    psi = (-np.log1p(-2*lambdas)-2*lambdas)/4
    return utility[...,None]*lambdas - (utility-center)[...,None]**2*psi


def coherent_eb_log_components(sums, lower, upper, lambdas):
    sa,sd,qaa,qad,qdd = sums
    lambdas = np.asarray(lambdas)
    psi = (-np.log1p(-2*lambdas)-2*lambdas)/4
    def at(theta):
        linear = sa - sd*theta
        quadratic = qaa - 2*qad*theta + qdd*theta**2
        return linear[...,None]*lambdas - quadratic[...,None]*psi
    return np.minimum(at(lower),at(upper))


def agrapa_stake(total, squares, observations):
    """One-sided specialization on normalized [-1,1] scores, past values only."""
    if observations == 0:
        return np.full_like(total,.1)
    return np.clip(np.divide(total,squares,out=np.zeros_like(total),where=squares>0),0.,.8)


def simulate(spec: dict, case: dict, *, smoke: bool = False) -> tuple[dict,dict]:
    started = time.perf_counter()
    w,tmax,h = (128,60,spec["hypotheses"]) if smoke else (spec["worlds"],spec["steps"],spec["hypotheses"])
    seed = np.random.SeedSequence(spec["seed"]).spawn(2)
    outcomes, calibration = (np.random.default_rng(s) for s in seed)
    shape = (w,h)
    logs = np.zeros((len(METHODS),w,h,5))
    first = np.full((len(METHODS),w,h),tmax+1,dtype=np.int64)
    hits = np.zeros_like(first,dtype=bool)
    selected = np.full((len(METHODS),w),-1,dtype=np.int64)
    utility = np.zeros((len(METHODS),w))
    adapt_total,adapt_squares = np.zeros((3,w,h)),np.zeros((3,w,h))
    plugin_total = np.zeros(shape)
    sums = np.zeros((5,w,h))
    n = spec["initial_calibration"]
    cal_total = calibration.binomial(n,spec["true_cost"]/spec["cost_cap"],w)*spec["cost_cap"]
    lo,hi = _calibration_bounds(cal_total,n,spec["cost_cap"],spec["delta"])
    conflict,coverage_failed = np.zeros(w,dtype=bool),np.zeros(w,dtype=bool)
    used_conflict = np.zeros(w,dtype=bool)
    previous = np.zeros(w)
    linear_grid,eb_grid = np.asarray(spec["linear_grid"]),np.asarray(spec["eb_grid"])
    threshold = -math.log((spec["alpha"]-spec["delta"])/h)
    trace = []
    max_support_utility = 0.
    for step in range(tmax):
        # Everything through stake and center calculation precedes current shocks.
        positive = case["turnover_pattern"] == "positive" or (step//20)%2 == 0
        qa,qr = (.8,.4) if positive else (.4,.8)
        d = qa-qr
        center = np.clip(plugin_total/max(1,step),-1.,1.)
        stakes = agrapa_stake(adapt_total,adapt_squares,step)
        used_conflict |= conflict
        coverage_failed |= (lo>spec["true_cost"]) | (hi<spec["true_cost"]) | conflict
        sigma = case["volatility_scale"]*(.2+.1*(1+math.sin(2*math.pi*step/80))+.15*(previous>0))
        common = outcomes.choice([-1.,1.],w)
        individual = outcomes.choice([-1.,1.],shape)
        latent = sigma[:,None]*(.6*common[:,None]+.4*individual)
        if case["prefix_weak"]:
            latent += -.06 if step<tmax//2 else .06
        else:
            latent[:,0] += case["effect"]
        a = latent+d*spec["true_cost"]
        joint_low = a-np.maximum(d*lo[:,None],d*hi[:,None])
        joint_high = a-np.minimum(d*lo[:,None],d*hi[:,None])
        separate_low = a-qa*hi[:,None]+qr*lo[:,None]
        separate_high = a-qa*lo[:,None]+qr*hi[:,None]
        max_support_utility = max(max_support_utility,float(max(np.max(np.abs(x)) for x in
                                  (latent,a,a-d*spec["cost_cap"],a-qa*spec["cost_cap"],a+qr*spec["cost_cap"]))))
        if max_support_utility>spec["bound"]:
            raise ValueError("Generator violates the specified known bound; clipping is forbidden")
        for method in range(len(METHODS)):
            eligible = selected[method]>=0
            rows = np.flatnonzero(eligible)
            utility[method,rows] += latent[rows,selected[method,rows]]
        base = np.stack((latent,joint_low,separate_low))
        for i in range(3):
            logs[i] += np.log1p(base[i,...,None]*linear_grid)
            # Store a single adaptive product replicated over mixture slots;
            # the mixture is then exactly the same one product, not five tests.
            logs[3+i] += np.log1p(stakes[i]*base[i])[...,None]
        logs[6] += eb_log_factor(latent,center,eb_grid)
        logs[7] += np.minimum(eb_log_factor(joint_low,center,eb_grid),eb_log_factor(joint_high,center,eb_grid))
        logs[8] += np.minimum(eb_log_factor(separate_low,center,eb_grid),eb_log_factor(separate_high,center,eb_grid))
        centered = a-center
        sums[0] += a
        sums[1] += d
        sums[2] += centered**2
        sums[3] += centered*d
        sums[4] += d*d
        logs[9] = coherent_eb_log_components(sums,lo[:,None],hi[:,None],eb_grid)
        if np.any((logs[9] < logs[7]-1e-9) & ~conflict[:,None,None]):
            raise ValueError("Nested-set coherent/local component dominance failed")
        evidence = _mixture(logs)
        new = evidence>=threshold
        new[[1,2,4,5,7,8,9]] &= ~conflict[None,:,None]
        first[new & ~hits] = step+1
        hits |= new
        for method in range(len(METHODS)):
            available = (selected[method]<0) & hits[method].any(axis=1)
            selected[method,available] = hits[method,available].argmax(axis=1)
        if step in (0,tmax//2-1,tmax-1):
            trace.append({"label":step+1,"world":0,"cost_interval":[float(lo[0]),float(hi[0])],"calibration_n":n,
                          "first_stream_log_evidence":evidence[:,0,0].tolist(),"first_stream_center":float(center[0,0])})
        adapt_total += base
        adapt_squares += base**2
        plugin_total += a-d*(cal_total/n)[:,None]
        sample = calibration.binomial(1,spec["true_cost"]/spec["cost_cap"],w)*spec["cost_cap"]
        if case["cost_information"] == "contracting":
            cal_total += sample
            n += 1
            fresh_lo,fresh_hi = _calibration_bounds(cal_total,n,spec["cost_cap"],spec["delta"])
            lo,hi = np.maximum(lo,fresh_lo),np.minimum(hi,fresh_hi)
            conflict |= lo>hi
        previous = common
    null = np.ones(h,dtype=bool)
    if not case["prefix_weak"] and case["effect"]>0:
        null[0] = False
    summary = {}
    for i,method in enumerate(METHODS):
        guarantee = "prefix-weak null: alpha_test + global simultaneous-coverage failure"
        if "agrapa" in method:
            guarantee = "unsupported under prefix-weak diagnostic" if case["prefix_weak"] else "strong conditional null only: alpha_test + global simultaneous-coverage failure"
        if method.startswith("oracle"):
            guarantee += "; oracle needs no cost coverage allocation (same test thresholds retained)"
        summary[method] = {"null_family_rejection":wilson(hits[i][:,null].any(axis=1)),
                           "first_stream_rejection":wilson(hits[i,:,0]),
                           "restricted_first_stream_detection_time":mean_interval(np.minimum(first[i,:,0],tmax)),
                           "materiality_adjusted_paper_utility":mean_interval(utility[i]),"guarantee":guarantee}
    pairs = {}
    for left,right in ((4,1),(9,7),(7,8),(1,2),(4,5),(6,0)):
        key = METHODS[left]+"_minus_"+METHODS[right]
        pairs[key] = {"first_stream_rejection_difference":mean_interval(hits[left,:,0].astype(float)-hits[right,:,0]),
                      "utility_difference":mean_interval(utility[left]-utility[right])}
    arrays = {"hits":hits,"first_crossing":first,"selected":selected,"materiality_adjusted_utility":utility,
              "true_null":null,"cost_coverage_failed":coverage_failed,"cost_conflict":used_conflict,
              "cost_conflict_after_final_unused_calibration":conflict,"final_log_components":logs}
    report = {"case":case,"kind":"smoke" if smoke else "substantive","worlds":w,"steps":tmax,"hypotheses":h,
              "methods":summary,"paired":pairs,"cost_coverage_failure":wilson(coverage_failed),"cost_conflict":wilson(used_conflict),
              "cost_conflict_after_final_unused_calibration":wilson(conflict),
              "trace":trace,"runtime_seconds":time.perf_counter()-started,"algorithm_state_bytes":sum(x.nbytes for x in
                  (logs,first,hits,selected,utility,adapt_total,adapt_squares,plugin_total,sums,lo,hi,conflict,used_conflict,coverage_failed,previous,cal_total,linear_grid,eb_grid)),
              "memory_limit":"Named persistent state arrays, not process peak memory or transient NumPy allocations",
              "maximum_support_utility_observed":max_support_utility,
              "utility_convention":"Additive materiality-adjusted latent utility; first discovered lowest-index stream active only on subsequent labels; no funded compounding",
              "coupling":"Same underlying innovations by world index across cases; independent worlds, dependent streams and paired factorial cells"}
    return report,arrays


def freeze(output: Path) -> dict:
    ledger = Ledger(ROOT/"runs/research.sqlite")
    identifier = ledger.start("followup_v2_freeze",{"output":str(output)},code=code_hash(ROOT))
    try:
        spec = load_spec(ROOT/SPEC)
        if output.exists() or not (ROOT/REVIEW).is_file():
            raise ValueError("Existing freeze or missing independent methods review")
        documents = [ROOT/PROTOCOL,ROOT/REVIEW]
        archive = output.with_suffix(".sources.zip")
        result = {"kind":"followup_v2_freeze","created_at":utc_now(),"spec_sha256":digest(ROOT/SPEC),
                  "code_sha256":code_hash(ROOT),"runtime":{"python":platform.python_version(),"numpy":np.__version__},
                  "source_snapshot":archive.name,"source_snapshot_sha256":_snapshot_source(ROOT,archive,documents),
                  "documents":[{"path":p.relative_to(ROOT).as_posix(),"sha256":digest(p)} for p in documents],
                  "cases":len(spec["cases"]),"scope":"Separately specified after all v1 outcomes; established-method diagnostics only"}
        result["freeze_sha256"] = _seal(result)
        json_write(output,result)
        ledger.finish(identifier,"completed",{"freeze":str(output),"sha256":digest(output)})
        return result
    except Exception as error:
        ledger.finish(identifier,"failed",{"error":str(error)})
        raise


def run(output: Path, frozen: Path|None, *, smoke: bool = False, ledger_path: Path|None = None) -> dict:
    ledger = Ledger(ledger_path or ROOT/"runs/research.sqlite")
    identifier = ledger.start("followup_v2",{"output":str(output),"smoke":smoke,"freeze":str(frozen)},code=code_hash(ROOT))
    try:
        spec = load_spec(ROOT/SPEC)
        frozen_record = None
        if not smoke:
            if frozen is None:
                raise ValueError("Substantive follow-up requires a reviewed source freeze")
            saved = json.loads(frozen.read_text())
            seal = saved.pop("freeze_sha256",None)
            if seal != _seal(saved) or saved["kind"] != "followup_v2_freeze" or saved["code_sha256"] != code_hash(ROOT) or saved["spec_sha256"] != digest(ROOT/SPEC):
                raise ValueError("Follow-up source/specification freeze mismatch")
            if saved["runtime"] != {"python":platform.python_version(),"numpy":np.__version__} or digest(frozen.parent/saved["source_snapshot"]) != saved["source_snapshot_sha256"]:
                raise ValueError("Changed runtime or source archive")
            if any(digest(ROOT/d["path"]) != d["sha256"] for d in saved["documents"]):
                raise ValueError("Changed protocol or independent review")
            frozen_record = {"source_file":frozen.name,"file_sha256":digest(frozen),"payload":{**saved,"freeze_sha256":seal}}
        if output.exists():
            raise ValueError("Preserve earlier follow-up attempts; choose a new output")
        output.mkdir(parents=True)
        manifest = {"run_id":identifier,"kind":"smoke" if smoke else "substantive","created_at":utc_now(),"spec":spec,
                    "spec_sha256":digest(ROOT/SPEC),"code_sha256":code_hash(ROOT),"freeze":frozen_record,
                    "runtime":{"python":platform.python_version(),"numpy":np.__version__,"platform":platform.platform()},"cases":[]}
        json_write(output/"manifest.json",manifest)
        for case in spec["cases"]:
            child = ledger.start("followup_v2_case",{"parent":identifier,"case":case,"smoke":smoke},code=manifest["code_sha256"])
            try:
                report,arrays = simulate(spec,case,smoke=smoke)
                report_path,arrays_path = output/(case["id"]+".json"),output/(case["id"]+".npz")
                np.savez_compressed(arrays_path,**arrays)
                report["arrays_sha256"] = digest(arrays_path)
                json_write(report_path,report)
                manifest["cases"].append({"case_id":case["id"],"attempt_id":child,"report_sha256":digest(report_path),"arrays_sha256":digest(arrays_path)})
                json_write(output/"manifest.json",manifest)
                ledger.finish(child,"completed",{"report":str(report_path),"report_sha256":digest(report_path)})
                print(json.dumps({"completed_case":case["id"],"runtime_seconds":report["runtime_seconds"]}),flush=True)
            except Exception as error:
                ledger.finish(child,"failed",{"error":str(error)})
                raise
        manifest["completed_at"] = utc_now()
        json_write(output/"manifest.json",manifest)
        ledger.finish(identifier,"completed",{"output":str(output),"manifest_sha256":digest(output/"manifest.json")})
        return manifest
    except Exception as error:
        ledger.finish(identifier,"failed",{"error":str(error),"partial_output":str(output)})
        raise


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action",choices=("freeze","run"))
    parser.add_argument("--output",type=Path,required=True)
    parser.add_argument("--freeze",type=Path)
    parser.add_argument("--smoke",action="store_true")
    parser.add_argument("--ledger",type=Path)
    args = parser.parse_args()
    result = freeze(args.output) if args.action == "freeze" else run(args.output,args.freeze,smoke=args.smoke,ledger_path=args.ledger)
    print(json.dumps(result,indent=2))
