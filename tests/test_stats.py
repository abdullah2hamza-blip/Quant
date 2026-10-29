import itertools
import json
import math

import numpy as np
import pytest

from quant.stats import _predictable_bet, paired_block_bootstrap, simulate_evidence


def test_block_bootstrap_constant_difference_and_linear_annualization():
    result = paired_block_bootstrap(np.full(100, 0.002), block_length=10, draws=100)
    assert result["mean_difference"] == pytest.approx(0.002)
    assert result["mean_difference_ci"] == pytest.approx([0.002, 0.002])
    assert result["annualized_mean_difference"] == pytest.approx(4.38)
    assert result["effective_block_count"] == 10
    assert "not CAGR" in " ".join(result["caveats"])
    json.dumps(result, allow_nan=False)


def test_bootstrap_reproducibility_and_translation_equivariance():
    values = np.sin(np.arange(120) / 11) * 0.01
    first = paired_block_bootstrap(values, block_length=12, draws=100, seed=9)
    second = paired_block_bootstrap(values, block_length=12, draws=100, seed=9)
    shifted = paired_block_bootstrap(values + 0.03, block_length=12, draws=100, seed=9)
    assert first == second
    assert shifted["mean_difference_ci"] == pytest.approx(
        np.asarray(first["mean_difference_ci"]) + 0.03
    )
    assert shifted["annualized_mean_difference"] == pytest.approx(
        first["annualized_mean_difference"] + 0.03 * 2190
    )


@pytest.mark.parametrize(
    "values,kwargs",
    [
        ([], {}),
        ([0.01] * 49, {"block_length": 10}),
        ([0.01] * 100, {"block_length": 1}),
        ([0.01] * 100, {"block_length": True}),
        ([0.01] * 100, {"block_length": 10, "draws": 10}),
        ([0.01] * 100, {"block_length": 10, "annualization": float("inf")}),
        ([0.01] * 100, {"block_length": 10, "confidence": 1.0}),
        ([[0.01, 0.02]] * 100, {"block_length": 10}),
        ([float("nan")] * 100, {"block_length": 10}),
    ],
)
def test_bootstrap_rejects_unsupported_inputs_instead_of_iid_fallback(values, kwargs):
    with pytest.raises(ValueError):
        paired_block_bootstrap(values, **kwargs)


def test_predictable_betting_has_unit_expectation_on_symmetric_null_paths():
    # Enumerate the entire finite null law, rather than relying on Monte Carlo
    # to "prove" a probabilistic bound. Each conditional outcome is +/-0.7.
    terminal_evidence = []
    crossing = []
    alpha = 0.25
    for signs in itertools.product([-1.0, 1.0], repeat=8):
        previous_sum = np.array(0.0)
        previous_squares = np.array(0.0)
        evidence = 1.0
        ever_crossed = False
        for sign in signs:
            stake = float(_predictable_bet(previous_sum, previous_squares))
            increment = sign * 0.7
            assert 0 <= stake <= 1
            evidence *= 1 + stake * increment
            ever_crossed |= evidence >= 1 / alpha
            previous_sum += increment
            previous_squares += increment * increment
        terminal_evidence.append(evidence)
        crossing.append(ever_crossed)
    assert np.mean(terminal_evidence) == pytest.approx(1.0)
    assert np.mean(crossing) <= alpha


def test_predictable_bet_is_bounded_for_adverse_and_favorable_histories():
    stakes = _predictable_bet(np.array([-100.0, 0.0, 100.0]), np.array([1.0, 0.0, 1.0]))
    assert stakes == pytest.approx([0.0, 0.1, 1.0])


@pytest.fixture(scope="module")
def evidence_result():
    return simulate_evidence(worlds=300, steps=150, hypotheses=4, seed=21)


def test_simulation_is_reproducible_and_serializable(evidence_result):
    assert evidence_result == simulate_evidence(worlds=300, steps=150, hypotheses=4, seed=21)
    json.dumps(evidence_result, allow_nan=False)
    assert evidence_result["per_hypothesis_bonferroni_alpha"] == 0.05 / 4


def test_simulation_threshold_adjustments_and_cost_bound_construction(evidence_result):
    for state in ["null", "alternative"]:
        methods = evidence_result[state]
        adjusted = methods["anytime_e_bonferroni"]["family_rejection_rate"]["estimate"]
        unadjusted = methods["anytime_e_unadjusted"]["family_rejection_rate"]["estimate"]
        assert adjusted <= unadjusted
        assert methods["naive_repeated_z_bonferroni"]["family_rejection_rate"]["estimate"] <= (
            methods["naive_repeated_z_unadjusted"]["family_rejection_rate"]["estimate"]
        )
        # Cost subtraction changes the adaptive bet too, so it is not generally
        # pathwise-monotone in rejection. Do not assert that invalid shortcut.
    assert evidence_result["cost_stress"]["true_cost_range"][1] <= (
        evidence_result["cost_stress"]["deterministic_conservative_cost_upper_bound"]
    )


def test_simulation_mc_intervals_use_worlds_and_disclose_guarantee_limits(evidence_result):
    rate = evidence_result["null"]["anytime_e_bonferroni"]["family_rejection_rate"]
    assert rate["independent_worlds"] == 300
    assert "Wilson" in rate["interval_method"]
    assert rate["confidence_interval"][0] <= rate["estimate"] <= rate["confidence_interval"][1]
    assert 0 <= rate["standard_error"] <= 0.5 / math.sqrt(299)
    assert "not a novelty claim" in " ".join(evidence_result["caveats"])
    assert "delayed-feedback" in " ".join(evidence_result["caveats"])
    assert "invalid_optimistic_cost_proxy" in evidence_result["null"]


@pytest.mark.parametrize(
    "kwargs",
    [
        {"worlds": 10},
        {"steps": 5},
        {"hypotheses": 0},
        {"worlds": True},
        {"alpha": 0.0},
        {"alpha": float("nan")},
        {"seed": -1},
    ],
)
def test_simulation_rejects_invalid_parameters(kwargs):
    with pytest.raises(ValueError):
        simulate_evidence(**kwargs)
