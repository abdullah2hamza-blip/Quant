# Protocol v1 addendum 01: implementation details before substantive runs

This addendum is written after smoke tests, independent mathematical review and
data-coverage inspection, before any 4,000-world publication simulation or new
2025-2026 strategy P&L. It preserves the original protocol rather than replacing
its historical registration. No numerical performance result motivated a change.
Its hash must be included in the substantive freeze and attempt ledger.

## Exact bounded-game generator

Under each valid generating law, the unknown common coefficient is fixed at
theta=0.08 and calibration support is [0,0.2]. Initial calibration is generated
as n0 independent bounded Bernoulli observations, represented by their sufficient
sum `0.2*Binomial(n0,theta/0.2)`. Later add one independent bounded calibration
observation after each matured trial, so it is available only at the next issue.
The interval at issue uses preceding samples, including n0, not the current
utility outcome. The stationarity-violation case changes theta to 0.18 halfway
through the calendar horizon and is explicitly outside that fixed-mean model.

For each independent world, draw fresh common and candidate-specific Rademacher
shocks S and I_j at trial maturity. **The common shock S is publicly observed at
maturity.** Before the next outcome, turnover and volatility may use the prior
matured S. They never access the current or future shock. Define

```text
sigma_t = 0.2 + 0.2*(1+sin(2*pi*issue_time/80))/2 + 0.15*1{S_previous>0}
noise_j = sigma_t*(0.6*S + 0.4*I_j)
qA = 0.7 + 0.1*1{S_previous>0}
qB = qA*overlap
```

The reference-more-turnover cases swap qA and qB. In mixed families, even-indexed
candidate streams have declared effect and odd-indexed streams have zero effect.
`D_j = noise_j + effect_j` is already adjusted for materiality. Generate observed
gross utility `G_j = D_j + (qA-qB)*theta + m`. Latent D is used only for truth and
evaluation, not cost estimation, prescreen selection or bets. The bound |D|<=1
holds by construction. The prefix-weak null case replaces all effects with
alternating -0.07,+0.07, beginning negative.

Adaptive births occur at predeclared calendar spacings. At each birth choose the
highest cumulative past plugin utility among unused pool candidates; ties prefer
the smallest candidate index. Past prescreen outcomes are not inserted into the
new evidence stream. Test-alpha spending follows birth order. In delayed cases,
issue at 0,d+1,2(d+1),... and mature at issue+d+1. There is no intermediate
feedback in this game. A fixed horizon therefore reduces both utility outcomes
and per-trial calibration samples when d increases.

The same fixed lambda grid and equal mixture weights are used for joint,
rectangular and known-cost comparisons. Oracle and proxy utility tests all use
the same 0.04 family test budget, allowing direct comparisons; the known-cost
oracle does not need the additional 0.01 calibration budget, so its theoretical
bound is correspondingly conservative at total level 0.05.

## Fixed linear mixtures and the weaker null

The independent mathematical review established an additional valid interpretation
of the implemented constant-component linear mixture. For each fixed lambda<1,
divide its latent factors by `1+lambda*mu_t/B`, where mu_t is the oracle-history
conditional mean. The resulting ratio product is a martingale. Under a
nonpositive conditional-mean sum at every prefix, the product of denominators is
at most `exp(lambda*sum(mu_t)/B)<=1`. Thus the original fixed-component product is
dominated by a martingale under the prefix-weak null as well as the strong null.
Fixed mixtures and the cost-envelope error composition inherit the result.

This does not hold automatically for independently refitted adaptive lambdas.
The complete proof and literature qualifications are in the mathematical review.
The result is elementary multiplicative-compensator algebra and is not claimed
as an original theorem. The Hoeffding comparison remains useful as a transparent,
potentially less powerful existing baseline.

## Reporting corrections and negative controls

Compare joint and rectangular first-stream *rejection rates*. On null cases the
difference is not power. The pathwise nesting makes their difference a binary
joint-only rejection event; use a world-level Wilson interval, including when
zero such events occur. A normal Monte Carlo interval for degenerate utility or
censored-time samples is unavailable rather than [0,0]. Show the empirical mean
and zero sample standard error with a clear lack-of-uncertainty-estimate flag.

Detection times are calendar times from study origin. Undetected worlds are
horizon-censored; conditional detection medians exclude them and are labeled.
The first discovery activates one paper candidate only on subsequent trials;
ties use the lowest test index. Utility is additive and based on the synthetic
mean-cost model, not realized fill-cost shocks or a funded account.

Exact counterexamples now include reuse of prescreened null labels: repeatedly
selecting the maximum of ten already-observed fair signs and scoring it again
gives an expected selected label `1-2^(1-10)>0`, despite each original sign's
zero mean. Repeated positive selected batches can cross a nominal threshold with
probability close to one. Pointwise-only cost coverage likewise has an explicit
finite-horizon binomial false-rejection calculation. These are negative controls,
not valid procedures in the substantive comparison.

## Market coverage determination before P&L

The audited source files extend through 2026-10-20. Applying feature-history
validity, without simulating portfolios, gives first supported scored opens:

| Interval | First supported open, UTC |
|---|---|
| 1 hour | 2026-02-19 22:00 |
| 4 hours | 2024-08-27 16:00 |
| 1 day | 2020-07-31 00:00 |

Primary retrospective application remains 4-hour data from 2025-01-01 through
2026-10-20. The fair timeframe comparison uses **2026-02-20 through 2026-10-20**,
rounding the latest supported open up to a whole UTC day. This derives from
coverage and warm-up rules, not strategy returns. Native daily and hourly candles
have different outage coverage, which remains a substantive limitation.

The simpler adaptation control will be a nonselective ensemble: the arithmetic
mean of the three candidate target weights at each valid close, with the same
execution, cost, risk-cap and rebalance rules. It smooths across declared
lookbacks without choosing a retrospective winner. It is an additional baseline,
not a replacement for the fixed or adaptive primary policy. This exact definition
must be implemented and tested before market outcomes are viewed.
