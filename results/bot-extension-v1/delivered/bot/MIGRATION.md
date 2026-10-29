# Migration from supplied v2 to the paper protocol

The supplied folder was found at
`C:\Users\Abdul\Downloads\btc_trend_bot_full\btc_trend_bot`.
All14 original files are preserved in the checksum-bound archive named in
`paper-origin.json`. Development happens in `Quant/bots/btc_trend_bot`; only a
verified versions are synchronized back to the original folder with a per-file
hash inventory and copied-source checks in `validation/installation.json`.

The original code used daily price/SMA ensembles,40% volatility targeting,
30days of volatility and a15-point band. Those rules and the claimed v2 results
are a different study from the completed paper. They are not evidence for this
replacement. The old resizing equation could leave negative cash at a100%
target because it purchased the entire pre-fee NAV and then debited fees.
The old restart loop lacked a durable candle/order identity. Its research delay
check shifted prices instead of isolating delayed execution on unchanged prices.
Its reported forward test starts before its stated strategy freeze, so that
portion cannot be treated as prospective evidence for these changes.

The replacement uses exact reviewed modules, byte-bound to `paper-origin.json`:
4h UTC BTC spot, long/cash EMA50/200,20% annual volatility target,180 prior
log returns, exposure at most100%,10-point resizing band, and2,000-bar warm-up.
Optional adaptation uses25/100,50/200,100/400 continuous shadow books,4,380
post-warm-up returns and180-bar selection cadence. Ties retain the incumbent.
Features reset at gaps, orders cannot cross missing bars, and spot holdings
are carried. Replay inherits prewindow holdings and marks terminal holdings.
All5 cost scenarios retain the25bps selection schedule and rerun exact books.

The default execution policy is the simple fixed reference. Adaptive and
ensemble policies are explicit options. The paper establishes no adaptive
advantage; the default is a complexity decision, not a profit claim or a new
out-of-sample strategy selection. Research controls remain available in replay.

The user's final preference also retains `--policy legacy_daily` as a clearly
labeled alternative. Its original daily SMA vote and40% risk settings are
preserved. It requires150 continuous candles, evaluates bands at the executable
price with shared entry/exit rules, and uses exact no-borrowing fee accounting.
These execution corrections differ from the supplied close-trigger backtest;
the new alternative is not silently described as a registered paper strategy.
Its native daily data, configuration and SQLite state are separate from the
default4h protocol. Both policies use the same order/restart protections.

Execution and replay have different fill information. Replay uses the next
observed open and25bps assumed all-in cost. Online simulation uses a current
observable midpoint plus that modeled cost. Sandbox modes use actual broker
responses, not a quoted-price substitute for a fill. They reserve100bps when
sizing for uncertain fees and observe exchange increments/minimums. Real fills,
fee differences, quote basis, latency and capacity can diverge from the paper.

SQLite state binds source/configuration, policy, account identity and immutable
seed. Candle events and simulated cash/coin updates commit together. Broker
intents commit before POST. Restarts reconcile client order IDs, partial fills
and ambiguous outcomes before any new order. A missing remote result after an
ambiguous submission blocks resubmission for manual reconciliation. A local
process lock prevents concurrent use of one state. Stale decisions, stale/wide
quotes, bad data, legacy JSON state and a `STOP` file suppress new orders.
Artificial clocks/prices are restricted to an explicit offline simulation.

This migration is not complete until the isolated test suite, six-case numerical
parity, offline/restart CLI checks, public-data integration, interpretation audit
and synchronization checks have actual recorded results. Broker account tests
can be exercised only when paper/testnet credentials are supplied; none are
required for offline testing. No production-money order endpoint is provided.

## Verified working-copy evidence

The isolated locked environment passed50 tests. The completed six-case replay
matched270 policy/cost paths and1,632 account/time arrays exactly, including
all metrics, inherited states, base trades, selections and registered bootstrap
intervals. The offline CLI filled once and skipped the same candle after restart.
The actual public-data append and quote reads passed; a late decision correctly
skipped trading. `validation/quality.json` and its local receipts preserve
these checks and the negative economic conclusion. Authenticated broker tests
remain unperformed because no paper/testnet credentials were present.
Original-folder synchronization and copied-source tests are separately receipted
after the working copy is installed.

The final daily implementation returned11.8784% at25bps over the same inspected
2025-01-01 through2026-10-20 period, with25.1663% daily-close drawdown; its
100bps sensitivity lost8.4427%. A daily EMA control and dependent-data interval
are included, with the interval crossing zero. These results supersede no paper
claims and do not establish future profitability. The earlier fee-only corrected
old close-trigger diagnostic returned13.6577%; it is a different implementation.
`validation/legacy-signal.json` independently checks3,188 daily target values
against the original function, agreeing within8.4e-15 after full warm-up.
