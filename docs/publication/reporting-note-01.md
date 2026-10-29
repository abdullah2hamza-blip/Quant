# Post-outcome reporting note 01: numerical identity

The frozen six-case market study completed without a strategy/configuration
change. Independent output review found that the four-hour adaptive procedure
made no scored-window pair switches. Binance's adaptive and fixed raw paths
are exactly identical. Bitstamp has earlier pre-window switches and different
inherited wealth, but its rebased paths are equal up to floating-point roundoff.

Preserve all original reports and their hashes. Bitstamp's raw grid sign-change
brackets are driven by differences around 1e-16 and must not be interpreted as
economic break-even costs. Generated publication outputs will explicitly mark
paired paths with maximum absolute per-bar log difference <=1e-12 as numerically
indistinguishable, using the pre-existing log-accounting identity tolerance.
This is a display/interpretation rule, not a new selection rule or return filter.
Always retain the actual numerical values in full machine-readable tables.

Likewise, a [0,0] block-bootstrap interval from an exactly zero realized
difference series describes degenerate resampling of this historical path. It
does not establish zero uncertainty about a future adaptive rule, prove a
permanent equality of expected returns, or justify positive discovery language.
Near-zero roundoff intervals receive the same explicit interpretation. This
correction was made after outcomes and is not described as pre-outcome design.
