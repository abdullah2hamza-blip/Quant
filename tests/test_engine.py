from dataclasses import replace

import numpy as np
import pytest

from quant.data import Bars
from quant.engine import Book, features, metrics, run_suite, select_pairs, simulate, trade_to_weight
from tests.factories import sample_bars, small_settings


@pytest.mark.parametrize("target", [0., .01, .2, .75, 1.])
@pytest.mark.parametrize("initial", [(1., 0.), (.4, .006)])
def test_self_financing_target_with_fees(target, initial):
    cash, coins = initial
    price, rate = 100., .01
    before = cash + coins * price
    after_cash, after_coins, notional, cost = trade_to_weight(cash, coins, price, target, rate)
    after = after_cash + after_coins * price
    assert after == pytest.approx(before - rate * abs(notional))
    assert after_coins * price / after == pytest.approx(target)
    assert after_cash >= 0 and after_coins >= 0
    assert cost == pytest.approx(rate * abs(notional))


def test_full_exit_then_tiny_target_reenters():
    cash, coins, _, _ = trade_to_weight(24.40965107221529, .3636272074070572, 62514.06427154871, 0., .0025)
    assert coins == 0.
    assert trade_to_weight(cash, coins, 62514.06427154871, .01, .0025)[1] > 0


def test_signal_only_fills_at_next_open_and_cost_is_on_notional():
    s = small_settings()
    bars = sample_bars(4)
    targets = np.array([np.nan, 1., 0., np.nan])
    book = simulate(bars, targets, s, 100., "test")
    assert [t["bar_index"] for t in book.trades] == [2, 3]
    price = bars.values[2, 0]
    assert book.trades[0]["price"] == price
    assert book.trades[0]["signed_notional"] == pytest.approx(1 / 1.01)
    assert book.trades[0]["assumed_cost"] == pytest.approx(.01 / 1.01)
    assert book.cash.min() >= 0 and book.coins.min() >= 0
    assert book.coins[-1] == 0


def test_features_and_selector_do_not_read_future_prices():
    s, original = small_settings(), sample_bars()
    changed_values = original.values.copy()
    changed_values[270:, :4] *= 50
    changed = Bars(original.times, changed_values, original.close_times, original.interval, {})
    a, choices_a, fa, first = run_suite(original, s, 25)
    b, choices_b, fb, other = run_suite(changed, s, 25)
    assert first == other == s.min_history
    for pair in s.pairs:
        np.testing.assert_allclose(fa.targets[pair][:270], fb.targets[pair][:270], equal_nan=True)
    np.testing.assert_allclose(a["adaptive"].nav[:270], b["adaptive"].nav[:270])
    np.testing.assert_allclose(a["ensemble"].nav[:270], b["ensemble"].nav[:270])
    assert [x for x in choices_a if x["bar_index"] < 270] == [x for x in choices_b if x["bar_index"] < 270]


def test_selector_scores_continuous_shadow_returns_and_keeps_ties():
    s, bars = small_settings(), sample_bars()
    f = features(bars, s)
    shadows = {p: simulate(bars, target, s, 25, str(p)) for p, target in f.targets.items()}
    _, choices = select_pairs(bars, s, f, shadows)
    first = choices[0]
    t = first["bar_index"]
    assert t == s.min_history - 1
    for pair, book in shadows.items():
        assert first["scores"][f"{pair[0]}/{pair[1]}"] == pytest.approx(np.log(book.nav[t] / book.nav[t - s.trailing]) / s.trailing)
    tied_shadows = {p: shadows[s.initial_pair] for p in s.pairs}
    _, tied = select_pairs(bars, s, f, tied_shadows)
    assert all(tuple(x["selected_pair"]) == s.initial_pair for x in tied)


def test_cost_sensitivity_keeps_base_cost_selection_schedule():
    s, bars = small_settings(), sample_bars()
    _, choices, _, _ = run_suite(bars, s, 25)
    _, stressed_choices, _, _ = run_suite(bars, s, 100, frozen_choices=choices)
    assert stressed_choices == choices


def test_gap_cancels_order_carries_holdings_and_resets_features():
    s, bars = small_settings(), sample_bars(360)
    mask = np.arange(360) != 210
    gapped = bars.take(mask)
    f = features(gapped, s)
    gap_index = 210
    assert not f.valid[gap_index:gap_index + s.warmup - 1].any()
    assert not f.selector_valid[gap_index:].any()
    target = np.ones(len(gapped))
    target[209] = 0.
    book = simulate(gapped, target, s, 25, "test")
    assert gap_index not in [x["bar_index"] for x in book.trades]
    assert book.coins[gap_index] == book.coins[gap_index - 1]
    stats = metrics(book, gapped, 180, len(gapped), 2190, 25)
    assert not stats["regular_grid_statistics_available"]
    assert stats["annualized_volatility"] is None
    assert stats["descriptive_sharpe"] is None


def test_zero_volatility_yields_no_invented_risk_target():
    bars = sample_bars()
    prices = bars.values.copy()
    prices[:, :4] = 100.
    flat = Bars(bars.times, prices, bars.close_times, bars.interval, {})
    f = features(flat, small_settings())
    assert not f.valid.any()
    with pytest.raises(ValueError, match="Insufficient"):
        run_suite(flat, small_settings(), 25)


def test_benchmarks_have_matching_feature_inception():
    s, bars = small_settings(), sample_bars()
    books, _, _, _ = run_suite(bars, s, 25)
    first_btc_trade = books["buy_hold"].trades[0]["bar_index"]
    first_risk_trade = books["volatility_target"].trades[0]["bar_index"]
    assert first_btc_trade == first_risk_trade == s.warmup


def test_terminal_holdings_are_marked_and_exit_adjustment_is_separate():
    s, bars = small_settings(), sample_bars()
    book = simulate(bars, np.ones(len(bars)), s, 100, "test")
    stats = metrics(book, bars, 180, len(bars), 2190, 100)
    assert stats["estimated_exit_adjusted_return"] < stats["total_return"]
    assert book.coins[-1] > 0


def test_short_window_cagr_is_unavailable_instead_of_overflow():
    bars = sample_bars(3)
    nav = np.array([1., 2., 4.])
    book = Book("x", nav, nav, np.zeros(3), np.zeros(3), np.zeros(3), np.zeros(3), [])
    result = metrics(book, bars, 1, 3, 2190, 25)
    assert result["cagr"] is None
    assert result["total_return"] == 3


def test_cagr_includes_gap_before_first_scored_observation():
    bars = sample_bars(240).take(np.r_[0, np.arange(120, 240)])
    nav = np.linspace(1., 1.1, len(bars))
    zero = np.zeros(len(bars))
    book = Book("x", nav, nav, zero, zero, zero, zero, [])
    result = metrics(book, bars, 1, len(bars), 2190, 25)
    elapsed_years = (bars.close_times[-1] - bars.close_times[0]) / (365 * 86400 * 1000)
    assert result["cagr"] == pytest.approx(1.1 ** (1 / elapsed_years) - 1)
    assert not result["regular_grid_statistics_available"]
