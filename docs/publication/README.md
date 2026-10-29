# Research overview

The current study diagnoses how paired strategy comparisons lose information
when a defensibly shared cost coefficient is bounded separately across
portfolios or independently across time. It compares established linear,
empirical-Bernstein and adaptive-betting constructions, followed by a separate
retrospective Bitcoin application. No first-method or profitable-bot claim is
made, and no market cost-calibration guarantee is inferred from candles.

## Studies and chronology

The [baseline protocol](protocol-v1.md), [addendum](protocol-v1-addendum-01.md)
and [machine specification](../../configs/research/publication-study-v1.json)
define 24 cases with 4,000 worlds each. The [follow-up](followup-protocol-v2.md)
defines 25 cases and was frozen after the baseline was inspected, before its
own substantive run. Factorial cells share seeded innovations and cannot be
pooled as independent replications. Error budgets apply within a comparator's
candidate family, not across a favorable selection of methods.

The [market protocol](market-protocol-v1.md) defines six cases across Binance
BTC/USDT and Bitstamp BTC/USD. Nine books and five costs yield 270 registered
paths. The four-hour adaptive selector retains the fixed EMA reference in the
scored window. Native hourly/daily checks are negative and imprecise.

The separately supplied original daily SMA bot arrived after the initial
study. Its [dated extension protocol](bot-extension-protocol-2026-10-23.md)
preserves the delivered .15-band/150-warm-up correction separately from a
matched .10-band/334-warm-up SMA/EMA contrast. These 40 paths are post-outcome
exploratory evidence on reused history; both central intervals include zero.

## Limits and reproduction

The bounded synthetic utilities and simultaneous cost-calibration assumptions
are not asserted for market portfolios. Market intervals are approximate,
retrospective and unadjusted. The [edge-weighting diagnostic](reporting-note-02.md)
retains the original bootstrap results and documents the short-window limit.
[Reporting note 01](reporting-note-01.md) distinguishes floating-point identity
from economic break-even evidence.

Use [REPRODUCE.md](REPRODUCE.md) for integrity checks, data-free manuscript
builds and exact archived-source computation. The [submission guide](SUBMIT.md)
identifies the standalone manuscript and public replication artifacts.
The [literature register](literature-comparison.md) records nearest work and
access limits without certifying exhaustive priority. Local internal checks
are distinct from external peer review and venue acceptance.
