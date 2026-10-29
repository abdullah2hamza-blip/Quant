"""Paper-aligned strategy and replay interface. Broker execution lives separately."""
from __future__ import annotations

from dataclasses import asdict, replace
from datetime import date, datetime, timedelta, timezone
import csv
import hashlib
import json
import math
from pathlib import Path
import platform

import numpy as np

from paper_engine.config import Settings, load_settings
from paper_engine.data import Bars, audit, digest, iso, json_write, read_bars, timestamp
from paper_engine.engine import features, metrics, run_suite, simulate
from paper_engine.stats import paired_block_bootstrap

HOME = Path(__file__).resolve().parent
POLICIES = ("fixed", "adaptive", "ensemble", "cash", "buy_hold", "volatility_target", "slow_resize")


def settings(interval: str = "4h", cash: float = 1.0) -> Settings:
    if isinstance(cash, bool) or not math.isfinite(cash) or cash <= 0:
        raise ValueError("Starting cash must be finite and positive")
    return replace(load_settings(HOME / "config/paper.toml").at_interval(interval), initial_equity=float(cash))


def source_fingerprint() -> str:
    """Fingerprint active bot sources/configuration, excluding state and output."""
    h = hashlib.sha256()
    files = [*HOME.glob("*.py"), *HOME.glob("paper_engine/*.py"), *HOME.glob("research/*.py"), *HOME.glob("tests/*.py"),
             *HOME.glob("config/*"), HOME / "requirements.txt", HOME / "paper-origin.json",
             HOME / "pyproject.toml", HOME / "uv.lock"]
    for p in sorted(files):
        if p.is_file():
            h.update(p.relative_to(HOME).as_posix().encode() + b"\0" + p.read_bytes())
    return h.hexdigest()


def verify_paper_core() -> dict:
    origin = json.loads((HOME / "paper-origin.json").read_text())
    for name, expected in origin["paper_modules"].items():
        if digest(HOME / name) != expected:
            raise ValueError("Reviewed paper module changed: " + name)
    if digest(HOME / "config/paper.toml") != origin["paper_config_sha256"]:
        raise ValueError("Paper configuration changed; this is a new protocol")
    return {"verified_modules": len(origin["paper_modules"]), "paper_pdf_sha256": origin["paper_pdf_sha256"],
            "source_fingerprint": source_fingerprint(), "python": platform.python_version(), "numpy": np.__version__}


def load_csv(path: Path, s: Settings, *, as_of_ms: int | None = None) -> Bars:
    """Normalize legacy CSVs without filling, sorting or discarding bad rows."""
    with path.open(newline="", encoding="utf-8-sig") as f:
        header = next(csv.reader(f), [])
    if header and header[0] == "open_time_ms":
        bars = read_bars(path, interval=s.interval)
    else:
        with path.open(newline="", encoding="utf-8-sig") as f:
            rows = list(csv.DictReader(f))
        if not rows or not {"timestamp", "open", "high", "low", "close", "volume"}.issubset(header):
            raise ValueError("Need normalized paper CSV or timestamp/open/high/low/close/volume CSV")
        times = []
        for row in rows:
            value = row["timestamp"]
            try:
                numeric = int(value)
            except ValueError:
                dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
                if dt.tzinfo is None:
                    raise ValueError("ISO timestamps must include their UTC offset")
                opened = int(dt.timestamp() * 1000)
            else:
                if numeric <= 0:
                    raise ValueError("Invalid epoch timestamp")
                if numeric < 100_000_000_000:
                    opened = numeric * 1000
                elif numeric < 100_000_000_000_000:
                    opened = numeric
                else:
                    if numeric % 1000:
                        raise ValueError("Microsecond timestamp cannot be normalized exactly")
                    opened = numeric // 1000
            times.append(opened)
        opened = np.asarray(times, dtype=np.int64)
        values = np.asarray([[float(row[k]) for k in ("open", "high", "low", "close", "volume")] for row in rows])
        bars = Bars(opened, values, opened + s.seconds * 1000 - 1, s.interval,
                    {"provider": "user CSV; point-in-time provenance unverified", "symbol": s.symbol,
                     "instrument": "spot", "csv_sha256": digest(path), "local_path": str(path.resolve())})
    quality = audit(bars, allow_gaps=True, as_of_ms=as_of_ms)
    if quality["zero_volume_bars"]:
        raise ValueError("Zero-volume bars are not observable executable candles; audit/quarantine upstream")
    return bars


def signal(bars: Bars, s: Settings, policy: str = "fixed") -> dict:
    """Target based solely on the last completed candle and prior shadow books."""
    if policy == "legacy_daily":
        from legacy_daily import signal as legacy_signal
        return legacy_signal(bars, s)
    if policy not in ("fixed", "adaptive", "ensemble"):
        raise ValueError("Execution policy must be fixed, adaptive or ensemble")
    audit(bars, allow_gaps=True)
    f = features(bars, s)
    if not f.valid[-1]:
        return {"ready": False, "target": None, "reason": "insufficient continuous feature warm-up or invalid volatility"}
    selected, decisions = (s.fast, s.slow), []
    if policy == "adaptive":
        # Full continuous prehistory is retained. Rolling API windows must not
        # reset EMA initial conditions, selector cadence or the shadow books.
        from paper_engine.engine import select_pairs
        shadows = {p: simulate(bars, target, s, s.base_cost, str(p)) for p, target in f.targets.items()}
        targets, decisions = select_pairs(bars, s, f, shadows)
        if decisions:
            selected = tuple(decisions[-1]["selected_pair"])
        value = targets[-1]
    elif policy == "ensemble":
        value = np.mean([target[-1] for target in f.targets.values()])
    else:
        value = f.targets[selected][-1]
    return {"ready": True, "target": float(value), "policy": policy, "selected_pair": list(selected),
            "decision_time_ms": int(bars.close_times[-1]), "earliest_execution_ms": int(bars.close_times[-1]) + 1,
            "selector_history_ready": bool(f.selector_valid[-1]), "selection_count": len(decisions),
            "risk_weight": float(f.risk_weight[-1])}


def should_trade(target: float, current: float, coins: float, band: float) -> bool:
    if not all(math.isfinite(v) for v in (target, current, coins, band)) or not 0 <= target <= 1 or coins < 0:
        raise ValueError("Invalid target, holdings or band")
    # Entry and complete exit bypass the resizing band, matching the paper.
    return (target == 0 and coins > 0) or (target > 0 and coins == 0) or abs(target - current) >= band


def paired(a, b, bars: Bars, start: int, stop: int, s: Settings, *, draws: int, seed: int) -> dict:
    differences = a.log_returns[start:stop] - b.log_returns[start:stop]
    regular = bool(np.all(np.diff(bars.times[start - 1:stop]) == s.seconds * 1000))
    intervals = {}
    for days in (30, 15, 60):
        block = days * 86400 // s.seconds
        if regular and len(differences) >= 5 * block:
            intervals[str(days)] = {"available": True, **paired_block_bootstrap(differences, block_length=block,
                draws=draws, seed=seed, annualization=s.annualization, confidence=.95)}
        else:
            intervals[str(days)] = {"available": False, "reason": "Missing intervals or fewer than five physical-duration bootstrap blocks", "block_length": block}
    primary = intervals["30"]
    mean = float(differences.mean() * s.annualization) if regular else None
    return {"annualized_mean_log_difference": mean, "cumulative_log_difference": float(differences.sum()),
            "materiality_annual_log": .02, "bootstrap_by_block_days": intervals,
            "realized_paths_numerically_identical": bool(np.max(np.abs(differences)) <= 1e-12),
            "inference_status": "Approximate retrospective, unadjusted dependent-data intervals; no anytime guarantee",
            "future_profitability_established": False,
            "primary_lower_exceeds_materiality": bool(primary.get("available") and primary["annualized_mean_difference_ci"][0] > .02)}


def backtest(bars: Bars, s: Settings, start: date, end: date, *, draws: int = 5000,
             seed: int = 20261022, case_id: str = "binance_primary_4h") -> tuple[dict, dict, list]:
    if start >= end or draws < 100:
        raise ValueError("Need ordered dates and at least100 bootstrap draws")
    stop_time = timestamp(end + timedelta(days=1))
    bars = bars.take((bars.times >= timestamp(s.dev_start)) & (bars.times < stop_time))
    quality = audit(bars, allow_gaps=True)
    if quality["zero_volume_bars"] or bars.times[0] != timestamp(s.dev_start) or bars.times[-1] != stop_time - s.seconds * 1000:
        raise ValueError("Need positive-volume data, full original prehistory and the requested final candle")
    begin = int(np.searchsorted(bars.times, timestamp(start)))
    if not 1 <= begin < len(bars) - 1 or bars.times[begin] != timestamp(start):
        raise ValueError("Requested evaluation start is absent; do not silently shift the window")
    f = features(bars, s)
    if not f.selector_valid[begin - 1]:
        raise ValueError("Requested start lacks the paper's continuous warm-up and selector history")
    stop = len(bars)
    choices = None
    scenarios, arrays, base_trades = {}, {"open_time_ms": bars.times[begin:stop], "close_time_ms": bars.close_times[begin:stop]}, {}
    paired_seed = seed + int(hashlib.sha256(case_id.encode()).hexdigest()[:8], 16)
    for cost in (s.base_cost, 0., 10., 50., 100.):
        books, decisions, _, _ = run_suite(bars, s, cost, frozen_choices=choices)
        for pair, target in f.targets.items():
            if pair != (s.fast, s.slow):
                name = f"candidate_{pair[0]}_{pair[1]}"
                books[name] = simulate(bars, target, s, cost, name)
        if choices is None:
            choices = decisions
            base_trades = {name: [t for t in book.trades if begin <= t["bar_index"] < stop] for name, book in books.items()}
        results = {"metrics": {}, "initial_state": {}}
        for name, book in books.items():
            results["metrics"][name] = metrics(book, bars, begin, stop, s.annualization, cost)
            results["initial_state"][name] = {"nav": float(book.nav[begin - 1]), "cash": float(book.cash[begin - 1]),
                "coins": float(book.coins[begin - 1]), "valuation_time": iso(bars.close_times[begin - 1])}
            for field in ("nav", "cash", "coins", "weights", "costs", "turnover"):
                arrays[f"cost{cost:g}__{name}__{field}"] = getattr(book, field)[begin:stop]
        results["adaptive_minus_fixed"] = paired(books["adaptive"], books["fixed"], bars, begin, stop, s, draws=draws, seed=paired_seed)
        scenarios[f"{cost:g}"] = results
    report = {"schema_version": 3, "settings": json.loads(json.dumps(asdict(s), default=str)),
        "data": bars.provenance, "audit": quality, "source": verify_paper_core(), "case_id": case_id,
        "score_start": iso(bars.times[begin]), "score_end": iso(bars.close_times[-1]), "scored_bars": stop - begin,
        "scenarios": scenarios, "policy_choices_frozen_at_cost_bps": s.base_cost,
        "selection_changes_in_window": sum(begin <= x["bar_index"] < stop and x["selected_pair"] != x["previous_pair"] for x in choices),
        "interpretation": "Paper-aligned retrospective replay. No demonstrated adaptive edge; historical identity does not imply zero future uncertainty.",
        "execution_scope": "Modeled next-open fills at assumed traded-notional costs. Actual broker fills and capacity unvalidated."}
    return report, arrays, [base_trades, choices]


def save_backtest(output: Path, bars: Bars, s: Settings, start: date, end: date, *, evaluator=None, **kwargs) -> dict:
    output.mkdir(parents=True, exist_ok=False)
    attempt = {"status": "started", "started_at": datetime.now(timezone.utc).isoformat(), "source_fingerprint": source_fingerprint()}
    json_write(output / "attempt.json", attempt)
    try:
        report, arrays, (trades, choices) = (evaluator or backtest)(bars, s, start, end, **kwargs)
        json_write(output / "report.json", report)
        json_write(output / "trades.json", trades)
        json_write(output / "selections.json", choices)
        np.savez_compressed(output / "paths.npz", **arrays)
        if source_fingerprint() != attempt["source_fingerprint"]:
            raise ValueError("Bot source changed during the replay")
        files = {p.name: digest(p) for p in output.iterdir() if p.name != "attempt.json" and p.is_file()}
        json_write(output / "attempt.json", {**attempt, "status": "completed", "finished_at": datetime.now(timezone.utc).isoformat(), "outputs": files})
        return report
    except Exception as error:
        json_write(output / "attempt.json", {**attempt, "status": "failed", "error": str(error)})
        raise
