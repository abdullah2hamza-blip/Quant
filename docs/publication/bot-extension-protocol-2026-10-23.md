# Post-protocol original-bot extension

Specified2026-10-23 after inspection of the completed paper and bot migration.
This is an exploratory post-outcome amendment, not a fresh holdout or a change
to the frozen49 synthetic/six market cases. No best strategy will be selected.

## Existing delivered implementation

Retain the delivered native daily SMA vote (40/50/60/80/100/150),40% volatility
target,30 log returns,150-bar contiguous warm-up and.15 opening-weight band.
Report its existing25bps and0/10/50/100bps books, with corrected post-fee
no-borrowing accounting, shared entry/full-exit rules, inherited positions and
marked terminal holdings. Preserve the original14-file archive. Do not quote
the separate fee-only old-loop diagnostic unless its exact computation is
distributed; it is not the delivered variant.

## Matched-configuration signal contrast

Use the pinned native Binance daily data,2017-09-01 through2026-10-20, and score
2025-01-01 through2026-10-20. Use the same initial equity1 before prehistory;
score relative to each book's actual prior-close NAV. Compare fixed SMA vote
with fixed EMA9/34 (the paper's upward clock conversion of50/200), at each
volatility target.20 and.40. All matched books share30 sample log returns,
annualization365, cap1, opening-weight band.10,334-bar continuous warm-up,
gap carry/reset/cancel rules, next-open execution and exact fee accounting.
Mask SMA validity to the same334-bar feature-valid mask as EMA; require valid
common history at the scored boundary. No selector-history gate is needed for
these fixed rules. These SMA variants are distinct from delivered legacy_daily.

Include cash, buy-and-hold, and volatility-only controls at both target levels.
Rerun all books at0/10/25/50/100bps with fixed signals, not a fee subtraction.
Report return, descriptive Sharpe, realized volatility, exposure, turnover,
trades and daily-close drawdown for every book/cost. Targets do not guarantee
equal realized risk. Contrast SMA minus EMA separately within each target and
cost; use the existing approximate paired non-circular moving-block routine,
5000 draws,15/30/60-day blocks, seed20261023. Report every contrast and interval.
No multiplicity-adjusted or sequential inference, causal alpha, significance
selection, new optimal band, or future profitability claim is permitted.

## Provenance and required gates

Freeze this protocol, machine settings, daily input/manifest hashes and actual
executed source bytes before the new computation. Preserve attempts and bind
outputs to their source snapshot. Independently check opening trades, cash/coin
identities, prewindow holdings, contrast definitions and generated displays.
Keep old registered outputs and historical bot receipts unchanged. The final
source package must execute these checks without a Downloads path or credentials.
