"""Compare the operational bot with every recorded market path in the paper."""
from pathlib import Path
import sys

HOME = Path(__file__).resolve().parents[1]
if str(HOME) not in sys.path:
    sys.path.insert(0, str(HOME))

import argparse
from dataclasses import replace
from datetime import date
import json
import numpy as np

from bot_core import load_csv, save_backtest, settings, source_fingerprint
from paper_engine.data import digest, json_write


def require(condition, context):
    if not condition:
        raise ValueError("Paper parity failed: " + str(context))


def validate(root: Path, output: Path, *, draws=5000):
    root = root.resolve()
    if digest(root / "results/publication-v1/registry.json") != "dd8f573a1c8af69f14ea777a5d6516cdae7f6110fb39c2040a565fb91c5c0c8a":
        raise ValueError("Not the accepted paper result collection")
    output.mkdir(parents=True, exist_ok=False)
    spec = json.loads((root / "configs/research/market-study-v1.json").read_text())
    before = source_fingerprint()
    result = {"status": "started", "source_fingerprint": before, "cases": [],
              "scope": "Retrospective implementation parity, not a new holdout or trading-edge demonstration"}
    json_write(output / "validation.json", result)
    try:
        for case in spec["cases"]:
            s = replace(settings(case["interval"]), symbol=case["symbol"])
            bars = load_csv(root / case["data"], s)
            actual = save_backtest(output / case["id"], bars, s, date.fromisoformat(case["start"]),
                                   date.fromisoformat(case["end"]), draws=draws, case_id=case["id"])
            reference = root / "results/publication-v1/market" / case["id"]
            expected = json.loads((reference / "report.json").read_text())
            require(actual["scored_bars"] == expected["scored_bars"], (case["id"], "scored bars"))
            metric_count = 0
            for cost, scenario in actual["scenarios"].items():
                require(scenario["metrics"] == expected["scenarios"][cost]["metrics"], (case["id"], cost, "metrics"))
                require(scenario["initial_state"] == expected["scenarios"][cost]["initial_state"], (case["id"], cost, "initial state"))
                if draws == 5000:
                    require(scenario["adaptive_minus_fixed"]["bootstrap_by_block_days"] == expected["scenarios"][cost]["adaptive_minus_fixed"]["bootstrap_by_block_days"], (case["id"], cost, "intervals"))
                metric_count += len(scenario["metrics"])
            with np.load(reference / "paths.npz", allow_pickle=False) as a, np.load(output / case["id"] / "paths.npz", allow_pickle=False) as b:
                for name in b.files:
                    require(a[name].dtype == b[name].dtype and np.array_equal(a[name], b[name]), (case["id"], name))
                arrays = len(b.files)
            require(json.loads((output / case["id"] / "selections.json").read_text()) == json.loads((reference / "selections.json").read_text()), (case["id"], "selections"))
            require(json.loads((output / case["id"] / "trades.json").read_text()) == json.loads((reference / "base-cost-trades.json").read_text()), (case["id"], "trades"))
            result["cases"].append({"id": case["id"], "policy_cost_paths": metric_count,
                "arrays_exact": arrays, "all_metrics_initial_states_selections_and_base_trades_exact": True,
                "bootstrap_intervals_exact": draws == 5000, "reference_report_sha256": digest(reference / "report.json"),
                "replay_report_sha256": digest(output / case["id"] / "report.json")})
            json_write(output / "validation.json", result)
            print(f"{case['id']}: {metric_count} policy/cost paths and {arrays} arrays exact", flush=True)
        require(before == source_fingerprint(), "Source changed during parity validation")
        result.update(status="completed", total_policy_cost_paths=sum(c["policy_cost_paths"] for c in result["cases"]),
                      total_arrays_exact=sum(c["arrays_exact"] for c in result["cases"]),
                      conclusion="Implementation matches the paper; no adaptive edge or future profitability established")
        json_write(output / "validation.json", result)
        return result
    except Exception as error:
        json_write(output / "validation.json", {**result, "status": "failed", "error": str(error)})
        raise


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--research-root", type=Path, default=HOME.parents[1])
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    print(json.dumps(validate(args.research_root, args.output), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
