"""Verify preserved substantive results and generate all publication data displays.

No strategy selection, simulation or fitting occurs here. Frozen artifacts are
read-only; all derived outputs identify their original JSON keys and hashes.
"""
from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path

import numpy as np

from quant.data import digest, json_write
from quant.publication import _seal


LABELS = {"oracle_linear": "Oracle", "joint_linear": "Joint", "separate_linear": "Separate",
          "plugin_linear": "Plugin", "symmetric_upper_linear": "Upper both", "joint_hoeffding": "Joint H",
          "separate_hoeffding": "Separate H", "fixed_horizon_hoeffding": "Fixed time", "naive_peek_hoeffding": "Peeked"}
POLICIES = {"fixed": "Fixed EMA 50/200", "adaptive": "Adaptive", "ensemble": "Ensemble", "cash": "Cash",
            "buy_hold": "Buy and hold", "volatility_target": "Volatility target", "slow_resize": "Slow resizing",
            "candidate_25_100": "Fixed EMA 25/100", "candidate_100_400": "Fixed EMA 100/400"}
NUMERICAL_IDENTITY_TOLERANCE = 1e-12


def verify_results(result_root: Path) -> tuple[dict, dict, dict, dict]:
    registry = json.loads((result_root / "registry.json").read_text())
    sim_path, market_path = result_root / registry["simulation"], result_root / registry["market"]
    for path, expected in ((sim_path / "manifest.json", registry["simulation_manifest_sha256"]),
                           (market_path / "manifest.json", registry["market_manifest_sha256"]),
                           (result_root / "attempt-ledger.json", registry["ledger_json_sha256"]),
                           (result_root / "research.sqlite", registry["ledger_sqlite_sha256"])):
        if digest(path) != expected:
            raise ValueError(f"Preserved artifact changed: {path}")
    sm = json.loads((sim_path / "manifest.json").read_text())
    mm = json.loads((market_path / "manifest.json").read_text())
    for key, manifest in (("simulation", sm), ("market", mm)):
        freeze_path = result_root / registry["source_freezes"][key]
        frozen = json.loads(freeze_path.read_text())
        seal = frozen.pop("freeze_sha256")
        archive = freeze_path.parent / frozen["source_snapshot"]
        if seal != _seal(frozen) or seal != manifest["freeze"]["freeze_sha256"] or digest(archive) != frozen["source_snapshot_sha256"]:
            raise ValueError("Frozen run source integrity failed")
    ledger = json.loads((result_root / "attempt-ledger.json").read_text())
    if any(not any(r["id"] == registry[key + "_run_id"] and r["status"] == "completed" for r in ledger) for key in ("simulation", "market")):
        raise ValueError("Parent study completion is missing from the preserved ledger")
    if sm["kind"] != "substantive" or [c["id"] for c in sm["completed"]] != [c["id"] for c in sm["spec"]["cases"]] or mm["status"] != "completed":
        raise ValueError("Results are smoke, partial or failed")
    simulations, markets = {}, {}
    for record in sm["completed"]:
        cid = record["id"]
        if digest(sim_path / (cid + ".json")) != record["json_sha256"] or digest(sim_path / (cid + ".npz")) != record["worlds_sha256"]:
            raise ValueError("Simulation result hash mismatch")
        r = json.loads((sim_path / (cid + ".json")).read_text())
        if r["worlds"] != sm["spec"]["worlds"] or r["calendar_steps"] != sm["spec"]["calendar_steps"] or r["kind"] != "substantive":
            raise ValueError("Unexpected simulation dimensions or kind")
        with np.load(sim_path / (cid + ".npz")) as arrays:
            hit, null = arrays["rejected"], arrays["null_at_birth"]
            if hit.shape != (len(sm["spec"]["methods"]), r["worlds"], r["tested_hypotheses"]) or null.shape != hit.shape[1:]:
                raise ValueError("World arrays have incorrect dimensions")
            for index, name in enumerate(sm["spec"]["methods"]):
                fwer = (hit[index] & null).any(axis=1).mean()
                if abs(fwer - r["methods"][name]["null_family_rejection"]["estimate"]) > 1e-14:
                    raise ValueError("World-array false-rejection rate disagrees with summary")
            if np.any(hit[2] & ~hit[1]):
                raise ValueError("Joint/separate nesting failed")
        simulations[cid] = r
    if [c["case_id"] for c in mm["cases"]] != [c["id"] for c in mm["spec"]["cases"]]:
        raise ValueError("Missing market cases")
    for record in mm["cases"]:
        cid = record["case_id"]
        for name, expected in record["sha256"].items():
            if digest(market_path / cid / name) != expected:
                raise ValueError("Market result hash mismatch")
        markets[cid] = json.loads((market_path / cid / "report.json").read_text())
    return registry, sm, simulations, markets


def paired_path_difference(path: Path, report: dict, cost: str) -> np.ndarray:
    with np.load(path) as arrays:
        returns = {}
        for name in ("adaptive", "fixed"):
            initial = report["scenarios"][cost]["initial_state"][name]["nav"]
            nav = arrays[f"cost{cost}__{name}__nav"]
            returns[name] = np.diff(np.log(np.r_[initial, nav]))
    return returns["adaptive"] - returns["fixed"]


def numerical_identity(values: np.ndarray) -> bool:
    return bool(np.max(np.abs(values)) <= NUMERICAL_IDENTITY_TOLERANCE)


def write_csv(path: Path, rows: list[dict]) -> None:
    with path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def tex(value: str) -> str:
    return value.replace("_", r"\_").replace("%", r"\%").replace("&", r"\&")


def interval(record: dict | None, *, percentage: bool = True, digits: int = 3) -> str:
    if record is None:
        return "--"
    scale = 100 if percentage else 1
    point = f"{record['estimate']*scale:.{digits}f}"
    ci = record.get("confidence_interval")
    return point + (f" [{ci[0]*scale:.{digits}f}, {ci[1]*scale:.{digits}f}]" if ci is not None else r" $^{\ddagger}$")


def _save(fig, output: Path, name: str, plt) -> None:
    fig.savefig(output / (name + ".png"), dpi=300, bbox_inches="tight")
    fig.savefig(output / (name + ".svg"), bbox_inches="tight", metadata={"Date": None})
    plt.close(fig)


def build(result_root: Path, output: Path) -> dict:
    registry, sm, simulations, markets = verify_results(result_root)
    output.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("MPLCONFIGDIR", str((output / "plot-cache").resolve()))
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.ticker import PercentFormatter
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 9, "axes.spines.top": False,
                         "axes.spines.right": False, "svg.hashsalt": "quant-publication-v1"})
    colors = {"oracle_linear": "#646970", "joint_linear": "#176b91", "separate_linear": "#b65730", "plugin_linear": "#6b8c55", "symmetric_upper_linear": "#9465a5"}
    sim_rows, paired_rows, market_rows, contrast_rows = [], [], [], []
    for cid, r in simulations.items():
        for name, values in r["methods"].items():
            row = {"case": cid, "method": name, "worlds": r["worlds"], "calendar_steps": r["calendar_steps"],
                   "assumption_violation": bool(r["case"].get("assumption_violation")), "guarantee": values["guarantee"]}
            for field in ("null_family_rejection", "any_alternative_power", "first_stream_power", "restricted_first_alt_detection_time", "materiality_adjusted_paper_utility", "net_paper_utility"):
                item = values[field]
                row[field] = item["estimate"] if item else None
                ci = item.get("confidence_interval") if item else None
                row[field + "_lower"], row[field + "_upper"] = ci if ci else (None, None)
            row["conditional_detection_median"] = values["median_first_alt_detection_among_detected"]
            row["case_runtime_seconds"] = r["runtime_seconds"]
            row["largest_mixture_state_bytes"] = r["largest_mixture_state_bytes"]
            sim_rows.append(row)
        paired = r["paired_method_comparisons"]
        paired_rows.append({"case": cid, "first_stream_rejection_difference": paired["first_stream_joint_minus_separate_rejection_rate"]["estimate"],
                           "rejection_difference_ci": json.dumps(paired["first_stream_joint_minus_separate_rejection_rate"]["confidence_interval"]),
                           "materiality_utility_difference": paired["joint_minus_separate_materiality_utility"]["estimate"],
                           "utility_difference_ci": json.dumps(paired["joint_minus_separate_materiality_utility"]["confidence_interval"])})
    market_path = result_root / registry["market"]
    for cid, r in markets.items():
        for cost, scenario in r["scenarios"].items():
            difference = paired_path_difference(market_path / cid / "paths.npz", r, cost)
            identical = numerical_identity(difference)
            paired = scenario["adaptive_minus_fixed"]
            ci = paired["bootstrap_by_block_days"]["30"].get("annualized_mean_difference_ci")
            contrast_rows.append({"case": cid, "cost_bps": float(cost), "annualized_log_difference": paired["annualized_mean_log_difference"],
                                  "annual_log_ci_lower": ci[0] if ci else None, "annual_log_ci_upper": ci[1] if ci else None,
                                  "maximum_absolute_per_bar_log_difference": float(np.max(np.abs(difference))), "numerically_identical": identical,
                                  "identity_tolerance_per_bar": NUMERICAL_IDENTITY_TOLERANCE,
                                  "interpretation": "Historical numerical identity; future uncertainty not identified; economic break-even undefined" if identical else paired["inference_status"]})
            for name, values in scenario["metrics"].items():
                market_rows.append({"case": cid, "cost_bps": float(cost), "policy": name, **{k: values[k] for k in ("bars", "total_return", "cagr", "annualized_mean_log_return", "annualized_volatility", "descriptive_sharpe", "maximum_drawdown", "mean_exposure", "turnover", "trade_count", "ending_exposure", "estimated_exit_adjusted_return")},
                                    **{k: scenario["attribution"][name][k] for k in ("between_candles", "execution_cost", "within_candle_holdings", "total_log_return")}})
    write_csv(output / "simulation-all-methods.csv", sim_rows)
    write_csv(output / "simulation-paired-comparisons.csv", paired_rows)
    write_csv(output / "market-all-policies-costs.csv", market_rows)
    write_csv(output / "market-paired-costs.csv", contrast_rows)

    # Every registered method and case is retained in the supplement.
    table = [r"\begingroup\scriptsize", r"\begin{longtable}{llrrrr}",
             r"\caption{All synthetic outcomes. Rates and Wilson intervals are percentages. Time is restricted first-alternative detection time (calendar steps, horizon-censored); utility is mean materiality-adjusted paper utility.}\\",
             r"\toprule Case & Method & Null FWER [95\% CI] & First power [95\% CI] & Time & Utility\\\midrule\endfirsthead",
             r"\toprule Case & Method & Null FWER [95\% CI] & First power [95\% CI] & Time & Utility\\\midrule\endhead"]
    for index, (cid, r) in enumerate(simulations.items(), 1):
        for name, v in r["methods"].items():
            timing = v["restricted_first_alt_detection_time"]
            table.append(f"C{index:02d} & {LABELS[name]} & {interval(v['null_family_rejection'])} & {interval(v['first_stream_power'])} & "
                         + (f"{timing['estimate']:.1f}" if timing else "--") + f" & {v['materiality_adjusted_paper_utility']['estimate']:.3f}\\\\")
    table += [r"\bottomrule\end{longtable}", r"\noindent Null rates remain null rates in mixed families. No independence among candidates is assumed. Plugin, Upper both and Peeked are unguaranteed comparators. All methods in C22 use an explicitly violated cost model; no proxy guarantee is asserted there. Full utility/time uncertainty and runtime/state-array dimensions are in the accompanying CSV.\endgroup", "", r"\begin{longtable}{lp{0.78\textwidth}}\toprule Case & Registered specification key\\\midrule"]
    table += [f"C{i:02d} & \\texttt{{{tex(cid)}}}\\\\" for i, cid in enumerate(simulations, 1)]
    table += [r"\bottomrule\end{longtable}"]
    (output / "simulation-full-table.tex").write_text("\n".join(table) + "\n")

    primary = markets["binance_primary_4h"]
    rows = [r"\begin{tabular}{lrrrrr}\toprule Policy & Return (\%) & Max DD (\%) & Exposure (\%) & Trades & Turnover\\\midrule"]
    for name, v in primary["scenarios"]["25"]["metrics"].items():
        rows.append(f"{tex(POLICIES.get(name,name))} & {100*v['total_return']:.2f} & {100*v['maximum_drawdown']:.2f} & {100*v['mean_exposure']:.1f} & {v['trade_count']} & {v['turnover']:.2f}\\\\")
    rows += [r"\bottomrule\end{tabular}"]
    (output / "market-primary-table.tex").write_text("\n".join(rows) + "\n")
    rows = [r"\begin{tabular}{lrrr}\toprule Case & Annual log diff. (\%) & 30-day interval (\%) & Switches\\\midrule"]
    for row in contrast_rows:
        if row["cost_bps"] != 25:
            continue
        r = markets[row["case"]]
        label = row["case"].replace("binance_", "Binance ").replace("bitstamp_", "Bitstamp ").replace("_", " ")
        point = "0.00$^\\dagger$" if row["numerically_identical"] else f"{row['annualized_log_difference']*100:.2f}"
        bounds = "identical path$^\\dagger$" if row["numerically_identical"] else f"[{100*row['annual_log_ci_lower']:.2f}, {100*row['annual_log_ci_upper']:.2f}]"
        rows.append(f"{label} & {point} & {bounds} & {r['selection_changes_in_window']}\\\\")
    rows += [r"\bottomrule\end{tabular}"]
    (output / "market-comparisons-table.tex").write_text("\n".join(rows) + "\n")

    rows = [r"\begingroup\small\begin{longtable}{lrrrr}",
            r"\caption{All market cost sensitivities. Differences are annualized mean log returns in percent; intervals use 30-day blocks.}\\",
            r"\toprule Case & Cost (bps) & Difference (\%) & Interval (\%) & Identity\\\midrule\endfirsthead",
            r"\toprule Case & Cost (bps) & Difference (\%) & Interval (\%) & Identity\\\midrule\endhead"]
    market_ids = {cid: f"M{i:02d}" for i, cid in enumerate(markets,1)}
    for row in contrast_rows:
        point = "0.00" if row["numerically_identical"] else f"{100*row['annualized_log_difference']:.2f}"
        ci = "historical identity" if row["numerically_identical"] else f"[{100*row['annual_log_ci_lower']:.2f}, {100*row['annual_log_ci_upper']:.2f}]"
        rows.append(f"{market_ids[row['case']]} & {row['cost_bps']:g} & {point} & {ci} & " + ("yes" if row["numerically_identical"] else "no") + r"\\")
    rows += [r"\bottomrule\end{longtable}\endgroup", r"\noindent Numerical identity is defined by maximum absolute per-bar paired log difference at most $10^{-12}$. The full CSV preserves raw floating-point values. Identity rows have no economically interpretable break-even sign bracket.",
             r"\begin{longtable}{lp{0.8\textwidth}}\toprule Case & Market specification key\\\midrule"]
    rows += [f"{label} & \\texttt{{{tex(cid)}}}\\\\" for cid,label in market_ids.items()]
    rows += [r"\bottomrule\end{longtable}"]
    (output / "market-cost-table.tex").write_text("\n".join(rows) + "\n")
    rows = [r"\begingroup\small\begin{longtable}{llrr}", r"\caption{Base-cost adaptive-minus-control contrasts. All intervals are exploratory, unadjusted, 30-day moving-block summaries; differences are annual log units in percent.}\\",
            r"\toprule Case & Control & Difference (\%) & Interval (\%)\\\midrule\endfirsthead",
            r"\toprule Case & Control & Difference (\%) & Interval (\%)\\\midrule\endhead"]
    controls_csv = []
    for cid,r in markets.items():
        for name,v in r["base_cost_adaptive_minus_controls"].items():
            ci = v["bootstrap_by_block_days"]["30"].get("annualized_mean_difference_ci")
            controls_csv.append({"case":cid,"control":name,"annualized_log_difference":v["annualized_mean_log_difference"],"annual_log_ci_lower":ci[0] if ci else None,"annual_log_ci_upper":ci[1] if ci else None})
            # Small EMA spans in the daily/hourly output are recorded exactly.
            label = POLICIES.get(name,name.replace("candidate_","EMA ").replace("_","/"))
            bounds = f"[{ci[0]*100:.2f}, {ci[1]*100:.2f}]" if ci else "unavailable"
            rows.append(f"{market_ids[cid]} & {tex(label)} & {v['annualized_mean_log_difference']*100:.2f} & {bounds}\\\\")
    rows += [r"\bottomrule\end{longtable}\endgroup"]
    (output / "market-control-table.tex").write_text("\n".join(rows) + "\n")
    write_csv(output / "market-control-comparisons.csv", controls_csv)

    fig, axes = plt.subplots(1, 2, figsize=(7, 3), sharey=True, layout="constrained")
    for ax, effect in zip(axes, ("02", "05")):
        for method in ("oracle_linear", "joint_linear", "separate_linear", "plugin_linear"):
            records = [simulations[f"effect{effect}_{s}"]["methods"][method]["first_stream_power"] for s in ("no_overlap", "half_overlap", "equal_turnover")]
            y = np.asarray([r["estimate"] for r in records])
            ci = np.asarray([r["confidence_interval"] for r in records])
            ax.errorbar([0, .5, 1], y, yerr=np.stack([y-ci[:,0], ci[:,1]-y]), color=colors[method], label=LABELS[method], marker="o", markersize=3, linewidth=1, capsize=2)
        ax.set_title(f"Materiality-adjusted effect = 0.{effect}")
        ax.set_xlabel("Reference/candidate turnover ratio")
        ax.set_xticks([0,.5,1]); ax.grid(alpha=.2); ax.yaxis.set_major_formatter(PercentFormatter(1))
    axes[0].set_ylabel("First-stream detection power")
    axes[1].legend(fontsize=7, loc="upper left")
    _save(fig, output, "simulation-power", plt)

    selected = ["null_no_overlap", "null_equal_turnover", "null_search30", "null_births", "weak_prefix_null", "reference_more_turnover", "violated_cost_stationarity"]
    fig, ax = plt.subplots(figsize=(7, 4), layout="constrained")
    for k, method in enumerate(("joint_linear", "separate_linear", "plugin_linear", "symmetric_upper_linear")):
        records = [simulations[c]["methods"][method]["null_family_rejection"] for c in selected]
        y = np.asarray([r["estimate"] for r in records]); ci = np.asarray([r["confidence_interval"] for r in records])
        ax.errorbar(y, np.arange(len(selected))+(k-1.5)*.15, xerr=np.stack([y-ci[:,0],ci[:,1]-y]), label=LABELS[method], color=colors[method], fmt="o", markersize=3, capsize=2, linewidth=.8)
    ax.set_yticks(range(len(selected)), [s.replace("_", " ") for s in selected]); ax.invert_yaxis()
    ax.axvline(.05, color="#333333", linestyle="--", linewidth=.8, label="Nominal family level")
    ax.set_xlabel("True-null family rejection probability (95% Monte Carlo intervals)")
    ax.xaxis.set_major_formatter(PercentFormatter(1)); ax.grid(axis="x", alpha=.2)
    ax.legend(fontsize=7, loc="lower center", bbox_to_anchor=(.5,1.02), ncol=3, frameon=False)
    _save(fig, output, "simulation-validity", plt)

    selected = ["effect05_no_overlap", "effect05_half_overlap", "effect05_equal_turnover", "effect05_search30", "effect05_delay4", "effect05_births", "effect05_no_calibration", "effect05_calibration512"]
    fig, axes = plt.subplots(1, 2, figsize=(7, 4), layout="constrained", sharey=True)
    for k, method in enumerate(("oracle_linear", "joint_linear", "separate_linear")):
        for ax, field in zip(axes, ("restricted_first_alt_detection_time", "materiality_adjusted_paper_utility")):
            records = [simulations[c]["methods"][method][field] for c in selected]
            y = [r["estimate"] for r in records]
            ax.plot(y, np.arange(len(selected))+(k-1)*.15, "o", label=LABELS[method], color=colors[method], markersize=3)
            for j, r in enumerate(records):
                if r["confidence_interval"] is not None:
                    ax.hlines(j+(k-1)*.15, *r["confidence_interval"], color=colors[method], linewidth=.8)
    short_labels = {"no_calibration":"initial calibration = 0", "calibration512":"initial calibration = 512"}
    axes[0].set_yticks(range(len(selected)), [short_labels.get(s.removeprefix("effect05_"),s.removeprefix("effect05_").replace("_", " ")) for s in selected]); axes[0].invert_yaxis()
    axes[0].set_xlabel("Restricted first-alt. detection time")
    axes[1].set_xlabel("Mean additive paper utility")
    axes[1].legend(fontsize=7)
    for ax in axes: ax.grid(axis="x", alpha=.2)
    _save(fig, output, "simulation-delay-utility", plt)

    with np.load(market_path / "binance_primary_4h/paths.npz") as paths:
        dates = [datetime.fromtimestamp(int(t)/1000, timezone.utc) for t in paths["close_time_ms"]]
        fig, axes = plt.subplots(2, 1, figsize=(7, 5), sharex=True, layout="constrained")
        for name in primary["scenarios"]["25"]["metrics"]:
            initial = primary["scenarios"]["25"]["initial_state"][name]["nav"]
            nav = paths[f"cost25__{name}__nav"] / initial
            label = POLICIES.get(name,name)
            style = "--" if name == "adaptive" else "-"
            linewidth = 1.4 if name in ("fixed", "adaptive", "ensemble") else .8
            axes[0].plot(dates, nav, style, label=label, linewidth=linewidth)
            axes[1].plot(dates, nav/np.maximum.accumulate(np.r_[1,nav])[1:]-1, style, linewidth=linewidth)
        axes[0].set_ylabel("Rebased wealth (log scale)"); axes[0].set_yscale("log")
        axes[1].set_ylabel("Drawdown"); axes[1].yaxis.set_major_formatter(PercentFormatter(1))
        axes[0].legend(fontsize=6, ncol=3)
        for ax in axes: ax.grid(alpha=.2)
        _save(fig, output, "market-primary-paths", plt)

    base_rows = [r for r in contrast_rows if r["cost_bps"] == 25]
    fig, ax = plt.subplots(figsize=(7, 3.3), layout="constrained")
    for j, r in enumerate(base_rows):
        if r["numerically_identical"]:
            ax.plot(0,j,"D",color="#646970",markersize=4)
        else:
            point = r["annualized_log_difference"]
            ax.errorbar(point,j,xerr=[[point-r["annual_log_ci_lower"]],[r["annual_log_ci_upper"]-point]],fmt="o",color="#176b91",capsize=3)
    ax.set_yticks(range(len(base_rows)), [r["case"].replace("_"," ") for r in base_rows]); ax.invert_yaxis()
    ax.axvline(0,color="#999999",linewidth=.7); ax.axvline(.02,color="#b65730",linestyle="--",linewidth=.8,label="Materiality")
    ax.set_xlabel("Adaptive-minus-fixed annualized mean log return\n30-day approximate block intervals; diamonds = historical identity")
    ax.xaxis.set_major_formatter(PercentFormatter(1)); ax.grid(axis="x",alpha=.2); ax.legend(fontsize=7)
    _save(fig, output, "market-paired-intervals", plt)

    equal = simulations["effect05_equal_turnover"]["methods"]
    numbers = {"EqualPowerJoint": equal["joint_linear"]["first_stream_power"]["estimate"]*100,
               "EqualPowerSeparate": equal["separate_linear"]["first_stream_power"]["estimate"]*100,
               "HalfPowerJoint": simulations["effect05_half_overlap"]["methods"]["joint_linear"]["first_stream_power"]["estimate"]*100,
               "HalfPowerSeparate": simulations["effect05_half_overlap"]["methods"]["separate_linear"]["first_stream_power"]["estimate"]*100,
               "UpperBothFWER": simulations["reference_more_turnover"]["methods"]["symmetric_upper_linear"]["null_family_rejection"]["estimate"]*100,
               "PluginDriftFWER": simulations["violated_cost_stationarity"]["methods"]["plugin_linear"]["null_family_rejection"]["estimate"]*100,
               "PrimaryFixedReturn": primary["scenarios"]["25"]["metrics"]["fixed"]["total_return"]*100,
               "PrimaryEnsembleReturn": primary["scenarios"]["25"]["metrics"]["ensemble"]["total_return"]*100}
    for label, cid, method, field in (("EqualJoint", "effect05_equal_turnover", "joint_linear", "first_stream_power"),
                                       ("EqualSeparate", "effect05_equal_turnover", "separate_linear", "first_stream_power"),
                                       ("UpperNull", "reference_more_turnover", "symmetric_upper_linear", "null_family_rejection"),
                                       ("PluginDrift", "violated_cost_stationarity", "plugin_linear", "null_family_rejection")):
        lower, upper = simulations[cid]["methods"][method][field]["confidence_interval"]
        numbers[label + "Lower"], numbers[label + "Upper"] = 100*lower, 100*upper
    gain = simulations["effect05_equal_turnover"]["paired_method_comparisons"]["first_stream_joint_minus_separate_rejection_rate"]
    numbers["EqualPowerGain"] = 100*gain["estimate"]
    numbers["EqualGainLower"], numbers["EqualGainUpper"] = [100*x for x in gain["confidence_interval"]]
    numbers["MaxValidJointFWER"] = 100*max(r["methods"]["joint_linear"]["null_family_rejection"]["estimate"] for r in simulations.values() if not r["case"].get("assumption_violation"))
    numbers["ZeroWilsonUpper"] = 100*simulations["null_no_overlap"]["cost_envelope_any_failure"]["confidence_interval"][1]
    (output / "numbers.tex").write_text("% Generated from preserved artifacts.\n" + "\n".join(f"\\newcommand{{\\{k}}}{{{v:.3f}}}" for k,v in numbers.items()) + "\n")
    files = [p for p in output.iterdir() if p.is_file() and p.name != "traceability.json"]
    trace = {"input_registry_sha256": digest(result_root / "registry.json"), "simulation_manifest_sha256": registry["simulation_manifest_sha256"],
             "market_manifest_sha256": registry["market_manifest_sha256"], "generator_sha256": digest(Path(__file__)),
             "simulation_rows": len(sim_rows), "market_policy_cost_rows": len(market_rows), "market_paired_cost_rows": len(contrast_rows),
             "numerical_identity_tolerance_per_bar": NUMERICAL_IDENTITY_TOLERANCE, "post_outcome_note": "docs/publication/reporting-note-01.md",
             "numeric_macro_values": numbers, "source_key_rule": "CSV case/method/policy/cost identifiers map to the matching preserved report JSON. Simulation fields use methods.<method>.<field>; market fields use scenarios.<cost>.metrics/attribution.<policy>.",
             "output_sha256": {p.name: digest(p) for p in sorted(files)}}
    json_write(output / "traceability.json", trace)
    return trace


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--results", type=Path, default=Path("results/publication-v1"))
    p.add_argument("--output", type=Path, default=Path("paper/generated"))
    args = p.parse_args()
    print(json.dumps(build(args.results, args.output), indent=2))
