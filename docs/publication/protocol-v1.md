# Publication study protocol v1

Registered design: October 21, 2026 America/New_York. The machine specification is
`configs/research/publication-study-v1.json`. Its hash and this document's hash
must enter the attempt ledger before substantive publication experiments start.
Source/data fingerprints will be pinned separately once implementation validation
passes. A changed design requires a new version, with reasons and prior access
disclosed. This is a local, retrospectively timestamped research protocol, not
an externally registered or independently witnessed preregistration.

## Question and contribution gate

Does uncertainty about *paired* trading costs destroy useful sequential evidence,
and how much of that loss is avoidable by retaining a defensible shared cost
structure? The proposed contribution is a measured validity/power diagnosis and
audited Bitcoin application. Safe betting, alpha spending, confidence sequences
and robust counterparts are prior art. The shared-interval width identity is an
elementary proposition. Do not claim an original general theorem from combining
them. Determine whether the empirical findings are sufficiently substantive for
a publication after comparison with the nearest full texts.

## Estimands and information

For the synthetic study, let qA and qB be nonnegative, pre-outcome turnover
coefficients. Under each data-generating law, theta is a fixed unknown common
mean-cost coefficient, with calibration observations in [0,cmax] having conditional
mean theta given all previous game information. Define
`D = G - (qA-qB)*theta - m`, where G is a bounded gross utility difference and m
is the declared materiality threshold. These units are synthetic utilities.
They are not backtest log returns or measured execution costs.

Primary strong-null comparisons require `E[D_t | oracle past] <= 0` at every
post-birth trial, with |D_t| <= B. The oracle past includes previous latent
utilities, calibration, policy and researcher information. A separate existing
Hoeffding mixture baseline addresses the weaker null that every post-birth
prefix sum of conditional means is nonpositive. Rejection of the strong null
does not establish positive average performance or a future trading edge.

Candidate decisions, birth/selection, alpha allocation, turnover and bets must
precede the affected outcomes. The fixed mixture components share the same
declared betting grid across methods. Do not claim pathwise wealth dominance
for independently refitted adaptive betting rules from increment dominance alone.
Delayed cases use non-overlapping trials, fixed bets at issue time and no label
access before maturity; a fixed calendar horizon reduces matured sample size.
General overlapping-label inference is outside the guarantee.

## Cost envelopes and error budget

Allocate family alpha 0.05 as 0.04 to utility tests and delta=0.01 to one global,
simultaneous calibration envelope. With n bounded calibration observations use
two-sided Hoeffding intervals with error spending
`delta_n = delta * 6 / (pi^2*n^2)` for n>=1; at n=0 use the entire support.
The conditional mean assumption must hold in the calibration filtration.
Calibration may be shared across all candidates; allocate its delta only once.

For theta in [l,u], the joint lower proxy is
`G - max((qA-qB)*l, (qA-qB)*u) - m`.
The separate-envelope proxy is `G-qA*u+qB*l-m`. Their gap is
`min(qA,qB)*(u-l)`. A symmetric upper cost for both strategies is not generally
conservative for their difference. Plugin cost estimates have no claimed bound.

Observed proxy wealth need not be an e-process on a high-probability coverage
event. A valid proof must compare it pathwise with latent valid wealth using
the same predictable bets, and add envelope failure probability without
conditioning on coverage. State oracle-filtration qualifications explicitly.
Clipping a proxy is permitted only when domination follows from a known bound
on the already-defined latent utility. Clipping financial returns changes the
estimand and is not an automatic fix.

Fixed families allocate test alpha uniformly. Adaptive births spend weights
`1/(j*(j+1))` in birth order; hypotheses consume only outcomes after birth.
Within-world dependence is allowed, but the stated conditional null remains
necessary. This controls FWER under the stated assumptions, not FDR.

## Registered simulations and reporting

Run every case in the JSON once with 4,000 independent worlds, 800 calendar
steps, fixed seed derivation and a fixed mixture grid. Cases cover global nulls,
mixed null/alternative families, weak effects, turnover overlap, search size,
delayed maturity, adaptive births, calibration budget, a weak-prefix null and
an explicitly invalid cost-stationarity stress. Invalid procedures and invalid
assumption scenarios must be visibly separated from claimed error control.

Primary measures are true-null family rejection probability and true-alternative
power for joint versus separate envelopes. Report Wilson Monte Carlo intervals
at world level; hypotheses are dependent, not simulation replicates. Report
detection delays with nonrejections censored, restricted detection time through
the horizon, cost-envelope coverage, accumulated incremental utility under a
declared paper-allocation rule, runtime and memory dimensions. No utility
metric simulates a funded live account. Compare the known-cost oracle, plugin,
symmetric-upper, fixed-horizon and repeatedly peeked controls. Keep every failed
and partial attempt. Publish all cases, including unfavorable or vacuous results.

Deterministic counterexamples address pointwise versus simultaneous envelopes,
observable versus oracle filtrations, symmetric upper costs, reuse of prescreened
outcomes and immediate use of delayed labels. Smoke tests use explicitly reduced
world/step counts and do not count as publication results.

## Market-data acquisition and analysis amendment

Existing access includes development and 2023-2024 selection data and their
reported results. They cannot be made unseen. Keep the original 4-hour strategy
and conservative gap reset as the primary continuation protocol. First extend
the immutable Binance public snapshot through 2026-10-20 and audit completeness
without computing strategy P&L. This is acquisition of known retrospective
history, not prospective confirmation. The old ledger's reserved counter counts
backtests, not data downloads or human prior knowledge.

The 2025-2026 period is the prespecified retrospective application. It may supply
enough post-gap history for a longer comparison without changing cleaning rules.
Do not relax gap controls to improve returns. If gaps still invalidate adequate
history, assess an independently audited second venue or a separately justified
gap amendment before viewing its P&L. Keep symbol, quote currency and venue
differences explicit. Public data availability does not establish measured fills.

Before market P&L is unblinded, pin source, protocol, strategy configuration,
runtime, data prefix, candidate controls, primary metric and reporting script.
Primary economic metric remains paired net mean log return at an assumed 25 bps
per side, with an annualized mean-log materiality threshold 0.02. Retain
10/25/50/100 bps scenarios and frozen base-cost selector choices. Existing cash,
buy-and-hold, volatility-targeted BTC and slow resizing controls remain; add a
prespecified smoothed selector as a complexity control. Run 1-hour and daily
robustness with preserved physical lookback durations and independent data
audits. Do not select the best interval or cost scenario.

Use paired non-overlapping calendar aggregation for diagnostics where justified,
moving-block uncertainty with declared sensitivity, and exposure/turnover
attribution. Approximate historical intervals remain separate from synthetic
sequential guarantees. The common mean-cost model is not identified by candles;
report cost fragility and unavailable quote/fill evidence honestly. A second
venue is a robustness comparison, not an independent Bitcoin history.

## Completion and stop rules

Scientific failure is a valid outcome: no adaptive gain, uninformative evidence
or impractical cost-calibration demands must be reported. A publication claim
requires a substantive finding and resolved proof/implementation review, not
just statistically significant backtest returns. Complete the full manuscript,
supplement, verified bibliography, generated figures/tables, replication package,
CI and visual PDF review. Do not publish or submit externally. Do not call the
goal complete while the requirements audit contains unverified essentials.
