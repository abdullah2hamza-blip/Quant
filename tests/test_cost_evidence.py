"""Analytical checks of cost geometry, budgets, and information timing."""
import math

import numpy as np
import pytest

from quant.cost_evidence import CostEvidenceStream, CostInterval, bounded_cost_interval, counterexamples, log_mixture, paired_cost_proxies, test_level as level


def test_calibration_interval_matches_hoeffding_spending_formula():
    n, total, cap, delta = 200, 16., .2, .01
    result = bounded_cost_interval(total, n, cap, delta)
    error = 6 * delta / (math.pi ** 2 * n ** 2)
    radius = cap * math.sqrt(math.log(2 / error) / (2 * n))
    assert result.lower == pytest.approx(max(0, total / n - radius))
    assert result.upper == pytest.approx(min(cap, total / n + radius))
    assert sum(6 * delta / (math.pi ** 2 * i ** 2) for i in range(1, 10000)) < delta
    assert bounded_cost_interval(0, 0, cap, delta).upper == cap


@pytest.mark.parametrize("args", [(1, 0, .2, .01), (-1, 2, .2, .01), (1, 2, .2, .01), (0, -1, .2, .01), (0, True, .2, .01), (0, 2, 0, .01), (0, 2, .2, 0), (math.nan, 2, .2, .01)])
def test_calibration_rejects_invalid_inputs(args):
    with pytest.raises(ValueError):
        bounded_cost_interval(*args)


def test_joint_cost_geometry_and_exact_gain():
    interval = CostInterval(.03, .17, 100, .01)
    qa = np.array([0., .3, .8, 1., .2])
    qb = np.array([1., .8, .3, 1., .2])
    gross = np.array([.1, -.2, .3, .1, 0.])
    p = paired_cost_proxies(gross, qa, qb, interval, .01)
    np.testing.assert_allclose(p["joint"] - p["separate"], np.minimum(qa, qb) * (.17 - .03), atol=1e-16)
    for theta in np.linspace(interval.lower, interval.upper, 25):
        latent = gross - (qa - qb) * theta - .01
        assert np.all(p["joint"] <= latent + 1e-15)
        assert np.all(p["separate"] <= p["joint"] + 1e-15)
    assert p["joint"][-1] == pytest.approx(-.01)


def test_symmetric_upper_is_optimistic_when_reference_trades_more():
    p = paired_cost_proxies(-.1, 0, 1, CostInterval(0, .2, 0, .01))
    assert float(p["symmetric_upper"]) == pytest.approx(.1)
    assert float(p["joint"]) == pytest.approx(-.1)


def test_plugin_estimate_is_frozen_before_outcome_arrives():
    stream = CostEvidenceStream(.01, proxy="plugin")
    stream.issue(0, 4, 1., 0., CostInterval(0., .2, 0, .01), estimate=.03)
    result = stream.observe(.1, 4)
    assert result["raw_utility_proxy"] == pytest.approx(.07)


@pytest.mark.parametrize("turnover", [-1, math.nan, math.inf])
def test_cost_geometry_rejects_invalid_turnover(turnover):
    with pytest.raises(ValueError):
        paired_cost_proxies(.1, turnover, 0., CostInterval(0, .2, 0, .01))


def test_fixed_family_and_adaptive_birth_budgets():
    assert sum(level(.05, .01, j, family_size=10) for j in range(1, 11)) == pytest.approx(.04)
    spent = sum(level(.05, .01, j) for j in range(1, 1000))
    assert 0 < spent < .04
    with pytest.raises(ValueError):
        level(.05, .01, 11, family_size=10)
    with pytest.raises(ValueError):
        level(.05, .05, 1)


def test_stream_freezes_cost_information_at_issue_and_waits_for_maturity():
    stream = CostEvidenceStream(.01)
    envelope = CostInterval(.02, .1, 30, .01, available_at=4)
    with pytest.raises(ValueError, match="timing"):
        stream.issue(3, 5, .5, .2, envelope)
    stream.issue(4, 8, .5, .2, envelope)
    with pytest.raises(ValueError, match="Overlapping"):
        stream.issue(5, 9, .5, .2, envelope)
    with pytest.raises(ValueError, match="matured"):
        stream.observe(.2, 7)
    result = stream.observe(.2, 8)
    assert result["raw_utility_proxy"] == pytest.approx(.17)
    expected = math.log(np.mean(1 + stream.grid * .17))
    assert result["log_evidence"] == pytest.approx(expected)
    with pytest.raises(ValueError, match="matured"):
        stream.observe(.2, 8)
    with pytest.raises(ValueError, match="timing"):
        stream.issue(7, 9, .5, .2, envelope)


@pytest.mark.parametrize("mode", ["linear", "hoeffding"])
def test_common_fixed_mixture_is_pathwise_monotone_in_cost_lower_proxy(mode):
    joint = CostEvidenceStream(.01, mode=mode, proxy="joint")
    separate = CostEvidenceStream(.01, mode=mode, proxy="separate")
    envelope = CostInterval(.02, .14, 50, .01)
    for t, gross in enumerate(np.random.default_rng(8).uniform(-.5, .5, 100)):
        for s in (joint, separate):
            s.issue(t, t + 1, .8, .6, envelope)
        j, b = joint.observe(float(gross), t + 1), separate.observe(float(gross), t + 1)
        assert j["log_evidence"] >= b["log_evidence"] - 1e-13


def test_hoeffding_update_and_known_latent_bound_proxy_projection():
    stream = CostEvidenceStream(.01, mode="hoeffding")
    stream.issue(0, 1, 100, 0, CostInterval(0, .2, 0, .01))
    result = stream.observe(.1, 1)
    assert result["normalized_proxy"] == -1
    expected = log_mixture(-stream.grid - stream.grid ** 2 / 2)
    assert result["log_evidence"] == pytest.approx(expected)


def test_numerically_stable_mixture_and_crossing_history():
    assert log_mixture(np.array([1000., 999.])) == pytest.approx(1000 + math.log((1 + math.exp(-1)) / 2))
    stream = CostEvidenceStream(.05, birth_time=5)
    envelope = CostInterval(0, 0, 0, .01)
    with pytest.raises(ValueError, match="timing"):
        stream.issue(0, 1, 0, 0, envelope)
    events = []
    for t in range(5, 35):
        stream.issue(t, t + 1, 0, 0, envelope)
        events.append(stream.observe(.5, t + 1))
    assert events[-1]["first_crossing_time"] is not None
    assert events[-1]["first_crossing_time"] == next(x["observed_at"] for x in events if x["crossed"])


def test_fixed_configuration_cannot_be_changed_through_public_api():
    original = np.array([.1, .5])
    stream = CostEvidenceStream(.05, grid=original)
    original[0] = .9
    assert stream.grid[0] == .1
    with pytest.raises(ValueError):
        stream.grid[0] = .3
    for field, value in [("grid", np.array([.2])), ("mode", "hoeffding"), ("proxy", "plugin"), ("alpha", .5), ("bound", 10.), ("birth_time", 10)]:
        with pytest.raises(AttributeError):
            setattr(stream, field, value)


@pytest.mark.parametrize("proxy", ["plugin", "symmetric_upper"])
def test_invalid_comparators_do_not_emit_validity_claims(proxy):
    stream = CostEvidenceStream(.05, proxy=proxy)
    stream.issue(0, 1, 0., 1., CostInterval(0., .2, 0, .01))
    result = stream.observe(-.1, 1)
    assert result["guarantee"].startswith("none:")


def test_counterexamples_state_actual_failure_and_boundaries():
    result = counterexamples()
    hidden = result["observable_filtration_only"]
    assert sum(a * b for a, b in zip(hidden["latent_values"], hidden["probabilities"])) == pytest.approx(0.)
    assert hidden["observed_crossing_probability"] > hidden["nominal_alpha_plus_delta"]
    assert result["pointwise_envelopes"]["probability_of_any_independent_envelope_failure"] > .999
    assert result["pointwise_envelopes"]["exact_false_rejection_probability_by_horizon"] > .5
    assert result["peeked_delayed_outcomes"]["expected_one_step_factor"] > 1
    assert result["reused_prescreen"]["false_rejection_probability_lower_bound"] > .99
