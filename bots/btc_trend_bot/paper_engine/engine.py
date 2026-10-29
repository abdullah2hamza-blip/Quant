"""Causal features and a self-financing, long/cash spot research simulator."""
from __future__ import annotations

from dataclasses import dataclass
import math

import numpy as np

from .config import Settings
from .data import Bars, iso


@dataclass
class Features:
    targets: dict[tuple[int, int], np.ndarray]
    valid: np.ndarray
    selector_valid: np.ndarray
    risk_weight: np.ndarray


@dataclass
class Book:
    name: str
    nav: np.ndarray
    cash: np.ndarray
    coins: np.ndarray
    weights: np.ndarray
    costs: np.ndarray
    turnover: np.ndarray
    trades: list[dict]

    @property
    def log_returns(self) -> np.ndarray:
        return np.diff(np.log(self.nav), prepend=np.log(self.nav[0]))


def trade_to_weight(cash: float, coins: float, price: float, target: float, fee: float) -> tuple[float, float, float, float]:
    """Target post-fee NAV weight; buy and sell sides solve different equations."""
    if not all(math.isfinite(x) for x in (cash, coins, price, target, fee)) or cash < -1e-12 or coins < -1e-12 or price <= 0 or not 0 <= target <= 1 or not 0 <= fee < 1:
        raise ValueError("Invalid spot trade inputs")
    nav, holding = cash + coins * price, coins * price
    if nav <= 0:
        raise ValueError("Insolvent portfolio")
    difference = target * nav - holding
    sign = 1 if difference >= 0 else -1
    notional = difference / (1 + sign * fee * target)
    cost = fee * abs(notional)
    cash_after, coins_after = cash - notional - cost, coins + notional / price
    if target == 0:
        coins_after = 0.
    elif target == 1:
        cash_after = 0.
    tolerance = 1e-10 * max(nav, 1)
    if cash_after < -tolerance or coins_after < -tolerance:
        raise ValueError("Trade would borrow cash or coins")
    return max(0., cash_after), max(0., coins_after), notional, cost


def features(bars: Bars, settings: Settings) -> Features:
    n = len(bars)
    close = bars.values[:, 3]
    boundaries = np.r_[0, np.flatnonzero(np.diff(bars.times) != settings.seconds * 1000) + 1, n]
    emas = {span: np.full(n, np.nan) for span in {x for pair in settings.pairs for x in pair}}
    volatility = np.full(n, np.nan)
    warmed = np.zeros(n, dtype=bool)
    for begin, end in zip(boundaries[:-1], boundaries[1:], strict=True):
        for span, ema in emas.items():
            alpha = 2. / (span + 1)
            ema[begin] = close[begin]
            for i in range(begin + 1, end):
                ema[i] = alpha * close[i] + (1 - alpha) * ema[i - 1]
        returns = np.diff(np.log(close[begin:end]))
        window = settings.vol_window
        if len(returns) >= window:
            # Center before cumulative sums to reduce cancellation in the variance.
            center = returns[0]
            shifted = returns - center
            sums = np.r_[0., np.cumsum(shifted)]
            squares = np.r_[0., np.cumsum(shifted ** 2)]
            total = sums[window:] - sums[:-window]
            second = squares[window:] - squares[:-window]
            variance = np.maximum((second - total ** 2 / window) / (window - 1), 0.)
            volatility[begin + window:end] = np.sqrt(variance * settings.annualization)
        warmed[begin + settings.warmup - 1:end] = True
    valid = warmed & np.isfinite(volatility) & (volatility > 1e-12)
    risk = np.full(n, np.nan)
    risk[valid] = np.minimum(settings.max_weight, settings.vol_target / volatility[valid])
    targets = {pair: np.where(valid, np.where(emas[pair[0]] > emas[pair[1]], risk, 0.), np.nan) for pair in settings.pairs}
    # At close t, the selector scores returns t-L+1 ... t. A return at i
    # requires a valid decision at close i-1 and no missing interval before i.
    bad_return = np.ones(n, dtype=np.int64)
    bad_return[1:] = ~(valid[:-1] & (np.diff(bars.times) == settings.seconds * 1000))
    cumulative = np.r_[0, np.cumsum(bad_return)]
    selector_valid = np.zeros(n, dtype=bool)
    for i in range(settings.min_history - 1, n):
        selector_valid[i] = cumulative[i + 1] == cumulative[i + 1 - settings.trailing]
    return Features(targets, valid, selector_valid, risk)


def simulate(bars: Bars, targets: np.ndarray, settings: Settings, cost_bps: float, name: str, *, resize_interval: int = 1) -> Book:
    n = len(bars)
    if len(targets) != n or not math.isfinite(cost_bps) or not 0 <= cost_bps < 10000:
        raise ValueError("Invalid target sequence or costs")
    nav = np.empty(n)
    cash_series, coin_series, weights, costs, turnover = (np.zeros(n) for _ in range(5))
    cash, coins, last_resize = settings.initial_equity, 0., -resize_interval
    trades = []
    for i in range(n):
        opening, closing = bars.values[i, 0], bars.values[i, 3]
        before = cash + coins * opening
        # No order may cross an unobserved gap; existing spot holdings are carried.
        can_act = i > 0 and bars.times[i] - bars.times[i - 1] == settings.seconds * 1000 and np.isfinite(targets[i - 1])
        if can_act:
            target = float(targets[i - 1])
            current = coins * opening / before
            transition = (target == 0 and coins > 0) or (target > 0 and coins == 0)
            resize = abs(target - current) >= settings.band and i - last_resize >= resize_interval
            if transition or resize:
                cash, coins, notional, cost = trade_to_weight(cash, coins, opening, target, cost_bps / 10000)
                if abs(notional) > 1e-14 * before:
                    costs[i], turnover[i] = cost, abs(notional) / before
                    last_resize = i
                    trades.append({"bar_index": i, "decision_time": iso(bars.close_times[i - 1]), "execution_time": iso(bars.times[i]),
                                   "side": "buy" if notional > 0 else "sell", "price": float(opening), "coins": float(abs(notional) / opening),
                                   "signed_notional": float(notional), "assumed_cost": float(cost), "cost_bps_per_side": cost_bps, "target_weight_after_cost": target})
        nav[i] = cash + coins * closing
        if not math.isfinite(nav[i]) or nav[i] <= 0:
            raise ValueError("Portfolio NAV became non-positive or non-finite")
        cash_series[i], coin_series[i] = cash, coins
        weights[i] = coins * closing / nav[i]
    return Book(name, nav, cash_series, coin_series, weights, costs, turnover, trades)


def select_pairs(bars: Bars, settings: Settings, f: Features, shadows: dict[tuple[int, int], Book]) -> tuple[np.ndarray, list[dict]]:
    selected, next_selection = settings.initial_pair, settings.min_history - 1
    targets = np.full(len(bars), np.nan)
    logs = {pair: np.log(book.nav) for pair, book in shadows.items()}
    selections = []
    for i in range(len(bars)):
        if i >= next_selection and f.selector_valid[i]:
            scores = {pair: float((value[i] - value[i - settings.trailing]) / settings.trailing) for pair, value in logs.items()}
            maximum = max(scores.values())
            tied = [pair for pair, score in scores.items() if math.isclose(score, maximum, rel_tol=0, abs_tol=1e-14)]
            previous = selected
            selected = selected if selected in tied else ((settings.fast, settings.slow) if (settings.fast, settings.slow) in tied else tied[0])
            selections.append({"decision_time": iso(bars.close_times[i]), "available_through": iso(bars.close_times[i]),
                               "score_start": iso(bars.times[i - settings.trailing + 1]), "selected_pair": list(selected), "previous_pair": list(previous),
                               "scores": {f"{p[0]}/{p[1]}": s for p, s in scores.items()}, "bar_index": i})
            next_selection = i + settings.selection_interval
        targets[i] = f.targets[selected][i]
    return targets, selections


def run_suite(bars: Bars, settings: Settings, cost_bps: float, *, frozen_choices: list[dict] | None = None) -> tuple[dict[str, Book], list[dict], Features, int]:
    f = features(bars, settings)
    eligible = np.flatnonzero(f.selector_valid)
    if len(eligible) == 0 or eligible[0] + 1 >= len(bars):
        raise ValueError("Insufficient contiguous, nonzero-volatility warm-up and selector history before scored trades")
    first = int(eligible[0] + 1)
    shadows = {pair: simulate(bars, target, settings, cost_bps, f"shadow_{pair[0]}_{pair[1]}") for pair, target in f.targets.items()}
    adaptive_target, choices = select_pairs(bars, settings, f, shadows)
    if frozen_choices is not None:
        choices = frozen_choices
        selected = settings.initial_pair
        by_index = {x["bar_index"]: tuple(x["selected_pair"]) for x in choices}
        for i in range(len(bars)):
            selected = by_index.get(i, selected)
            adaptive_target[i] = f.targets[selected][i]
    buy_hold = np.full(len(bars), np.nan)
    buy_hold[int(np.flatnonzero(f.valid)[0]):] = 1.
    books = {"fixed": shadows[(settings.fast, settings.slow)],
             "adaptive": simulate(bars, adaptive_target, settings, cost_bps, "adaptive"),
             "ensemble": simulate(bars, np.mean(np.stack(list(f.targets.values())), axis=0), settings, cost_bps, "ensemble"),
             "cash": simulate(bars, np.zeros(len(bars)), settings, cost_bps, "cash"),
             "buy_hold": simulate(bars, buy_hold, settings, cost_bps, "buy_hold"),
             "volatility_target": simulate(bars, f.risk_weight, settings, cost_bps, "volatility_target"),
             "slow_resize": simulate(bars, f.targets[(settings.fast, settings.slow)], settings, cost_bps, "slow_resize", resize_interval=settings.selection_interval)}
    return books, choices, f, first


def metrics(book: Book, bars: Bars, start: int, stop: int, annualization: int, cost_bps: float) -> dict:
    if not 1 <= start < stop <= len(bars):
        raise ValueError("Scored window needs at least one prior NAV and one scored return")
    values = np.r_[book.nav[start - 1], book.nav[start:stop]]
    returns = values[1:] / values[:-1] - 1
    logs = np.log(values[1:] / values[:-1])
    # Initial wealth is valued at the previous observed close. Include any
    # missing interval between that valuation and the first scored candle.
    years = (int(bars.close_times[stop - 1]) - int(bars.close_times[start - 1])) / (365 * 86400 * 1000)
    exponent = math.log(values[-1] / values[0]) / years
    cagr = math.expm1(exponent) if years >= 30 / 365 and abs(exponent) < 700 else None
    std = float(np.std(returns, ddof=1)) if len(returns) > 1 else 0.
    regular_grid = bool(np.all(np.diff(bars.times[start - 1:stop]) == (bars.close_times[0] - bars.times[0] + 1)))
    peak = np.maximum.accumulate(values)
    ending_holding = book.coins[stop - 1] * bars.values[stop - 1, 3]
    ending_liquidation = book.nav[stop - 1] - ending_holding * cost_bps / 10000
    return {"bars": len(returns), "start": iso(bars.times[start]), "end": iso(bars.close_times[stop - 1]),
            "total_return": float(values[-1] / values[0] - 1), "cagr": cagr,
            "cagr_caveat": "unavailable below 30 days or for numerical overflow; otherwise elapsed-calendar-time annualization",
            "mean_log_return": float(np.mean(logs)), "annualized_mean_log_return": float(np.mean(logs) * annualization) if regular_grid else None,
            "annualized_volatility": std * math.sqrt(annualization) if regular_grid else None, "descriptive_sharpe": float(np.mean(returns) / std * math.sqrt(annualization)) if regular_grid and std > 0 else None,
            "regular_grid_statistics_available": regular_grid,
            "maximum_drawdown": float(np.min(values / peak - 1)), "time_in_market": float(np.mean(book.weights[start:stop] > 1e-10)),
            "mean_exposure": float(np.mean(book.weights[start:stop])), "turnover": float(np.sum(book.turnover[start:stop])),
            "trade_count": sum(start <= t["bar_index"] < stop for t in book.trades),
            "costs_in_start_nav_units": float(np.sum(book.costs[start:stop]) / values[0]),
            "ending_exposure": float(book.weights[stop - 1]), "estimated_exit_adjusted_return": float(ending_liquidation / values[0] - 1),
            "scoring_convention": "continuous strategy; inherited holdings; returns rebased at prior close; terminal holdings marked, not force-filled",
            "sharpe_caveat": "descriptive annualization; no IID or selection-adjusted inference"}
