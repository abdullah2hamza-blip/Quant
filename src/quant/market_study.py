"""Separately frozen retrospective market application; no market e-process claim."""
from __future__ import annotations

from dataclasses import asdict, replace
from datetime import date, timedelta
import hashlib
import json
import math
from pathlib import Path
import platform
import re
import time

import numpy as np

from .config import INTERVAL_SECONDS, Settings, load_settings
from .data import Bars, audit, digest, iso, json_write, read_bars, timestamp
from .engine import Book, features, metrics, run_suite, simulate
from .ledger import Ledger, code_hash, utc_now
from .publication import _seal, _snapshot_source
from .stats import paired_block_bootstrap


def _local(root: Path, name: str) -> Path:
    path = (root / name).resolve()
    if not path.is_relative_to(root.resolve()):
        raise ValueError("Study inputs must be inside the project")
    return path


def load_market_spec(path: Path) -> dict:
    spec = json.loads(path.read_text(encoding="utf-8"))
    required = {"schema_version", "study_id", "config", "materiality_annual_log", "base_cost_bps", "costs_bps", "bootstrap", "cases"}
    if set(spec) != required or spec["schema_version"] != 1 or not re.fullmatch(r"[a-z0-9_-]+", spec["study_id"]):
        raise ValueError("Unsupported market study schema")
    if not isinstance(spec["config"], str):
        raise ValueError("Need a configuration path")
    costs = spec["costs_bps"]
    if not isinstance(costs, list) or not costs or any(type(x) not in (int, float) or not math.isfinite(x) or not 0 <= x < 10000 for x in costs):
        raise ValueError("Invalid cost scenarios")
    if len(set(costs)) != len(costs) or type(spec["base_cost_bps"]) not in (int, float) or spec["base_cost_bps"] not in costs:
        raise ValueError("Base cost must occur once in the cost grid")
    materiality = spec["materiality_annual_log"]
    if type(materiality) not in (int, float) or not math.isfinite(materiality) or materiality < 0:
        raise ValueError("Invalid market materiality")
    bs = spec["bootstrap"]
    if set(bs) != {"draws", "block_days", "seed", "confidence"}:
        raise ValueError("Unsupported bootstrap settings")
    if type(bs["draws"]) is not int or bs["draws"] < 100 or type(bs["seed"]) is not int or bs["seed"] < 0:
        raise ValueError("Invalid bootstrap repetitions or seed")
    if not isinstance(bs["block_days"], list) or not bs["block_days"] or any(type(d) is not int or d <= 0 for d in bs["block_days"]) or len(set(bs["block_days"])) != len(bs["block_days"]):
        raise ValueError("Block days must be distinct positive integers")
    if type(bs["confidence"]) not in (int, float) or not 0 < bs["confidence"] < 1:
        raise ValueError("Invalid confidence level")
    fields = {"id", "data", "independent_audit", "interval", "symbol", "provider", "start", "end", "role"}
    if not isinstance(spec["cases"], list) or not spec["cases"]:
        raise ValueError("Need market cases")
    names = []
    for case in spec["cases"]:
        if set(case) != fields or any(not isinstance(v, str) for v in case.values()):
            raise ValueError("Unsupported market case fields")
        if not re.fullmatch(r"[a-z0-9_-]+", case["id"]) or case["interval"] not in INTERVAL_SECONDS or case["symbol"] not in ("BTCUSDT", "BTCUSD") or not case["provider"]:
            raise ValueError("Invalid market case identifier or instrument")
        if case["role"] not in ("primary", "timeframe_robustness", "venue_robustness") or date.fromisoformat(case["start"]) >= date.fromisoformat(case["end"]):
            raise ValueError("Invalid market case role or dates")
        if any(days * 86400 // INTERVAL_SECONDS[case["interval"]] < 2 for days in bs["block_days"]):
            raise ValueError("Each physical bootstrap block must contain at least two candles")
        names.append(case["id"])
    if len(set(names)) != len(names) or sum(c["role"] == "primary" for c in spec["cases"]) != 1:
        raise ValueError("Need distinct cases and exactly one primary comparison")
    return spec


def _runtime() -> dict:
    return {"python": platform.python_version(), "numpy": np.__version__}


def _settings(root: Path, spec: dict, case: dict) -> Settings:
    settings = load_settings(_local(root, spec["config"])).at_interval(case["interval"])
    if settings.base_cost != spec["base_cost_bps"]:
        raise ValueError("Market and original configuration base costs differ")
    # The venue/quote override is declared per case and recorded in full. The
    # original Binance configuration remains preserved, never silently relabeled.
    return replace(settings, symbol=case["symbol"])


def _case_input(root: Path, settings: Settings, case: dict) -> tuple[Bars, dict, int, int]:
    bars = read_bars(_local(root, case["data"]), interval=settings.interval)
    if any(bars.provenance.get(k) != v for k, v in (("symbol", case["symbol"]), ("provider", case["provider"]), ("instrument", "spot"))):
        raise ValueError("Market data identity differs from the specification")
    finish = timestamp(date.fromisoformat(case["end"]) + timedelta(days=1))
    bars = bars.take((bars.times >= timestamp(settings.dev_start)) & (bars.times < finish))
    quality = audit(bars, allow_gaps=True)
    if quality["zero_volume_bars"] or bars.times[0] != timestamp(settings.dev_start) or bars.times[-1] != finish - settings.seconds * 1000:
        raise ValueError("Need complete boundaries, positive volume and original prehistory")
    start = int(np.searchsorted(bars.times, timestamp(date.fromisoformat(case["start"]))))
    if not 1 <= start < len(bars) - 1 or bars.times[start] != timestamp(date.fromisoformat(case["start"])):
        raise ValueError("Requested score window is missing")
    return bars, quality, start, len(bars)


def _input_fingerprints(root: Path, spec: dict) -> list[dict]:
    records = {}
    for case in spec["cases"]:
        data, independent = _local(root, case["data"]), _local(root, case["independent_audit"])
        manifest = data.with_suffix(".manifest.json")
        checked = json.loads(independent.read_text(encoding="utf-8"))
        if checked.get("csv_sha256") != digest(data) or checked.get("manifest_sha256") != digest(manifest):
            raise ValueError("Independent audit does not match the data snapshot")
        for kind, path in (("csv", data), ("manifest", manifest), ("independent_audit", independent)):
            name = path.relative_to(root.resolve()).as_posix()
            records[name] = {"kind": kind, "path": name, "sha256": digest(path)}
    return [records[k] for k in sorted(records)]


def freeze_market(spec_path: Path, protocol: Path, review: Path, output: Path, ledger: Ledger, root: Path) -> dict:
    identifier = ledger.start("publication_market_freeze", {"spec": str(spec_path), "protocol": str(protocol), "review": str(review), "output": str(output)}, code=code_hash(root))
    try:
        if output.exists():
            raise ValueError("Market freeze already exists")
        spec = load_market_spec(spec_path)
        inputs = _input_fingerprints(root, spec)
        coverage = []
        for case in spec["cases"]:
            settings = _settings(root, spec, case)
            bars, quality, start, stop = _case_input(root, settings, case)
            f = features(bars, settings)  # Features only; no portfolio simulation.
            if not f.selector_valid[start - 1]:
                raise ValueError(f"{case['id']}: insufficient predeclared selector history at window start")
            coverage.append({"case_id": case["id"], "score_start": iso(bars.times[start]), "score_end": iso(bars.close_times[stop - 1]),
                             "scored_bars": stop - start, "history_gaps": quality["missing_bars"],
                             "score_regular_grid": bool(np.all(np.diff(bars.times[start - 1:stop]) == settings.seconds * 1000)),
                             "feature_pause_bars_in_score_window": int(np.sum(~f.valid[start:stop]))})
        docs = [protocol, review, *(_local(root, c["independent_audit"]) for c in spec["cases"])]
        documents = [{"path": p.resolve().relative_to(root.resolve()).as_posix(), "sha256": digest(p)} for p in sorted(set(docs))]
        snapshot = output.with_suffix(".sources.zip")
        source_hash = _snapshot_source(root, snapshot, docs)
        payload = {"kind": "publication_market_freeze", "created_at": utc_now(), "spec_sha256": digest(spec_path),
                   "code_sha256": code_hash(root), "config_sha256": digest(_local(root, spec["config"])), "runtime": _runtime(),
                   "inputs": inputs, "documents": documents, "coverage": coverage,
                   "source_snapshot": snapshot.name, "source_snapshot_sha256": source_hash,
                   "status": "retrospective; data acquisition and feature coverage inspected; no claim of prospective secrecy",
                   "gate": "Separate prespecified publication study; no matching hourly selection-phase backtest is claimed or required"}
        payload["freeze_sha256"] = _seal(payload)
        json_write(output, payload)
        ledger.finish(identifier, "completed", {"output": str(output), "sha256": digest(output)})
        return payload
    except Exception as error:
        ledger.finish(identifier, "failed", {"error": str(error)})
        raise


def check_market_freeze(freeze: Path, spec_path: Path, root: Path) -> dict:
    payload = json.loads(freeze.read_text(encoding="utf-8"))
    saved = payload.pop("freeze_sha256", None)
    if payload.get("kind") != "publication_market_freeze" or saved != _seal(payload):
        raise ValueError("Market freeze integrity check failed")
    spec = load_market_spec(spec_path)
    expected = {"code_sha256": code_hash(root), "spec_sha256": digest(spec_path), "runtime": _runtime(),
                "config_sha256": digest(_local(root, spec["config"])), "inputs": _input_fingerprints(root, spec)}
    for key, value in expected.items():
        if payload.get(key) != value:
            raise ValueError(f"Market freeze mismatch: {key}")
    for document in payload["documents"]:
        if digest(_local(root, document["path"])) != document["sha256"]:
            raise ValueError("Market protocol or review changed")
    snapshot = (freeze.parent / payload["source_snapshot"]).resolve()
    if snapshot.parent != freeze.parent.resolve() or digest(snapshot) != payload["source_snapshot_sha256"]:
        raise ValueError("Market source snapshot missing or changed")
    return {**payload, "freeze_sha256": saved}


def log_attribution(book: Book, bars: Bars, start: int, stop: int) -> tuple[dict, dict[str, np.ndarray]]:
    """Exact self-financing log identity; descriptive, not causal attribution."""
    before = book.cash[start - 1:stop - 1] + book.coins[start - 1:stop - 1] * bars.values[start:stop, 0]
    after = book.cash[start:stop] + book.coins[start:stop] * bars.values[start:stop, 0]
    previous, current = book.nav[start - 1:stop - 1], book.nav[start:stop]
    parts = {"between_candles": np.log(before / previous), "execution_cost": np.log(after / before),
             "within_candle_holdings": np.log(current / after)}
    actual = np.log(current / previous)
    residual = sum(parts.values()) - actual
    fee_residual = np.abs(before - after - book.costs[start:stop])
    if not np.allclose(residual, 0, atol=1e-12, rtol=0) or np.any(fee_residual > 1e-10 * np.maximum(1., before)):
        raise ValueError("Portfolio log attribution identity failed")
    return {**{k: float(v.sum()) for k, v in parts.items()}, "total_log_return": float(actual.sum()),
            "maximum_absolute_identity_residual": float(np.max(np.abs(residual))),
            "interpretation": "accounting identity; holdings differ across strategies and cost paths; not a causal decomposition"}, parts


def _paired(a: Book, b: Book, bars: Bars, start: int, stop: int, settings: Settings, spec: dict, seed: int) -> dict:
    differences = a.log_returns[start:stop] - b.log_returns[start:stop]
    regular = bool(np.all(np.diff(bars.times[start - 1:stop]) == settings.seconds * 1000))
    annualized = float(differences.mean() * settings.annualization) if regular else None
    intervals = {}
    for days in spec["bootstrap"]["block_days"]:
        block = days * 86400 // settings.seconds
        if not regular or len(differences) < 5 * block:
            intervals[str(days)] = {"available": False, "reason": "Missing intervals or fewer than five physical-duration bootstrap blocks", "block_length": block}
        else:
            intervals[str(days)] = {"available": True, **paired_block_bootstrap(differences, block_length=block,
                draws=spec["bootstrap"]["draws"], seed=seed, annualization=settings.annualization, confidence=spec["bootstrap"]["confidence"])}
    return {"cumulative_log_difference": float(differences.sum()), "annualized_mean_log_difference": annualized,
            "materiality_annual_log": spec["materiality_annual_log"], "point_estimate_exceeds_materiality": annualized > spec["materiality_annual_log"] if regular else None,
            "bootstrap_by_block_days": intervals, "inference_status": "approximate retrospective paired intervals; no sequential, multiplicity or selection-adjusted guarantee"}


def evaluate_market_case(spec: dict, case: dict, root: Path, path: Path) -> dict:
    settings = _settings(root, spec, case)
    bars, quality, start, stop = _case_input(root, settings, case)
    f = features(bars, settings)
    if not f.selector_valid[start - 1]:
        raise ValueError("Insufficient selector history at the requested score start")
    path.mkdir(parents=True, exist_ok=False)
    costs = [spec["base_cost_bps"], *(x for x in spec["costs_bps"] if x != spec["base_cost_bps"])]
    choices = None
    scenarios, arrays, base_books = {}, {"open_time_ms": bars.times[start:stop], "close_time_ms": bars.close_times[start:stop]}, None
    for cost in costs:
        books, scenario_choices, _, common_start = run_suite(bars, settings, cost, frozen_choices=choices)
        if common_start > start:
            raise ValueError("Requested window precedes valid common history")
        for pair, target in f.targets.items():
            if pair != (settings.fast, settings.slow):
                name = f"candidate_{pair[0]}_{pair[1]}"
                books[name] = simulate(bars, target, settings, cost, name)
        if choices is None:
            choices, base_books = scenario_choices, books
        cost_name = format(cost, "g")
        result = {"metrics": {}, "attribution": {}, "initial_state": {}}
        for name, book in books.items():
            result["metrics"][name] = metrics(book, bars, start, stop, settings.annualization, cost)
            attribution, parts = log_attribution(book, bars, start, stop)
            result["attribution"][name] = attribution
            result["initial_state"][name] = {"nav": float(book.nav[start - 1]), "cash": float(book.cash[start - 1]), "coins": float(book.coins[start - 1]), "valuation_time": iso(bars.close_times[start - 1])}
            for field in ("nav", "cash", "coins", "weights", "costs", "turnover"):
                arrays[f"cost{cost_name}__{name}__{field}"] = getattr(book, field)[start:stop]
            for field, values in parts.items():
                arrays[f"cost{cost_name}__{name}__log_{field}"] = values
        # Common random bootstrap indices across contrasts/costs in this case.
        seed = spec["bootstrap"]["seed"] + int(hashlib.sha256(case["id"].encode()).hexdigest()[:8], 16)
        result["adaptive_minus_fixed"] = _paired(books["adaptive"], books["fixed"], bars, start, stop, settings, spec, seed)
        scenarios[cost_name] = result
    assert base_books is not None and choices is not None
    controls = {name: _paired(base_books["adaptive"], book, bars, start, stop, settings, spec, seed)
                for name, book in base_books.items() if name not in ("adaptive", "fixed")}
    years = {}
    for year in range(date.fromisoformat(case["start"]).year, date.fromisoformat(case["end"]).year + 1):
        begin = max(start, int(np.searchsorted(bars.times, timestamp(date(year, 1, 1)))))
        end = min(stop, int(np.searchsorted(bars.times, timestamp(date(year + 1, 1, 1)))))
        if end - begin >= 2:
            years[str(year)] = {"start": iso(bars.times[begin]), "end": iso(bars.close_times[end - 1]), "adaptive_minus_fixed": _paired(base_books["adaptive"], base_books["fixed"], bars, begin, end, settings, spec, seed),
                                "metrics": {name: metrics(book, bars, begin, end, settings.annualization, spec["base_cost_bps"]) for name, book in base_books.items()}}
    cost_signs = [(float(c), r["adaptive_minus_fixed"]["cumulative_log_difference"]) for c, r in scenarios.items()]
    cost_signs.sort()
    brackets = [[a[0], b[0]] for a, b in zip(cost_signs[:-1], cost_signs[1:]) if a[1] * b[1] < 0]
    report = {"case": case, "created_at": utc_now(), "effective_settings": json.loads(json.dumps(asdict(settings), default=str)),
              "score_start": iso(bars.times[start]), "score_end": iso(bars.close_times[stop - 1]), "scored_bars": stop - start,
              "audit": quality, "provenance": bars.provenance, "runtime": _runtime(), "scenarios": scenarios,
              "base_cost_adaptive_minus_controls": controls, "base_cost_calendar_subperiods": years,
              "cost_break_even": {"sign_change_brackets_bps": brackets, "evaluated_costs_and_cumulative_log_difference": cost_signs,
                                  "limit": "Grid brackets only; full cost paths are nonlinear, differences need not be monotone, no unique interpolated break-even is asserted"},
              "selection_changes_in_window": sum(x["selected_pair"] != x["previous_pair"] for x in choices if start - 1 <= x["bar_index"] < stop - 1),
              "feature_pause_bars_in_window": int(np.sum(~f.valid[start:stop])),
              "selection_policy": "base-cost shadow-book choices frozen at all sensitivity costs; histories are continuous and inherited",
              "limitations": ["Retrospective prices and researcher prior knowledge; not prospective confirmation", "Paired bootstrap assumes sufficiently stable weak dependence and has no optional-stopping or research-selection guarantee",
                              "Costs are assumed all-in notional haircuts; no measured spread, latency, capacity or actual fills", "The nonlinear self-financing cost paths are not the bounded affine-cost synthetic model",
                              "Cross-venue Bitcoin observations are dependent; USD and USDT involve different quote risks", "No original bot code was available at the original protocol freeze; the later daily SMA bot is a separate exploratory extension"]}
    json_write(path / "report.json", report)
    json_write(path / "selections.json", choices)
    json_write(path / "base-cost-trades.json", {name: [t for t in book.trades if start <= t["bar_index"] < stop] for name, book in base_books.items()})
    np.savez_compressed(path / "paths.npz", **arrays)
    return report


def run_market(spec_path: Path, freeze: Path, output_root: Path, ledger: Ledger, root: Path, *, acknowledge_retrospective: bool = False, progress=print) -> dict:
    with ledger.connect() as db:
        access = db.execute("SELECT COUNT(*) FROM attempts WHERE kind='publication_market'").fetchone()[0] + 1
    identifier = ledger.start("publication_market", {"spec": str(spec_path), "freeze": str(freeze), "retrospective_access_number": access}, code=code_hash(root), phase="retrospective")
    path = output_root / identifier
    manifest = None
    try:
        if not acknowledge_retrospective:
            raise ValueError("Market study requires explicit retrospective acknowledgement")
        frozen = check_market_freeze(freeze, spec_path, root)
        spec = load_market_spec(spec_path)
        path.mkdir(parents=True, exist_ok=False)
        manifest = {"run_id": identifier, "created_at": utc_now(), "kind": "publication_market", "status": "running",
                    "retrospective_access_number": access, "spec": spec, "freeze": frozen, "cases": []}
        json_write(path / "manifest.json", manifest)
        for case in spec["cases"]:
            child = ledger.start("publication_market_case", {"parent_run": identifier, "case": case}, code=frozen["code_sha256"], phase="retrospective")
            begun = time.perf_counter()
            try:
                result = evaluate_market_case(spec, case, root, path / case["id"])
                files = {name: digest(path / case["id"] / name) for name in ("report.json", "selections.json", "base-cost-trades.json", "paths.npz")}
                record = {"case_id": case["id"], "elapsed_seconds": time.perf_counter() - begun, "sha256": files,
                          "scored_bars": result["scored_bars"]}
                manifest["cases"].append(record)
                json_write(path / "manifest.json", manifest)
                ledger.finish(child, "completed", record)
                progress(f"Completed market case {case['id']} ({record['elapsed_seconds']:.2f}s)")
            except Exception as error:
                ledger.finish(child, "failed", {"error": str(error), "partial_output": str(path / case["id"])})
                raise
        manifest["status"] = "completed"
        manifest["finished_at"] = utc_now()
        json_write(path / "manifest.json", manifest)
        ledger.finish(identifier, "completed", {"output": str(path.resolve()), "manifest_sha256": digest(path / "manifest.json"), "retrospective_access_number": access})
        return {"run_id": identifier, "output": str(path.resolve()), "cases": len(manifest["cases"]), "retrospective_access_number": access}
    except Exception as error:
        if manifest is not None:
            manifest["status"], manifest["error"] = "failed", str(error)
            json_write(path / "manifest.json", manifest)
        ledger.finish(identifier, "failed", {"error": str(error), "partial_output": str(path), "retrospective_access_number": access})
        raise
