"""Paired-cost evidence primitives with explicit timing and guarantee limits.

These implement established betting, Hoeffding and robust-counterpart tools.
An observed proxy product is NOT automatically an e-process when its cost
envelope has only high-probability simultaneous coverage. The safety argument
uses latent domination plus a separate coverage-failure budget. See the
publication protocol and independent mathematical review.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
from numbers import Integral, Real

import numpy as np


def _number(name: str, value: float) -> float:
    if isinstance(value, (bool, np.bool_)) or not isinstance(value, Real) or not math.isfinite(value):
        raise ValueError(f"{name} must be a finite number")
    return float(value)


def _count(name: str, value: int, minimum: int = 0) -> int:
    if isinstance(value, (bool, np.bool_)) or not isinstance(value, Integral) or value < minimum:
        raise ValueError(f"{name} must be an integer >= {minimum}")
    return int(value)


@dataclass(frozen=True)
class CostInterval:
    lower: float
    upper: float
    observations: int
    delta: float
    available_at: int = 0

    def __post_init__(self):
        lower, upper = _number("lower", self.lower), _number("upper", self.upper)
        delta = _number("delta", self.delta)
        if not 0 <= lower <= upper or not 0 < delta < 1:
            raise ValueError("Need 0 <= lower <= upper and 0 < delta < 1")
        _count("observations", self.observations)
        _count("available_at", self.available_at)


def bounded_cost_interval(total: float, observations: int, support_upper: float,
                          delta: float, *, available_at: int = 0) -> CostInterval:
    """Conservative confidence sequence via Hoeffding and n^-2 error spending.

    Each calibration observation must be in [0,support_upper] and have the SAME
    fixed conditional mean theta given the complete preceding game information.
    This is an interval for that mean coefficient, not a prediction interval for
    individual future slippage. The caller must validate per-observation support;
    an aggregate sum alone cannot establish that assumption.
    """
    n = _count("observations", observations)
    cap = _number("support_upper", support_upper)
    error = _number("delta", delta)
    total = _number("total", total)
    if cap <= 0 or not 0 < error < 1 or not 0 <= total <= n * cap:
        raise ValueError("Invalid support, error budget, or calibration sum")
    if n == 0:
        return CostInterval(0., cap, 0, error, available_at)
    # log(2/delta_n) with delta_n=6*delta/(pi^2*n^2).
    radius = cap * math.sqrt((math.log(math.pi ** 2 / (3 * error)) + 2 * math.log(n)) / (2 * n))
    mean = total / n
    return CostInterval(max(0., mean - radius), min(cap, mean + radius), n, error, available_at)


def paired_cost_proxies(gross, candidate_turnover, reference_turnover,
                        interval: CostInterval, materiality: float = 0., *, estimate: float | None = None) -> dict[str, np.ndarray]:
    """Unnormalized utility proxies for a COMMON unknown mean-cost coefficient.

    Joint and separate lower proxies are valid on the shared coverage event.
    Plugin and symmetric_upper are deliberately unguaranteed comparators.
    Inputs may broadcast. This function does not establish the common-cost model.
    """
    gross, qa, qb = np.broadcast_arrays(np.asarray(gross, dtype=float),
                                       np.asarray(candidate_turnover, dtype=float),
                                       np.asarray(reference_turnover, dtype=float))
    margin = _number("materiality", materiality)
    if not all(np.isfinite(x).all() for x in (gross, qa, qb)) or np.any(qa < 0) or np.any(qb < 0) or margin < 0:
        raise ValueError("Need finite utility, nonnegative turnover and materiality")
    if estimate is not None:
        center = _number("estimate", estimate)
        if center < 0:
            raise ValueError("Cost estimate must be nonnegative")
    else:
        center = (interval.lower + interval.upper) / 2
    difference = qa - qb
    return {
        "joint": gross - np.maximum(difference * interval.lower, difference * interval.upper) - margin,
        "separate": gross - qa * interval.upper + qb * interval.lower - margin,
        "plugin": gross - difference * center - margin,
        "symmetric_upper": gross - difference * interval.upper - margin,
    }


def test_level(alpha_family: float, delta_cost: float, birth_index: int,
               *, family_size: int | None = None) -> float:
    """Utility-test alpha after ONE global cost-envelope failure allocation.

    Adaptive births spend (alpha-delta)/(j*(j+1)). Fixed families spend uniformly.
    Birth choices must be predictable and the null valid conditionally at birth.
    """
    alpha, delta = _number("alpha_family", alpha_family), _number("delta_cost", delta_cost)
    j = _count("birth_index", birth_index, 1)
    if not 0 <= delta < alpha < 1:
        raise ValueError("Need 0 <= delta_cost < alpha_family < 1")
    if family_size is None:
        return (alpha - delta) / (j * (j + 1))
    h = _count("family_size", family_size, 1)
    if j > h:
        raise ValueError("Birth index exceeds the fixed family")
    return (alpha - delta) / h


def log_mixture(log_components: np.ndarray) -> float:
    values = np.asarray(log_components, dtype=float)
    if values.ndim != 1 or len(values) == 0 or not np.isfinite(values).all():
        raise ValueError("Need a finite nonempty component vector")
    largest = float(values.max())
    return largest + math.log(float(np.mean(np.exp(values - largest))))


@dataclass(frozen=True)
class IssuedTrial:
    issue_time: int
    maturity_time: int
    candidate_turnover: float
    reference_turnover: float
    interval: CostInterval
    materiality: float
    estimate: float | None


class CostEvidenceStream:
    """One candidate, non-overlapping labels, fixed equal-weight betting mixture.

    Both FIXED-mixture modes support a nonpositive cumulative conditional mean
    at every prefix, via appropriate latent domination; the strong conditional
    null is a subset. The linear fixed-mixture extension uses a multiplicative
    conditional-mean compensator, not an adaptive-bet argument. Both require a known latent
    |D|<=bound in an appropriate oracle filtration. This timing API cannot verify
    that a caller has not inspected an outcome elsewhere.
    """

    def __init__(self, alpha: float, *, bound: float = 1., grid=(.05, .1, .2, .4, .8),
                 mode: str = "linear", proxy: str = "joint", birth_time: int = 0):
        self._alpha, self._bound = _number("alpha", alpha), _number("bound", bound)
        self._grid = np.array(grid, dtype=float, copy=True)
        if not 0 < self.alpha < 1 or self.bound <= 0:
            raise ValueError("Need 0 < alpha < 1 and a positive bound")
        if self.grid.ndim != 1 or len(self.grid) == 0 or not np.isfinite(self.grid).all() or np.any((self.grid <= 0) | (self.grid >= 1)):
            raise ValueError("Fixed betting grid must be a nonempty vector in (0,1)")
        if len(np.unique(self.grid)) != len(self.grid) or mode not in ("linear", "hoeffding") or proxy not in ("joint", "separate", "plugin", "symmetric_upper"):
            raise ValueError("Invalid grid, mode or proxy")
        self._grid.flags.writeable = False
        self._mode, self._proxy = mode, proxy
        self._birth_time = _count("birth_time", birth_time)
        self.last_observation_time = self.birth_time
        self.pending: IssuedTrial | None = None
        self.log_components = np.zeros(len(self.grid))
        self.observations = 0
        self.first_crossing_time: int | None = None

    @property
    def alpha(self):
        return self._alpha

    @property
    def bound(self):
        return self._bound

    @property
    def grid(self):
        view = self._grid.view()
        view.flags.writeable = False
        return view

    @property
    def mode(self):
        return self._mode

    @property
    def proxy(self):
        return self._proxy

    @property
    def birth_time(self):
        return self._birth_time

    def issue(self, issue_time: int, maturity_time: int, candidate_turnover: float,
              reference_turnover: float, interval: CostInterval, *, materiality: float = 0.,
              estimate: float | None = None) -> IssuedTrial:
        issue = _count("issue_time", issue_time)
        maturity = _count("maturity_time", maturity_time)
        qa, qb = _number("candidate_turnover", candidate_turnover), _number("reference_turnover", reference_turnover)
        margin = _number("materiality", materiality)
        if self.pending is not None:
            raise ValueError("Overlapping trials are outside this stream's guarantee")
        if issue < self.last_observation_time or maturity <= issue or interval.available_at > issue:
            raise ValueError("Trial or cost envelope violates information timing")
        if min(qa, qb, margin) < 0:
            raise ValueError("Turnover and materiality must be nonnegative")
        if estimate is not None and _number("estimate", estimate) < 0:
            raise ValueError("Cost estimate must be nonnegative")
        self.pending = IssuedTrial(issue, maturity, qa, qb, interval, margin, estimate)
        return self.pending

    def observe(self, gross: float, observed_at: int) -> dict:
        now, gross = _count("observed_at", observed_at), _number("gross", gross)
        trial = self.pending
        if trial is None or now < trial.maturity_time:
            raise ValueError("No matured trial is available")
        raw = float(paired_cost_proxies(gross, trial.candidate_turnover, trial.reference_turnover,
                                        trial.interval, trial.materiality, estimate=trial.estimate)[self.proxy])
        # The proof requires a known bound on latent D, not on the observed proxy.
        normalized = float(np.clip(raw / self.bound, -1., 1.))
        if self.mode == "linear":
            update = np.log1p(self.grid * normalized)
        else:
            update = self.grid * normalized - self.grid ** 2 / 2
        self.log_components += update
        self.observations += 1
        wealth = log_mixture(self.log_components)
        crossed = wealth >= -math.log(self.alpha)
        if crossed and self.first_crossing_time is None:
            self.first_crossing_time = now
        self.last_observation_time, self.pending = now, None
        return {"issue_time": trial.issue_time, "maturity_time": trial.maturity_time,
                "observed_at": now, "observations": self.observations,
                "mode": self.mode, "proxy": self.proxy, "raw_utility_proxy": raw,
                "normalized_proxy": normalized, "log_evidence": wealth,
                "log_threshold": -math.log(self.alpha), "crossed": crossed,
                "first_crossing_time": self.first_crossing_time,
                "guarantee": ("latent-wealth domination plus separate simultaneous-envelope error; observed proxy need not be an e-process"
                              if self.proxy in ("joint", "separate") else
                              "none: deliberately unguaranteed cost comparator; lower-proxy domination is not established")}


def counterexamples() -> dict:
    """Exact, deterministic diagnostics; no Monte Carlo or financial data."""
    delta, stake, alpha = .05, .5, .05
    positive = delta / (1 - delta)
    crossing = math.ceil(math.log(1 / alpha) / math.log1p(stake * positive))
    interval = CostInterval(0., .2, 0, .01)
    proxies = paired_cost_proxies(-.1, 0., 1., interval)
    pointwise_failure, steps = .01, 800
    pointwise_stake = .8
    failures_needed = math.ceil(math.log(1 / alpha) / math.log1p(pointwise_stake))
    failure_rejection = 1 - sum(math.comb(steps, k) * pointwise_failure ** k * (1 - pointwise_failure) ** (steps - k) for k in range(failures_needed))
    searched = 10
    reused_positive = 1 - 2. ** -searched
    reused_steps = math.ceil(math.log(1 / alpha) / math.log1p(pointwise_stake))
    return {
        "observable_filtration_only": {
            "latent_values": [positive, -1.], "probabilities": [1 - delta, delta],
            "observable_conditional_mean": 0., "constant_observed_lower_proxy": positive,
            "simultaneous_domination_probability": 1 - delta,
            "observed_crossing_probability": 1., "crossing_after_steps": crossing,
            "nominal_alpha_plus_delta": alpha + delta,
            "failure": "Past latent utilities reveal the persistent hidden state; an observable-filtration null is insufficient for latent-wealth domination."},
        "symmetric_upper_cost": {
            "gross_difference": -.1, "true_theta": .1, "candidate_turnover": 0., "reference_turnover": 1.,
            "latent_net_difference": 0., "valid_joint_proxy": float(proxies["joint"]),
            "invalid_symmetric_upper_proxy": float(proxies["symmetric_upper"]),
            "failure": "An upper cost for the benchmark is optimistic for candidate-minus-benchmark utility."},
        "pointwise_envelopes": {
            "pointwise_coverage": 1 - pointwise_failure, "steps": steps,
            "probability_of_any_independent_envelope_failure": -math.expm1(steps * math.log1p(-pointwise_failure)),
            "latent_utility": 0., "observed_proxy": "one on an independent envelope failure, zero otherwise",
            "stake": pointwise_stake, "alpha": alpha, "failures_required_for_rejection": failures_needed,
            "exact_false_rejection_probability_by_horizon": failure_rejection,
            "failure": "Pointwise coverage cannot be charged once as simultaneous coverage."},
        "peeked_delayed_outcomes": {
            "null_increment_values": [-.5, .5], "probabilities": [.5, .5],
            "invalid_stake_rule": "stake .5 after seeing a positive increment, zero after seeing a negative increment",
            "expected_one_step_factor": 1.125,
            "failure": "A bet chosen using the unmatured/current outcome is not predictable."},
        "reused_prescreen": {
            "independent_null_labels_per_search": searched,
            "original_label_mean": 0., "selected_max_label_mean": 1 - 2. ** (1 - searched),
            "stake": pointwise_stake, "expected_invalid_one_step_factor": 1 + pointwise_stake * (1 - 2. ** (1 - searched)),
            "searches": reused_steps, "alpha": alpha,
            "false_rejection_probability_lower_bound": reused_positive ** reused_steps,
            "failure": "Select the maximum after observing each batch of null labels, then reuse that selected label as fresh evidence. On all-positive-selected batches the wealth crosses the stated threshold."},
    }
