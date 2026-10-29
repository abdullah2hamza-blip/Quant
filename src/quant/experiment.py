"""Reproducible backtest artifacts and explicit retrospective access controls."""
from __future__ import annotations

import csv
from dataclasses import asdict
from datetime import timedelta
import hashlib
import json
import platform
from pathlib import Path
import sys

import numpy as np

from .config import Settings
from .data import Bars, audit, iso, json_write, read_bars, timestamp
from .engine import metrics, run_suite
from .ledger import Ledger, code_hash, utc_now
from .stats import paired_block_bootstrap


def _canonical(value: dict) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def _runtime() -> dict:
    return {"python": platform.python_version(), "numpy": np.__version__}


def _input(settings: Settings, data: Path, end) -> Bars:
    bars = read_bars(data, interval=settings.interval)
    if bars.provenance.get("symbol", settings.symbol) != settings.symbol or bars.provenance.get("instrument", "spot") != "spot":
        raise ValueError("Dataset symbol/instrument does not match the experiment")
    # Truncate before any feature or policy evaluation; future input values are not used.
    bars = bars.take((bars.times >= timestamp(settings.dev_start)) & (bars.times < timestamp(end + timedelta(days=1))))
    if len(bars) < 2 or bars.times[0] != timestamp(settings.dev_start) or bars.times[-1] != timestamp(end + timedelta(days=1)) - settings.seconds * 1000:
        raise ValueError("Dataset must cover the full configured prehistory and phase end")
    return bars


def make_freeze(settings: Settings, data: Path, output: Path, ledger: Ledger, root: Path, *, minimum_improvement: float = .02) -> dict:
    if output.exists():
        raise ValueError("Freeze file already exists; use a new protocol version")
    if not np.isfinite(minimum_improvement) or minimum_improvement < 0:
        raise ValueError("Materiality threshold must be finite and nonnegative")
    bars = _input(settings, data, settings.selection_end)
    audit(bars, allow_gaps=True)
    prefix, code = bars.prefix_hash(settings.selection_end), code_hash(root)
    if not ledger.matching_selection(settings.sha256, code, prefix):
        raise ValueError("A successful matching selection-phase run is required before freezing")
    payload = {"schema_version": 1, "created_at": utc_now(), "config_sha256": settings.sha256, "code_sha256": code,
               "interval": settings.interval, "runtime": _runtime(), "selection_data_prefix_sha256": prefix, "selection_end": str(settings.selection_end),
               "minimum_annual_log_improvement": minimum_improvement,
               "claim": "retrospective adaptive-minus-fixed paired mean log return; bootstrap assumptions apply; no sequential market guarantee",
               "candidate_family": [list(x) for x in settings.pairs], "base_cost_bps": settings.base_cost,
               "disclosure": "audit control, not security or protection from human/model prior knowledge"}
    payload["freeze_sha256"] = hashlib.sha256(_canonical(payload)).hexdigest()
    identifier = ledger.start("freeze", {"output": str(output)}, config_hash=settings.sha256, code=code, data_hash=prefix)
    try:
        json_write(output, payload)
        ledger.finish(identifier, "completed", {"output": str(output), "freeze_sha256": payload["freeze_sha256"]})
    except Exception as error:
        ledger.finish(identifier, "failed", {"error": str(error)})
        raise
    return payload


def check_freeze(path: Path, settings: Settings, bars: Bars, code: str) -> dict:
    payload = json.loads(path.read_text(encoding="utf-8"))
    saved = payload.pop("freeze_sha256", None)
    if saved != hashlib.sha256(_canonical(payload)).hexdigest():
        raise ValueError("Freeze integrity check failed")
    expected = {"config_sha256": settings.sha256, "code_sha256": code, "interval": settings.interval, "runtime": _runtime(),
                "selection_data_prefix_sha256": bars.prefix_hash(settings.selection_end)}
    for field, value in expected.items():
        if payload.get(field) != value:
            raise ValueError(f"Freeze mismatch for {field}; changed protocols need a new selection run and freeze")
    return {**payload, "freeze_sha256": saved}


def _plots(path: Path, times: np.ndarray, equity: dict[str, np.ndarray]) -> None:
    # Keep matplotlib font/config writes inside the run directory.
    import os
    os.environ.setdefault("MPLCONFIGDIR", str((path / "plot-cache").resolve()))
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from datetime import datetime, timezone
    dates = [datetime.fromtimestamp(int(t) / 1000, timezone.utc) for t in times]
    fig, axes = plt.subplots(2, 1, figsize=(11, 7), sharex=True, layout="constrained")
    for name, nav in equity.items():
        axes[0].plot(dates, nav, label=name, linewidth=1.2)
        axes[1].plot(dates, nav / np.maximum.accumulate(np.r_[1., nav])[1:] - 1, linewidth=1.1)
    axes[0].set_yscale("log")
    axes[0].set_ylabel("Rebased NAV (log scale)")
    axes[1].set_ylabel("Drawdown")
    axes[0].legend(ncol=3, fontsize=8)
    axes[0].set_title("BTC spot research — assumed execution and costs")
    for ax in axes:
        ax.grid(alpha=.2)
    fig.savefig(path / "equity-drawdown.png", dpi=150)
    plt.close(fig)


def backtest(settings: Settings, data: Path, phase: str, output_root: Path, ledger: Ledger, root: Path, *, allow_gaps: bool = False,
             freeze: Path | None = None, acknowledge_reserved: bool = False, block_length: int = 180, draws: int = 1000, seed: int = 7, plots: bool = True) -> dict:
    code = code_hash(root)
    access_number = ledger.reserved_count() + 1 if phase == "reserved" else None
    identifier = ledger.start("backtest", {"data": str(data), "interval": settings.interval, "allow_gaps": allow_gaps,
                                           "seed": seed, "block_length": block_length, "draws": draws, "reserved_access_number": access_number,
                                           "command": sys.argv}, phase=phase, config_hash=settings.sha256, code=code)
    path = output_root / identifier
    try:
        for name, value, minimum in (("block_length", block_length, 2), ("draws", draws, 100), ("seed", seed, 0)):
            if type(value) is not int or value < minimum:
                raise ValueError(f"{name} must be an integer >= {minimum}")
        if phase == "reserved" and (freeze is None or not acknowledge_reserved):
            raise ValueError("Reserved evaluation requires --freeze and --acknowledge-retrospective")
        begin, end = settings.dates(phase)
        bars = _input(settings, data, end)
        quality = audit(bars, allow_gaps=allow_gaps)
        if quality["zero_volume_bars"]:
            raise ValueError("Zero-volume bars lack a defensible next-open execution price; quarantine and document them before running")
        prefix = bars.prefix_hash(settings.selection_end)
        # Update provenance before computation so failures remain auditable too.
        with ledger.connect() as db:
            db.execute("UPDATE attempts SET data_prefix_hash=? WHERE id=?", (prefix, identifier))
        frozen = check_freeze(freeze, settings, bars, code) if phase == "reserved" else None
        if path.exists():
            raise ValueError("Run directory already exists")
        path.mkdir(parents=True)
        costs = list(dict.fromkeys([settings.base_cost, *settings.costs]))
        scenarios, base_books, choices, f, first = {}, None, None, None, None
        equity, base_start, base_stop = {}, 0, 0
        for cost in costs:
            books, scenario_choices, feature_set, common_start = run_suite(bars, settings, cost, frozen_choices=choices)
            start, stop = max(common_start, int(np.searchsorted(bars.times, timestamp(begin)))), len(bars)
            if stop - start < 2:
                raise ValueError("Phase has fewer than two scored bars after required history")
            scenarios[str(cost)] = {name: metrics(book, bars, start, stop, settings.annualization, cost) for name, book in books.items()}
            if base_books is None:
                base_books, choices, f, first = books, scenario_choices, feature_set, common_start
                base_start, base_stop = start, stop
                equity = {name: book.nav[start:stop] / book.nav[start - 1] for name, book in books.items()}
        differences = base_books["adaptive"].log_returns[base_start:base_stop] - base_books["fixed"].log_returns[base_start:base_stop]
        regular = scenarios[str(settings.base_cost)]["fixed"]["regular_grid_statistics_available"]
        if not regular:
            inference = {"available": False, "reason": "Scored window includes missing intervals; compressed rows are not a regular time series"}
        elif len(differences) < block_length * 5:
            inference = {"available": False, "reason": "Fewer than five bootstrap blocks; interval not reported"}
        else:
            inference = {"available": True, **paired_block_bootstrap(differences, block_length=block_length, draws=draws, seed=seed, annualization=settings.annualization)}
        effective = json.loads(json.dumps(asdict(settings), default=str))
        metadata = {"run_id": identifier, "created_at": utc_now(), "phase": phase, "data_kind": bars.provenance.get("provider", "unverified local input"),
                    "config": effective, "code_sha256": code, "data_csv_sha256": bars.provenance["csv_sha256"],
                    "selection_data_prefix_sha256": prefix, "provenance": bars.provenance, "audit": quality,
                    "runtime": {**_runtime(), "platform": platform.platform()},
                    "score_start": iso(bars.times[base_start]), "score_end": iso(bars.close_times[base_stop - 1]),
                    "feature_pause_bars_in_scored_window": int(np.sum(~f.valid[base_start:base_stop])),
                    "selection_changes": sum(x["selected_pair"] != x["previous_pair"] for x in choices if base_start - 1 <= x["bar_index"] < base_stop),
                    "reserved_access_number": access_number, "freeze": frozen,
                    "cost_sensitivity": "base-cost selector choices frozen across all actual-cost scenarios; candidate search not reoptimized for stress costs",
                    "limitations": ["assumed next-open prices and all-in costs, not measured fills", "spot USDT quote/venue risk is not modeled", "continuous books inherit positions at phase boundaries", "retrospective data may contain revisions and prior knowledge", "bootstrap is approximate, unadjusted for research selection, and not a market e-process", "no new theorem, novelty, profitability or production readiness established"]}
        report = {"metadata": metadata, "scenarios": scenarios, "paired_adaptive_minus_fixed": inference}
        json_write(path / "report.json", report)
        json_write(path / "selections.json", choices)
        (path / "config.toml").write_bytes(settings.source.read_bytes())
        with (path / "equity.csv").open("w", newline="", encoding="utf-8") as file:
            writer = csv.writer(file, lineterminator="\n")
            writer.writerow(["open_time", "close_time", *equity])
            for j, i in enumerate(range(base_start, base_stop)):
                writer.writerow([iso(bars.times[i]), iso(bars.close_times[i]), *(float(nav[j]) for nav in equity.values())])
        with (path / "trades.csv").open("w", newline="", encoding="utf-8") as file:
            fields = ["strategy", "bar_index", "decision_time", "execution_time", "side", "price", "coins", "signed_notional", "assumed_cost", "cost_bps_per_side", "target_weight_after_cost"]
            writer = csv.DictWriter(file, fieldnames=fields, lineterminator="\n")
            writer.writeheader()
            for name, book in base_books.items():
                for trade in book.trades:
                    if base_start <= trade["bar_index"] < base_stop:
                        writer.writerow({"strategy": name, **trade})
        lines = [f"# BTC trend research: {phase}", "", f"Run `{identifier}`; data kind: **{metadata['data_kind']}**.", "",
                 f"Scored UTC: {metadata['score_start']} through {metadata['score_end']}.", "",
                 f"Assumed base cost: {settings.base_cost:g} bps per side. Historical execution and fees are not validated.", "",
                 "| Strategy | Return | CAGR | Max drawdown | Mean exposure | Trades |", "|---|---:|---:|---:|---:|---:|"]
        for name, result in scenarios[str(settings.base_cost)].items():
            cagr_text = f"{result['cagr']:.2%}" if result['cagr'] is not None else "unavailable"
            lines.append(f"| {name} | {result['total_return']:.2%} | {cagr_text} | {result['maximum_drawdown']:.2%} | {result['mean_exposure']:.2%} | {result['trade_count']} |")
        lines += ["", "## Paired uncertainty", "", "```json", json.dumps(inference, indent=2, allow_nan=False), "```", "", "## Limits", ""]
        lines += [f"- {item}" for item in metadata["limitations"]]
        if not regular:
            lines += ["- Missing intervals: regular-grid annualized moments and bootstrap inference are unavailable; elapsed-time CAGR remains descriptive."]
        if access_number is not None:
            lines += [f"- Reserved access number: {access_number}; this is retrospective evaluation, not fresh prospective confirmation."]
        lines += ["", "All cost scenarios and provenance are in report.json. No strategy was selected using this report automatically.", ""]
        (path / "report.md").write_text("\n".join(lines), encoding="utf-8")
        if plots:
            _plots(path, bars.close_times[base_start:base_stop], equity)
        ledger.finish(identifier, "completed", {"output": str(path.resolve()), "data_kind": metadata["data_kind"], "reserved_access_number": access_number})
        return {"run_id": identifier, "output": str(path.resolve()), "phase": phase, "base_cost_bps": settings.base_cost,
                "fixed": scenarios[str(settings.base_cost)]["fixed"], "adaptive": scenarios[str(settings.base_cost)]["adaptive"], "paired": inference}
    except Exception as error:
        ledger.finish(identifier, "failed", {"error": str(error), "partial_output": str(path), "reserved_access_number": access_number})
        raise
