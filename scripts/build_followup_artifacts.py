"""Rebuild v2 displays from complete preserved results; no fitting or simulation."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import platform
import sqlite3
from types import SimpleNamespace

import numpy as np

from quant.data import digest, json_write
from quant.followup import METHODS
from scripts.collect_followup_results import verify_followup
from scripts.build_publication_artifacts import _save, interval, tex, write_csv


LABELS = {"oracle_linear":"Oracle lin.","joint_linear":"Joint lin.","separate_linear":"Separate lin.",
          "oracle_agrapa":"Oracle aGRAPA","joint_agrapa":"Joint aGRAPA","separate_agrapa":"Separate aGRAPA",
          "oracle_eb":"Oracle EB","joint_local_eb":"Local joint EB","separate_local_eb":"Local sep. EB","joint_coherent_eb":"Coherent EB"}
PAIRS = (("joint_agrapa_minus_joint_linear","aGRAPA - linear"),
         ("joint_coherent_eb_minus_joint_local_eb","Coherent - local EB"),
         ("joint_local_eb_minus_separate_local_eb","Joint - separate EB"))


def verify_collection(root: Path):
    registry = json.loads((root/"registry.json").read_text())
    if registry["kind"]!="followup_v2_result_collection" or registry["cases"]!=25:
        raise ValueError("Unsupported result collection")
    for path,sha in ((root/registry["followup"]/"manifest.json",registry["manifest_sha256"]),
                     (root/"attempt-ledger.json",registry["ledger_json_sha256"]),
                     (root/"research.sqlite",registry["ledger_sqlite_sha256"])):
        if digest(path)!=sha:
            raise ValueError("Preserved follow-up collection changed")
    rows = json.loads((root/"attempt-ledger.json").read_text())
    with sqlite3.connect((root/"research.sqlite").resolve().as_uri()+"?mode=ro",uri=True) as connection:
        connection.row_factory = sqlite3.Row
        stored = [{**dict(row),"details":json.loads(row["details"])} for row in connection.execute("SELECT * FROM attempts ORDER BY created,id")]
    if rows!=stored:
        raise ValueError("JSON and SQLite ledger snapshots disagree")
    freeze = root/registry["source_freezes"]["followup"]
    manifest,frozen,reports = verify_followup(root/registry["followup"],freeze,ledger=SimpleNamespace(rows=lambda:rows))
    if manifest["run_id"]!=registry["followup_run_id"]:
        raise ValueError("Collection and study run identifiers differ")
    return registry,manifest,frozen,reports


def primary_cells(reports):
    return [(cid,r) for cid,r in reports.items() if r["case"]["effect"]==.05 and not r["case"]["prefix_weak"]]


def flatten(reports):
    methods,pairs,calibration = [],[],[]
    for cid,report in reports.items():
        case = report["case"]
        common = {"case":cid,**{k:v for k,v in case.items() if k!="id"}}
        for name,method in report["methods"].items():
            row = {**common,"method":name,"worlds":report["worlds"],"steps":report["steps"],"guarantee":method["guarantee"]}
            for field in ("null_family_rejection","first_stream_rejection","restricted_first_stream_detection_time","materiality_adjusted_paper_utility"):
                value = method[field]
                row[field] = value["estimate"]
                row[field+"_standard_error"] = value["standard_error"]
                ci = value["confidence_interval"]
                row[field+"_lower"],row[field+"_upper"] = ci if ci is not None else (None,None)
            methods.append(row)
        for name,pair in report["paired"].items():
            row = {**common,"contrast":name}
            for field,value in pair.items():
                row[field] = value["estimate"]
                row[field+"_standard_error"] = value["standard_error"]
                row[field+"_lower"],row[field+"_upper"] = value["confidence_interval"] or (None,None)
            pairs.append(row)
        row = {**common,"runtime_seconds":report["runtime_seconds"],"named_state_bytes":report["algorithm_state_bytes"],
               "maximum_support_utility_observed":report["maximum_support_utility_observed"]}
        for field in ("cost_coverage_failure","cost_conflict","cost_conflict_after_final_unused_calibration"):
            row[field] = report[field]["estimate"]
            row[field+"_lower"],row[field+"_upper"] = report[field]["confidence_interval"]
        calibration.append(row)
    return methods,pairs,calibration


def build(root: Path, output: Path) -> dict:
    registry,manifest,frozen,reports = verify_collection(root)
    output.mkdir(parents=True,exist_ok=True)
    methods,pairs,calibration = flatten(reports)
    write_csv(output/"method-results.csv",methods)
    write_csv(output/"paired-results.csv",pairs)
    write_csv(output/"calibration-compute.csv",calibration)
    codes = {cid:f"F{i+1:02}" for i,cid in enumerate(reports)}
    table = [r"\begingroup\scriptsize\setlength{\tabcolsep}{2.5pt}",
             r"\begin{longtable}{llrrrr}",
             r"\caption{All separately specified v2 outcomes. Rates and Wilson intervals are percentages. Time is horizon-censored first-stream time; utility is additive materiality-adjusted paper utility.}\label{tab:followup-full}\\",
             r"\toprule Case & Method & Null rate [95\% CI] & First rej. [95\% CI] & Time & Utility\\\midrule\endfirsthead",
             r"\toprule Case & Method & Null rate [95\% CI] & First rej. [95\% CI] & Time & Utility\\\midrule\endhead"]
    for cid,report in reports.items():
        for name in METHODS:
            method = report["methods"][name]
            label = LABELS[name]+(r" $^{\star}$" if report["case"]["prefix_weak"] and "agrapa" in name else "")
            table.append(f"{codes[cid]} & {label} & {interval(method['null_family_rejection'],digits=2)} & {interval(method['first_stream_rejection'],digits=2)} & {method['restricted_first_stream_detection_time']['estimate']:.1f} & {method['materiality_adjusted_paper_utility']['estimate']:.3f}\\\\")
    table += [r"\bottomrule\end{longtable}",r"$^{\star}$ Unsupported under the prefix-weak null: these rates are diagnostics, not a valid 5\% FWER test. Each other error guarantee is per comparator, not pooled across methods. Full time/utility uncertainty and all paired contrasts are in the CSV files.",r"\endgroup"]
    (output/"full-table.tex").write_text("\n".join(table)+"\n",encoding="utf-8")
    dictionary = [r"\begingroup\small\begin{longtable}{lp{.85\linewidth}}\toprule Case & Specification key\\\midrule"]
    dictionary += [f"{code} & \\texttt{{{tex(cid)}}}\\\\" for cid,code in codes.items()]
    dictionary += [r"\bottomrule\end{longtable}\endgroup"]
    (output/"case-key.tex").write_text("\n".join(dictionary)+"\n",encoding="utf-8")
    table = [r"\begin{table}[tb]\centering",r"\begingroup\small\setlength{\tabcolsep}{3pt}",r"\begin{tabular}{lrrr}\toprule",
             r"Case & aGRAPA - linear & Coherent - local EB & Joint - separate EB\\\midrule"]
    primary = primary_cells(reports)
    for cid,report in primary:
        cells = [interval(report["paired"][pair]["first_stream_rejection_difference"],digits=2) for pair,_ in PAIRS]
        table.append(codes[cid]+" & "+" & ".join(cells)+r"\\")
    table += [r"\bottomrule\end{tabular}",r"\endgroup",
              r"\caption{Prespecified effect-0.05 contrasts in first-stream power, in percentage points. Intervals are paired, approximate, unadjusted 95\% normal Monte Carlo intervals across worlds. $^{\ddagger}$ marks a degenerate sample with an unavailable normal interval, not known zero uncertainty. Case definitions appear in the supplement.}\label{tab:followup-paired}",r"\end{table}"]
    (output/"primary-paired-table.tex").write_text("\n".join(table)+"\n",encoding="utf-8")

    os.environ.setdefault("MPLCONFIGDIR",str((output/"plot-cache").resolve()))
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.ticker import PercentFormatter, FuncFormatter
    plt.rcParams.update({"font.family":"DejaVu Sans","font.size":9,"axes.spines.top":False,"axes.spines.right":False,"svg.hashsalt":"quant-followup-v2"})
    shown = ("oracle_eb","joint_linear","joint_agrapa","joint_local_eb","separate_local_eb","joint_coherent_eb")
    colors = ("#646970","#176b91","#528154","#b65730","#b5a17c","#8351a0")
    fig,axes = plt.subplots(2,2,figsize=(8.5,6.7),sharey=True)
    for row,vol in enumerate((1.,.4)):
        for col,cost in enumerate(("static_initial","contracting")):
            ax = axes[row,col]
            selected = [next(r for _,r in primary if r["case"]["volatility_scale"]==vol and r["case"]["cost_information"]==cost and r["case"]["turnover_pattern"]==pattern) for pattern in ("positive","alternating")]
            for i,(method,color) in enumerate(zip(shown,colors,strict=True)):
                points = np.array([r["methods"][method]["first_stream_rejection"]["estimate"] for r in selected])
                cis = np.array([r["methods"][method]["first_stream_rejection"]["confidence_interval"] for r in selected])
                ax.errorbar(np.arange(2)+(i-2.5)*.075,points,yerr=np.stack((points-cis[:,0],cis[:,1]-points)),color=color,
                            marker="o",markersize=3,capsize=2,linestyle="none",label=LABELS[method])
            ax.set_xticks((0,1),("Positive turnover diff.","Alternating diff."))
            ax.set_title(("High" if vol==1 else "Low")+" volatility; "+("fixed interval" if cost=="static_initial" else "contracting interval"))
            ax.set_ylim(-.02,1.05)
            ax.yaxis.set_major_formatter(PercentFormatter(1))
            ax.grid(axis="y",alpha=.2)
            if col==0:
                ax.set_ylabel("First-stream power")
    handles,labels = axes[0,0].get_legend_handles_labels()
    fig.legend(handles,labels,loc="upper center",ncol=3,frameon=False,bbox_to_anchor=(.5,1.01))
    fig.tight_layout(rect=(0,0,1,.9))
    _save(fig,output,"power",plt)

    fig,ax = plt.subplots(figsize=(8.5,5.5))
    for row,(cid,report) in enumerate(primary):
        for offset,((key,label),color) in enumerate(zip(PAIRS,("#528154","#8351a0","#b65730"),strict=True)):
            point = report["paired"][key]["first_stream_rejection_difference"]
            ci = point["confidence_interval"]
            location = row+(offset-1)*.2
            err = np.array([[point["estimate"]-ci[0]],[ci[1]-point["estimate"]]]) if ci else None
            ax.errorbar([point["estimate"]],[location],xerr=err,color=color,marker="o" if ci else "D",markersize=4,capsize=2,
                        label=label if row==0 else None)
    ax.set_yticks(np.arange(len(primary)),[codes[cid]+": "+("high" if r["case"]["volatility_scale"]==1 else "low")+", "+("static" if r["case"]["cost_information"]=="static_initial" else "contracting")+", "+r["case"]["turnover_pattern"] for cid,r in primary])
    ax.invert_yaxis()
    ax.axvline(0,color="#666666",linestyle="--",linewidth=.8)
    ax.xaxis.set_major_formatter(FuncFormatter(lambda value,_:f"{100*value:g}"))
    ax.set_xlabel("Paired first-stream power difference (percentage points)")
    ax.text(.5,-.2,"Diamonds: degenerate sample; normal interval unavailable",ha="center",va="top",transform=ax.transAxes,fontsize=8)
    ax.grid(axis="x",alpha=.2)
    ax.legend(loc="lower center",bbox_to_anchor=(.5,1.02),ncol=3,frameon=False,fontsize=8)
    fig.tight_layout()
    _save(fig,output,"paired-power",plt)

    eligible = [(cid,name,method["null_family_rejection"]) for cid,r in reports.items() for name,method in r["methods"].items()
                if not (r["case"]["prefix_weak"] and "agrapa" in name)]
    worst = max(eligible,key=lambda item:item[2]["estimate"])
    numbers = {"FollowupSupportedMaxNullRate":100*worst[2]["estimate"]}
    numeric_sources = {"FollowupSupportedMaxNullRate":{"case":worst[0],"method":worst[1],"key":"null_family_rejection.estimate","scale":100}}
    for name,pair in (("Coherent","joint_coherent_eb_minus_joint_local_eb"),("Agra","joint_agrapa_minus_joint_linear"),("JointSeparate","joint_local_eb_minus_separate_local_eb")):
        ordered = sorted(primary,key=lambda item:item[1]["paired"][pair]["first_stream_rejection_difference"]["estimate"])
        for suffix,(cid,r) in (("Min",ordered[0]),("Max",ordered[-1])):
            macro = "Followup"+name+"Gain"+suffix
            numbers[macro] = 100*r["paired"][pair]["first_stream_rejection_difference"]["estimate"]
            numeric_sources[macro] = {"case":cid,"key":"paired."+pair+".first_stream_rejection_difference.estimate","scale":100}
    for cid,method,macro in (("vhigh_static_initial_alternating_e5","joint_coherent_eb","FollowupStaticAltCoherent"),
                             ("vhigh_static_initial_alternating_e5","joint_local_eb","FollowupStaticAltLocal"),
                             ("vhigh_contracting_alternating_e5","joint_coherent_eb","FollowupContractAltCoherent"),
                             ("vhigh_contracting_alternating_e5","joint_local_eb","FollowupContractAltLocal")):
        numbers[macro] = 100*reports[cid]["methods"][method]["first_stream_rejection"]["estimate"]
        numeric_sources[macro] = {"case":cid,"method":method,"key":"first_stream_rejection.estimate","scale":100}
    (output/"numbers.tex").write_text("% Generated from preserved v2 outputs.\n"+"\n".join(f"\\newcommand{{\\{key}}}{{{value:.3f}}}" for key,value in numbers.items())+"\n",encoding="utf-8")
    files = sorted(p for p in output.iterdir() if p.is_file() and p.name!="traceability.json")
    trace = {"input_registry_sha256":digest(root/"registry.json"),"input_manifest_sha256":registry["manifest_sha256"],
             "source_freeze_seal":frozen["freeze_sha256"],"generator_sha256":digest(Path(__file__)),
             "helper_sources_sha256":{name:digest(Path(__file__).resolve().parents[1]/name) for name in
                 ("scripts/collect_followup_results.py","scripts/build_publication_artifacts.py","src/quant/followup.py",
                  "src/quant/publication.py","src/quant/data.py","src/quant/ledger.py","uv.lock")},
             "display_runtime":{"python":platform.python_version(),"numpy":np.__version__,"matplotlib":matplotlib.__version__,"platform":platform.platform()},
             "cases":len(reports),"method_rows":len(methods),"paired_rows":len(pairs),"calibration_rows":len(calibration),
             "numeric_macro_values":numbers,"numeric_macro_sources":numeric_sources,"case_codes":codes,
             "output_sha256":{p.name:digest(p) for p in files},
             "limits":"No refitting; paired factorial cells are dependent; intervals are unadjusted Monte Carlo summaries. Runtime excludes serialization and is not a controlled benchmark."}
    json_write(output/"traceability.json",trace)
    return trace


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results",type=Path,default=Path("results/publication-v2"))
    parser.add_argument("--output",type=Path,default=Path("paper/generated/followup"))
    args = parser.parse_args()
    print(json.dumps(build(args.results,args.output),indent=2))
