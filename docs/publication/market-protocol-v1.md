# Retrospective Bitcoin application: protocol v1

Written after source acquisition, independent raw/CSV reconciliation and
feature-only coverage inspection, before evaluating strategy P&L on the newly
acquired 2025-2026 observations. The original 2024 comparison and synthetic
demonstrations were previously inspected and remain disclosed. This is a local
timestamped protocol, not an external preregistration or prospective holdout.
The synthetic v1 simulation is running concurrently; its full estimates have not
been inspected when this application design is written.

## Question, endpoint and interpretation

Primary application: adaptive minus fixed EMA 50/200 mean net log return on
Binance BTC/USDT spot four-hour candles, 2025-01-01 through 2026-10-20 inclusive
UTC, at 25 bps assumed all-in cost per traded side. The materiality threshold is
0.02 annual log units, scaled linearly by bars per year. This is a descriptive
retrospective estimand. A 95% non-circular moving-block percentile interval with
30-day blocks and 5,000 resamples is the primary approximate uncertainty summary.
Compare the lower endpoint to materiality, but do not interpret this as a
selection-adjusted or anytime-valid discovery. The assumed stability and weak
dependence of this resampling approximation cannot be verified for an arbitrary
Bitcoin regime. No market e-process, cost-coverage guarantee or profitability
claim follows from the bounded synthetic model.

The machine specification is `configs/research/market-study-v1.json`; it lists
all six cases. Equal-window timeframe robustness is 2026-02-20 through
2026-10-20, determined by the latest eligible source history and rounded up to
a UTC day before outcomes were evaluated. Native 1-hour, 4-hour and daily source
histories have different outages. Preserve clock durations using upward integer
rounding of indicator, volatility, warm-up and selector windows; record exact
effective settings. This changes physical discretization and source coverage
together, and does not isolate candle frequency perfectly.

Bitstamp BTC/USD four-hour data repeat the primary and matched windows without
retuning. USD/USDT quote risk, venue-specific candles and different earlier gaps
are confounds. These are dependent observations of the same asset, not new
independent market replications.

## Policies and accounting

Retain the original `btc-trend.toml`: candidate EMA 25/100, 50/200 and 100/400;
20% annual volatility target; unlevered long/cash; zero cash interest; 0.10
absolute weight rebalancing band; prior completed-candle signal executed at the
next observed open. Volatility uses 180 four-hour returns; feature warm-up is
2,000 bars; selector history is 4,380 valid post-warm-up returns; select each
180 bars. Continuous net-of-base-cost shadow portfolios determine trailing mean
log-return rankings; ties retain the incumbent then prefer the reference.

Always report fixed, adaptive, cash, buy-and-hold, volatility-targeted BTC, slow
reference resizing, the arithmetic mean of candidate target weights (ensemble),
and both additional fixed candidates. The ensemble contains all three candidates,
including the reference.
Slow resizing still acts on entry/exit transitions; its minimum interval applies
to resizing an existing nonzero position. These exact controls were not selected
from the new evaluation returns. No additional original bot source was supplied.

Cash and coin holdings are inherited continuously from prehistory, rebased for
comparison at the immediately preceding close, and marked at the final close.
Terminal estimated liquidation is a separately labeled sensitivity, not a
fabricated fill. Self-financing post-fee weight trades use the exact buy/sell
equations. Preserve gap handling: cancel crossing orders, carry holdings, reset
features and require sufficient new selector history before making another
selection. The incumbent adaptive pair can resume trading after feature warm-up,
before selector history is again sufficient; it is not replaced during that
pause. Do not silently repair or
fill missing candles. A primary-window start without valid selector history is
an error, not a reason to shift the score start after seeing returns.

Apply costs [0,10,25,50,100] bps per side; 25 is the base scenario. The zero-cost
case is a frictionless diagnostic added before new P&L, not a feasible cost
assumption. Freeze base-cost selector choices across stress costs. Re-execute
the same declared target procedure and continuous histories at each cost, so
fee effects on wealth, weights and band-triggered trades remain part of the
self-financing sensitivity. Do not subtract an ex-post linear turnover cost
from a fixed wealth path and call it exact.

## Attribution, comparisons and robustness

For each strategy and bar, decompose its net log return exactly into:
log(pre-trade open NAV / previous close NAV), log(post-trade open NAV /
pre-trade open NAV), and log(close NAV / post-trade open NAV). The middle term
is exact fee drag; the others reflect holdings and price moves. Verify their
sum against recorded NAV changes and fees against pre/post-trade wealth.
Differences across policies are descriptive accounting attribution, not a
causal estimate of selection alpha. Report exposure, volatility, turnover,
drawdown, trades, terminal exposure and return metrics alongside this identity.

Report adaptive-minus-fixed paired intervals at every cost and adaptive-minus-
control intervals at base cost. Use 15- and 60-day block sensitivities in
addition to the prespecified primary 30-day block. Physical block durations
match across timeframes. Fewer than five blocks or a missing scored interval
makes that interval unavailable; do not substitute IID inference. Use common
bootstrap resampling indices across paired contrasts within a case. All
secondary comparisons, calendar-year subperiods and cost signs are exploratory
robustness summaries with unadjusted intervals, not separate confirmed claims.

Provide cost-grid sign-change brackets for adaptive-minus-fixed cumulative log
return. Do not assume monotonic differences, a unique break-even cost or exact
linear interpolation. Report every scenario even when all results agree or
none has sufficient precision. Never choose a new strategy or timeframe using
these comparisons without a separately labeled exploratory amendment.

## Gate, provenance and attempts

The publication market freeze separately pins this protocol, specification,
implementation/tests/scripts, runtime, actual source ZIP, independent review,
all input CSVs, manifests and independent audit records. Creating the freeze
may inspect feature coverage only and must not simulate portfolio returns.
The hourly 2023-2024 selection interval lacks eligible history; this publication
gate honestly registers a prespecified robustness procedure rather than
claiming the older selection-run gate succeeded. The earlier CLI remains intact.

Require an explicit retrospective acknowledgement and matching freeze before
executing this study. Log parent and case attempts before computation, including
failed accesses; retain partial outputs. Save all scenario NAV/holding/cost/
turnover/attribution arrays, initial holdings, base-cost trades, selections,
full effective settings and hashes. Full results, not just favorable tables,
must be retained for independent checking and manuscript generation.

Candles cannot establish capacity, order-book spread, latency, actual fills or
the stationarity of unobserved execution costs. All-in cost scenarios address
sensitivity only. Public archive snapshots and retrieval-time API responses do
not certify point-in-time historical availability. These limitations constrain
the scientific claims even if the strategy appears favorable.
