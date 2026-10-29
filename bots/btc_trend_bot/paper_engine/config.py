"""Validated, explicit research settings; no exchange execution interface."""
from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date
import hashlib
import math
from pathlib import Path
import tomllib

INTERVAL_SECONDS = {"1h": 3600, "4h": 14400, "1d": 86400}


@dataclass(frozen=True)
class Settings:
    source: Path
    sha256: str
    symbol: str
    interval: str
    fast: int
    slow: int
    warmup: int
    initial_equity: float
    vol_target: float
    vol_window: int
    annualization: int
    max_weight: float
    band: float
    base_cost: float
    costs: tuple[float, ...]
    pairs: tuple[tuple[int, int], ...]
    selection_interval: int
    trailing: int
    min_history: int
    initial_pair: tuple[int, int]
    dev_start: date
    dev_end: date
    selection_start: date
    selection_end: date
    reserved_start: date
    reserved_end: date

    @property
    def seconds(self) -> int:
        return INTERVAL_SECONDS[self.interval]

    def at_interval(self, interval: str) -> Settings:
        """Preserve clock durations, rounding fractional candles upward."""
        if interval not in INTERVAL_SECONDS:
            raise ValueError("Supported intervals are 1h, 4h, 1d")
        ratio = self.seconds / INTERVAL_SECONDS[interval]
        convert = lambda x: max(1, math.ceil(x * ratio))
        pairs = tuple((convert(f), convert(s)) for f, s in self.pairs)
        if any(f >= s for f, s in pairs):
            raise ValueError("Timeframe conversion collapsed a candidate EMA pair")
        warmup, trailing = convert(self.warmup), convert(self.trailing)
        return replace(self, interval=interval, fast=convert(self.fast), slow=convert(self.slow),
                       warmup=warmup, vol_window=max(2, convert(self.vol_window)),
                       annualization=365 * 86400 // INTERVAL_SECONDS[interval], pairs=pairs,
                       selection_interval=convert(self.selection_interval), trailing=trailing,
                       min_history=warmup + trailing,
                       initial_pair=(convert(self.initial_pair[0]), convert(self.initial_pair[1])))

    def dates(self, phase: str) -> tuple[date, date]:
        return {"development": (self.dev_start, self.dev_end),
                "selection": (self.selection_start, self.selection_end),
                "reserved": (self.reserved_start, self.reserved_end)}[phase]


def load_settings(path: str | Path) -> Settings:
    path = Path(path).resolve()
    payload = path.read_bytes()
    raw = tomllib.loads(payload.decode("utf-8"))
    allowed = {
        "market": {"data_venue", "symbol", "instrument", "timeframe", "timezone", "completed_candles_only"},
        "reference": {"signal", "fast_bars", "slow_bars", "position_mode", "warmup_bars", "initial_equity", "cash_rate_annual"},
        "risk": {"annual_volatility_target", "volatility_lookback_bars", "volatility_estimator", "annualization_bars", "maximum_exposure", "rebalance_weight_band"},
        "execution": {"fill_assumption", "cost_model", "base_cost_bps_per_side", "sensitivity_cost_bps_per_side", "charge_on"},
        "adaptive": {"candidate_ema_pairs", "selection_interval_bars", "trailing_selection_bars", "minimum_history_before_scoring_bars", "score", "initial_pair", "tie_break", "charge_portfolio_turnover_on_switch"},
        "evaluation": {"development_start", "development_end", "selection_start", "selection_end", "retrospective_evaluation_start", "retrospective_evaluation_end", "requires_shared_warmup_and_selection_history", "robustness_timeframes", "sequential_guarantee_status", "prospective_start"},
    }
    if set(raw) != set(allowed) | {"schema_version", "project", "mode"}:
        raise ValueError("Unknown or missing top-level config fields")
    if raw["schema_version"] != 1 or raw["mode"] != "research" or not isinstance(raw["project"], str):
        raise ValueError("Only schema_version=1, mode=research is supported")
    for section, keys in allowed.items():
        if set(raw[section]) != keys:
            raise ValueError(f"Unknown or missing {section} fields: {set(raw[section]) ^ keys}")
    expected = {"market.data_venue": "binance", "market.symbol": "BTCUSDT", "market.instrument": "spot",
                "market.timezone": "UTC", "market.completed_candles_only": True,
                "reference.signal": "ema_cross", "reference.position_mode": "long_flat", "reference.cash_rate_annual": 0.0,
                "risk.volatility_estimator": "sample_std_log_returns", "execution.fill_assumption": "next_bar_open",
                "execution.cost_model": "assumed_all_in_bps_per_side", "execution.charge_on": "traded_notional",
                "adaptive.score": "net_mean_log_return", "adaptive.tie_break": "retain_incumbent_then_reference",
                "adaptive.charge_portfolio_turnover_on_switch": True,
                "evaluation.requires_shared_warmup_and_selection_history": True,
                "evaluation.sequential_guarantee_status": "research_question_unproven",
                "evaluation.prospective_start": "after_protocol_freeze"}
    for dotted, value in expected.items():
        section, field = dotted.split(".")
        if raw[section][field] != value:
            raise ValueError(f"Unsupported {dotted}; expected {value!r}")
    m, r, k, e, a, v = (raw[x] for x in allowed)
    integer_fields = [(r, x) for x in ("fast_bars", "slow_bars", "warmup_bars")] + [(k, "volatility_lookback_bars"), (k, "annualization_bars")] + [(a, x) for x in ("selection_interval_bars", "trailing_selection_bars", "minimum_history_before_scoring_bars")]
    if any(type(obj[field]) is not int or obj[field] <= 0 for obj, field in integer_fields):
        raise ValueError("Bar counts must be positive integers")
    pairs = tuple(tuple(pair) for pair in a["candidate_ema_pairs"])
    if not pairs or any(len(p) != 2 or any(type(x) is not int or x <= 0 for x in p) or p[0] >= p[1] for p in pairs) or len(set(pairs)) != len(pairs):
        raise ValueError("EMA candidates must be distinct positive fast<slow pairs")
    initial = tuple(a["initial_pair"])
    if initial not in pairs or (r["fast_bars"], r["slow_bars"]) not in pairs:
        raise ValueError("Initial and reference pairs must be in candidate family")
    numeric = [r["initial_equity"], k["annual_volatility_target"], k["maximum_exposure"], k["rebalance_weight_band"], e["base_cost_bps_per_side"], *e["sensitivity_cost_bps_per_side"]]
    if any(isinstance(x, bool) or not isinstance(x, (int, float)) or not math.isfinite(x) for x in numeric):
        raise ValueError("Financial settings must be finite numbers")
    if not 0 < r["initial_equity"] or not 0 < k["annual_volatility_target"] or not 0 < k["maximum_exposure"] <= 1 or not 0 <= k["rebalance_weight_band"] <= 1:
        raise ValueError("Invalid initial equity, volatility, exposure, or rebalance band")
    if k["volatility_lookback_bars"] < 2 or r["warmup_bars"] < max(max(s for _, s in pairs), k["volatility_lookback_bars"] + 1):
        raise ValueError("Insufficient feature warm-up")
    if m["timeframe"] not in INTERVAL_SECONDS or k["annualization_bars"] != 365 * 86400 // INTERVAL_SECONDS[m["timeframe"]]:
        raise ValueError("Annualization must match the candle interval")
    if a["minimum_history_before_scoring_bars"] != r["warmup_bars"] + a["trailing_selection_bars"]:
        raise ValueError("Minimum history must equal warmup + selector window")
    costs = tuple(float(x) for x in e["sensitivity_cost_bps_per_side"])
    if not costs or len(set(costs)) != len(costs) or any(not 0 <= x < 10000 for x in (*costs, e["base_cost_bps_per_side"])):
        raise ValueError("Costs must be distinct scenarios in [0, 10000) bps per side")
    if v["robustness_timeframes"] != ["1h", "1d"]:
        raise ValueError("This protocol fixes 1h and 1d robustness checks")
    dates = [date.fromisoformat(v[x]) for x in ("development_start", "development_end", "selection_start", "selection_end", "retrospective_evaluation_start", "retrospective_evaluation_end")]
    if not dates[0] < dates[1] < dates[2] < dates[3] < dates[4] < dates[5]:
        raise ValueError("Evaluation windows must be ordered and disjoint")
    return Settings(path, hashlib.sha256(payload).hexdigest(), m["symbol"], m["timeframe"], r["fast_bars"], r["slow_bars"], r["warmup_bars"], float(r["initial_equity"]), float(k["annual_volatility_target"]), k["volatility_lookback_bars"], k["annualization_bars"], float(k["maximum_exposure"]), float(k["rebalance_weight_band"]), float(e["base_cost_bps_per_side"]), costs, pairs, a["selection_interval_bars"], a["trailing_selection_bars"], a["minimum_history_before_scoring_bars"], initial, *dates)
