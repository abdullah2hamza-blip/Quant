"""Dependence-aware diagnostics and controlled sequential-evidence experiments.

Backtest confidence intervals are descriptive, approximate time-series inference.
The sequential experiment has a known synthetic null; its validity does not
transfer to historical strategy returns without checking the stated assumptions.
"""

from __future__ import annotations

import math
from numbers import Integral, Real
from statistics import NormalDist
from typing import Any

import numpy as np
from numpy.typing import ArrayLike, NDArray


def _integer(name: str, value: int, minimum: int) -> int:
    if isinstance(value, (bool, np.bool_)) or not isinstance(value, Integral):
        raise ValueError(f"{name} must be an integer >= {minimum}")
    if value < minimum:
        raise ValueError(f"{name} must be an integer >= {minimum}")
    return int(value)


def _probability(name: str, value: float) -> float:
    if isinstance(value, (bool, np.bool_)) or not isinstance(value, Real):
        raise ValueError(f"{name} must be finite and strictly between zero and one")
    if not math.isfinite(value) or not 0.0 < value < 1.0:
        raise ValueError(f"{name} must be finite and strictly between zero and one")
    return float(value)


def paired_block_bootstrap(
    differences: ArrayLike,
    block_length: int = 180,
    draws: int = 1000,
    seed: int = 7,
    annualization: float = 2190,
    confidence: float = 0.95,
) -> dict[str, Any]:
    """Moving-block percentile interval for aligned per-bar differences.

    Callers supply *paired differences*, preferably net log-return differences
    over exactly the same completed intervals. Contiguous overlapping blocks
    preserve within-block dependence; the final sampled block is truncated to
    the original sample size. No circular wrap is introduced. At least five
    effective blocks are required, and IID fallback is deliberately unavailable.

    Annualization scales the mean difference linearly. It is not CAGR or a
    claimed expected annual simple return. There is no multiplicity adjustment,
    optional-stopping guarantee, or robustness to arbitrary regime changes.
    """
    block_length = _integer("block_length", block_length, 2)
    draws = _integer("draws", draws, 100)
    seed = _integer("seed", seed, 0)
    confidence = _probability("confidence", confidence)
    if (
        isinstance(annualization, (bool, np.bool_))
        or not isinstance(annualization, Real)
        or not math.isfinite(annualization)
        or annualization <= 0
    ):
        raise ValueError("annualization must be finite and positive")
    try:
        values = np.asarray(differences, dtype=np.float64)
    except (TypeError, ValueError) as exc:
        raise ValueError("differences must be a finite one-dimensional array") from exc
    if values.ndim != 1 or not np.isfinite(values).all():
        raise ValueError("differences must be a finite one-dimensional array")
    count = len(values)
    if count < 5 * block_length:
        raise ValueError(
            "paired block bootstrap requires at least five effective blocks "
            f"({5 * block_length} observations for block_length={block_length}); got {count}"
        )

    rng = np.random.default_rng(seed)
    blocks_per_draw = math.ceil(count / block_length)
    offsets = np.arange(block_length)
    means = np.empty(draws)
    # Per-draw indexing bounds memory even for long hourly histories.
    for draw in range(draws):
        starts = rng.integers(0, count - block_length + 1, size=blocks_per_draw)
        indices = (starts[:, None] + offsets).ravel()[:count]
        means[draw] = values[indices].mean()
    tail = (1.0 - confidence) / 2.0
    lower, upper = np.quantile(means, [tail, 1.0 - tail])
    mean = float(values.mean())
    return {
        "method": "non-circular moving-block percentile bootstrap",
        "observations": count,
        "block_length": block_length,
        "effective_block_count": count / block_length,
        "blocks_per_draw": blocks_per_draw,
        "draws": draws,
        "seed": seed,
        "confidence_level": confidence,
        "mean_difference": mean,
        "mean_difference_ci": [float(lower), float(upper)],
        "annualization": float(annualization),
        "annualized_mean_difference": mean * annualization,
        "annualized_mean_difference_ci": [
            float(lower * annualization),
            float(upper * annualization),
        ],
        "caveats": [
            "Inputs must be paired over identical observation intervals.",
            "Approximate inference assumes an adequately stable weakly dependent process.",
            "Block length is prespecified; check sensitivity without selecting the best interval.",
            "Effective block count is a heuristic, not a proven independent sample size.",
            "Not anytime-valid, not multiplicity-adjusted, and not valid under arbitrary regime drift.",
            "Annualized mean is a linear scaling of the supplied differences, not CAGR.",
        ],
    }


def _predictable_bet(
    previous_sum: NDArray[np.float64], previous_squares: NDArray[np.float64]
) -> NDArray[np.float64]:
    """A nonnegative stake computed exclusively from previously revealed data."""
    return np.clip((previous_sum + 0.5) / (previous_squares + 5.0), 0.0, 1.0)


def _mc_estimate(values: NDArray[np.float64]) -> dict[str, Any]:
    """Uncertainty over independent worlds, never independent hypotheses."""
    count = len(values)
    mean = float(values.mean())
    standard_error = float(values.std(ddof=1) / math.sqrt(count))
    z = NormalDist().inv_cdf(0.975)
    if np.isin(values, [0.0, 1.0]).all():
        denominator = 1.0 + z * z / count
        centre = (mean + z * z / (2.0 * count)) / denominator
        radius = z * math.sqrt(mean * (1.0 - mean) / count + z * z / (4 * count**2))
        radius /= denominator
        interval = [max(0.0, centre - radius), min(1.0, centre + radius)]
        interval_method = "Wilson 95% interval across independent worlds"
    else:
        interval = [max(0.0, mean - z * standard_error), min(1.0, mean + z * standard_error)]
        interval_method = "normal 95% Monte Carlo interval for world-level rejection fractions"
    return {
        "estimate": mean,
        "standard_error": standard_error,
        "confidence_interval": interval,
        "confidence_level": 0.95,
        "independent_worlds": count,
        "interval_method": interval_method,
    }


def _rejection_summary(
    hits: NDArray[np.bool_], first_steps: NDArray[np.int64], steps: int
) -> dict[str, Any]:
    family_hits = hits.any(axis=1)
    detected_times = first_steps.min(axis=1)[family_hits]
    return {
        "family_rejection_rate": _mc_estimate(family_hits.astype(float)),
        "first_hypothesis_rejection_rate": _mc_estimate(hits[:, 0].astype(float)),
        "mean_hypothesis_rejection_fraction": _mc_estimate(hits.mean(axis=1)),
        "detected_worlds": int(family_hits.sum()),
        "median_first_family_rejection_step_among_detected": (
            float(np.median(detected_times)) if len(detected_times) else None
        ),
        "horizon_steps": steps,
        "timing_caveat": "Detection timing is conditional on rejection; nonrejections are censored.",
    }


def simulate_evidence(
    worlds: int = 2000,
    steps: int = 500,
    hypotheses: int = 20,
    seed: int = 7,
    alpha: float = 0.05,
) -> dict[str, Any]:
    """Compare valid anytime evidence with repeated approximate z-tests.

    Worlds are independent; within each world, hypotheses share shocks.
    Increments are bounded by one. Null increments have conditional mean zero
    with predictable, time-varying volatility. The stake is chosen before each
    increment using only previously revealed increments. Thus products of
    1 + stake * increment are nonnegative supermartingales under this *synthetic*
    null. Alpha/H thresholding plus Ville and the union bound gives FWER <= alpha
    without cross-hypothesis independence. All alternatives have drift 0.08.

    Every step is a fully matured non-overlapping outcome. This does not solve
    delayed/overlapping financial-label inference or prove a new theorem.
    """
    worlds = _integer("worlds", worlds, 100)
    steps = _integer("steps", steps, 20)
    hypotheses = _integer("hypotheses", hypotheses, 1)
    seed = _integer("seed", seed, 0)
    alpha = _probability("alpha", alpha)
    rng = np.random.default_rng(seed)
    shape = (5, worlds, hypotheses)
    sums = np.zeros(shape)
    squares = np.zeros(shape)
    log_e = np.zeros(shape)
    e_hits = np.zeros(shape, dtype=bool)
    e_single_hits = np.zeros(shape, dtype=bool)
    e_first = np.full(shape, steps + 1, dtype=np.int64)
    e_single_first = np.full(shape, steps + 1, dtype=np.int64)
    z_hits = np.zeros((2, worlds, hypotheses), dtype=bool)
    z_bonf_hits = np.zeros_like(z_hits)
    z_first = np.full(z_hits.shape, steps + 1, dtype=np.int64)
    z_bonf_first = np.full(z_hits.shape, steps + 1, dtype=np.int64)
    previous_common = np.zeros(worlds)
    if alpha / hypotheses == 0:
        raise ValueError("alpha/hypotheses is too small for the numerical z-test comparator")
    e_threshold = math.log(hypotheses) - math.log(alpha)
    single_threshold = -math.log(alpha)
    z_threshold = -NormalDist().inv_cdf(alpha)
    z_bonf_threshold = -NormalDist().inv_cdf(alpha / hypotheses)

    for step in range(steps):
        stakes = _predictable_bet(sums, squares)
        # All these state variables are known before the new shock is drawn.
        volatility = (
            0.20
            + 0.25 * (1.0 + math.sin(2 * math.pi * step / 60.0)) / 2.0
            + 0.25 * (previous_common > 0)
        )
        true_cost = 0.06 + 0.04 * (previous_common > 0)
        common = rng.choice([-1.0, 1.0], size=worlds)
        individual = rng.choice([-1.0, 1.0], size=(worlds, hypotheses))
        noise = volatility[:, None] * (0.6 * common[:, None] + 0.4 * individual)
        gross_null = noise + true_cost[:, None]
        increments = np.stack(
            [
                noise,
                gross_null - 0.12,
                gross_null - 0.02,
                noise + 0.08,
                gross_null + 0.08 - 0.12,
            ]
        )
        # The controlled construction keeps every scenario within [-1, 1].
        log_e += np.log1p(stakes * increments)
        sums += increments
        squares += increments * increments
        new_hits = log_e >= e_threshold
        e_first[new_hits & ~e_hits] = step + 1
        e_hits |= new_hits
        new_single = log_e >= single_threshold
        e_single_first[new_single & ~e_single_hits] = step + 1
        e_single_hits |= new_single

        # These tests use an asymptotic Gaussian critical value every step.
        # Their contrast is optional stopping, not a validated fixed-sample test.
        count = step + 1
        if count >= 20:
            selected_sums = sums[[0, 3]]
            selected_squares = squares[[0, 3]]
            variance = np.maximum(
                0.0, (selected_squares - selected_sums**2 / count) / (count - 1)
            )
            denominator = np.sqrt(count * variance)
            z_score = np.divide(
                selected_sums,
                denominator,
                out=np.zeros_like(selected_sums),
                where=denominator > 0,
            )
            new_z = z_score >= z_threshold
            z_first[new_z & ~z_hits] = count
            z_hits |= new_z
            new_z_bonf = z_score >= z_bonf_threshold
            z_bonf_first[new_z_bonf & ~z_bonf_hits] = count
            z_bonf_hits |= new_z_bonf
        previous_common = common

    def summary(index: int, adjusted: bool = True) -> dict[str, Any]:
        return _rejection_summary(
            e_hits[index] if adjusted else e_single_hits[index],
            e_first[index] if adjusted else e_single_first[index],
            steps,
        )

    return {
        "experiment": "known-null bounded sequential evidence; research simulation",
        "worlds": worlds,
        "steps": steps,
        "hypotheses": hypotheses,
        "seed": seed,
        "alpha": alpha,
        "per_hypothesis_bonferroni_alpha": alpha / hypotheses,
        "increment_bound": 1.0,
        "alternative_drift": 0.08,
        "null": {
            "anytime_e_bonferroni": summary(0),
            "anytime_e_unadjusted": summary(0, adjusted=False),
            "naive_repeated_z_bonferroni": _rejection_summary(z_bonf_hits[0], z_bonf_first[0], steps),
            "naive_repeated_z_unadjusted": _rejection_summary(z_hits[0], z_first[0], steps),
            "anytime_e_conservative_cost_bound": summary(1),
            "invalid_optimistic_cost_proxy": summary(2),
        },
        "alternative": {
            "anytime_e_bonferroni": summary(3),
            "anytime_e_unadjusted": summary(3, adjusted=False),
            "naive_repeated_z_bonferroni": _rejection_summary(z_bonf_hits[1], z_bonf_first[1], steps),
            "naive_repeated_z_unadjusted": _rejection_summary(z_hits[1], z_first[1], steps),
            "anytime_e_conservative_cost_bound": summary(4),
        },
        "cost_stress": {
            "units": "synthetic bounded utility units; not market fees or basis points",
            "true_cost_range": [0.06, 0.10],
            "deterministic_conservative_cost_upper_bound": 0.12,
            "optimistic_cost_proxy": 0.02,
            "interpretation": (
                "The conservative bound is valid by construction in these worlds. "
                "The optimistic proxy makes the purported null evidence invalid. "
                "No estimated-cost or market-execution guarantee is established."
            ),
        },
        "conditional_guarantees": [
            "For each valid null stream, predictable stakes in [0,1] and increments in [-1,1] "
            "with nonpositive conditional mean make the evidence a nonnegative supermartingale.",
            "Ville's inequality controls each anytime rejection at its assigned alpha; "
            "alpha/H and the union bound control synthetic family-wise error at alpha.",
            "Unadjusted per-stream thresholds do not provide family-wise control.",
            "These statements exclude the deliberately invalid optimistic cost proxy.",
        ],
        "caveats": [
            "This is an existing elementary betting construction, not a novelty claim.",
            "Monte Carlo intervals use independent worlds, not correlated hypotheses as replicates.",
            "The z-test comparator is approximate and repeatedly peeked; it has no anytime guarantee.",
            "No FDR, overlapping-label, delayed-feedback, or adaptive-hypothesis-birth theorem is claimed.",
            "Market backtest differences need not satisfy this conditional null or bound.",
            "Clipping changes the estimand and cannot silently repair unbounded financial returns.",
        ],
    }
