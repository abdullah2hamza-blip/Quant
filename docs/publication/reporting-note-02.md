# Post-outcome block-centering diagnostic, 2026-10-23

The fresh PI review identified a finite-sample property of the registered
non-circular moving-block percentile bootstrap. Uniform sampling of overlapping
blocks weights interior observations differently from edges. Truncating the
final block also affects those weights. Thus the expected resampled mean need
not equal the observed mean, even with infinitely many bootstrap draws.

The new deterministic display enumerates the expectation analytically for all
possible block starts and the final truncated block, for every preserved case,
cost and 15/30/60-day block size. It neither changes the primary registered
intervals nor chooses a favorable replacement. Its implementation is checked
against exhaustive enumeration on a short artificial sequence.

For the 243-day matched market window the primary 30-day block count is only 8.1.
Neither that count nor the old five-block reporting heuristic establishes
stationarity, adequate mixing or finite-sample coverage. The broad intervals
are descriptive conditional approximations, not calibrated economic exclusions.
The existing negative interpretation is retained. A newly selected corrected,
studentized or circular interval would be a different post-outcome analysis.
