# BTC paper-aligned trend bot (v3)

This delivers the completed paper's BTC spot EMA protocol and a corrected
daily version of the supplied SMA strategy. It defaults to the fixed EMA50/200 reference on4h UTC candles,
20% annual volatility targeting, at most100% long exposure and10-point resizing.
`--policy legacy_daily` explicitly selects the separate daily SMA alternative.
Adaptive25/100,50/200,100/400 selection is an explicit research option. The
paper found **no demonstrated adaptive advantage**. Correct implementation is
not a promise of future profit.

The original14-file bot is archived with hashes in `paper-origin.json`.
`MIGRATION.md` records the differences, defects and verification gates. Four
reviewed numerical modules are carried byte-for-byte in `paper_engine/`; every
command checks those hashes. Existing paper artifacts are not modified.

## Environment

Use Python3.13.7 and uv0.13.4. Run from this folder:

```sh
uv sync --locked
uv run --locked python trend_bot.py doctor
uv run --locked python research/checks.py
```

The only runtime dependency is the pinned NumPy version used by the paper.
Pytest is a development dependency. Broker adapters use Python's standard
library. No exchange credentials are needed for historical replay or local sim.

## Replay the paper

The included `data/btc-4h.csv` is the immutable audited2017-09-01 through
2026-10-20 seed. The adjacent manifest binds its bytes. A new output directory
is required; successful and failed attempts are preserved.

Seed data are local inputs excluded from Git. In a fresh checkout without
the included local seeds, acquire both into new files using the audited fetcher:

```sh
uv run --locked python research/get_data.py --interval 4h --end 2026-10-20
uv run --locked python research/get_data.py --interval 1d --end 2026-10-20
```

```sh
uv run --locked python trend_bot.py backtest --cash 1 --output runs/paper-replay
uv run --locked python trend_bot.py signal --policy fixed
uv run --locked python trend_bot.py signal --policy adaptive
```

Replay computes all nine policies at0/10/25/50/100bps, with base25bps selector
choices frozen across costs. It uses completed-close features, next-open trades,
exact self-financing cash/coin books, inherited prewindow positions and marked
terminal holdings. It does not subtract fees from an unchanged wealth path.
The default2025-01-01 through2026-10-20 window is retrospective and already spent.

To compare all six cases directly with the paper's preserved270 policy/cost
paths, supply the Quant research root and a new output directory:

```sh
uv run --locked python research/run_all.py --research-root C:/Users/Abdul/Documents/Quant --output runs/all-paper-cases
uv run --locked python research/checks.py
```

Hourly/daily paper replay accepts `--interval`, appropriately scaled lookbacks and an
independently audited native CSV. Different frequencies must use matched dates
and sufficient history. Execution supports the paper's4h policy and the separate
`legacy_daily` native1d policy.

## Corrected original daily alternative

```sh
uv run --locked python trend_bot.py doctor --policy legacy_daily
uv run --locked python trend_bot.py signal --policy legacy_daily
uv run --locked python trend_bot.py backtest --policy legacy_daily --cash 1 --output runs/daily-replay
uv run --locked python trend_bot.py sim --policy legacy_daily --once
```

This option uses the original40/50/60/80/100/150-day SMA vote,40% annual
volatility target,30 daily log returns and15-point resizing band, with no leverage.
It chooses `data/btc-1d.csv` and `state/legacy-daily.sqlite` automatically. The
included native daily seed has its own checksum manifest; candles are not
resampled from4h data. The configuration is frozen in `config/legacy_daily.json`.

The original signal agrees after full warm-up, but three corrections affect
execution: require150 continuous candles and restart that warm-up after gaps;
check the resize band at the executable opening valuation; solve post-fee
weights without borrowing. Entries and full exits share the paper's band rules.
This is an exploratory alternative outside the paper's registered EMA family.
It is not numerically identical to the old close-trigger backtest. The original
source is preserved in `legacy/original-v2.zip`.

Daily replay includes a separately named clock-scaled daily EMA control,
cash, buy-and-hold and volatility-only books, with0/10/25/50/100bps reruns and
retrospective15/30/60-day paired block intervals. Its daily EMA control is not
the default native4h strategy. Risk targets differ between the strategies.

## Local paper simulation

```sh
uv run --locked python trend_bot.py sim --once
uv run --locked python trend_bot.py sim
```

Online sim appends completed Binance BTCUSDT candles from the public data API,
retains the full continuous shadow history and uses current observable prices.
A fresh paper account starts with `--cash 10000`; it does not inherit hypothetical
research profits. Simulation records25bps modeled all-in cost. Current-price
fills are distinguishable from the replay's assumed next open.

A decision is eligible only within120seconds of its UTC4h or daily opening boundary. Late
startup records a skip and waits for the next completed candle. Re-running a
candle or restarting does not produce a second trade. Invalid/gapped history
pauses features without silently filling candles or selling carried inventory.
A `STOP` file blocks new orders. State is in `state/paper.sqlite`; use a separate
state for each mode/account/policy. Never reuse the old v2 JSON state blindly.

For an explicitly historical, offline one-cycle mechanics check, supply an
integer UTC millisecond clock immediately after the final seed candle and an
explicit simulated price. These overrides are rejected in all online/broker modes:

```sh
uv run --locked python trend_bot.py sim --offline --once --as-of-ms 1792540800100 --price 80000 --state state/offline.sqlite
# The same historical clock also follows the included daily seed's final close.
uv run --locked python trend_bot.py sim --policy legacy_daily --offline --once --as-of-ms 1792540800100 --price 80000 --state state/daily-offline.sqlite
```

## Broker paper/testnet modes

```sh
# Set BINANCE_TESTNET_KEY and BINANCE_TESTNET_SECRET in your environment.
uv run --locked python trend_bot.py binance --once --state state/binance.sqlite
# To select the daily alternative, add --policy legacy_daily and use a new state.
# Set ALPACA_API_KEY and ALPACA_API_SECRET for a dedicated paper account.
uv run --locked python trend_bot.py alpaca --once --state state/alpaca.sqlite --allow-quote-basis
```

Adapters are fixed to Binance Spot Testnet and Alpaca paper. Their quotes,
asset increments/minimums, balances, pending orders and actual response IDs are
checked. Sandbox sizing reserves100bps for uncertain fees; it cannot make a
market fill exactly equal a historical next-open model. Alpaca USD fills also
introduce an acknowledged basis difference from Binance USDT signals.

Order intents commit before submission. After a timeout or interrupted response,
the bot queries the same client order ID and blocks new orders while uncertain
or partially filled. It never substitutes a ticker price for an actual fill.
A stale `.lock` after a crash must be inspected against its recorded PID before
manual removal. Resolve ambiguous broker orders before restarting a new state.
Use a dedicated spot/cash paper account and one state/process per account.
No production-money trading endpoint is implemented.

## What the evidence supports

On2025-01-01 through2026-10-20, at25bps the primary fixed and adaptive policies both returned2.6067%, with
20.05% realized maximum drawdown and no adaptive-window switches. Hourly/daily
adaptive differences were negative and imprecise. These do not establish a
profitable adaptive edge, calibrated execution costs or future downside bounds.
The synthetic sequential guarantees are not applied to OHLC trading returns.

The delivered corrected daily alternative returned11.8784%, with25.1663%
maximum drawdown sampled at daily closes and101 trades. At100bps its return
was negative8.4427%. Its daily EMA control returned negative2.4915%; the
30-day-block95% interval for their annualized mean-log difference was
[-11.75%,23.00%], including zero. This is an unadjusted retrospective comparison
on already inspected data, at unequal risk targets, not evidence of a reliable
advantage. Daily-close drawdowns omit intraday excursions and cannot be directly
equated with4h drawdowns. `validation/legacy-report.json` records the actual
delivered variant; `validation/before-after.json` preserves the distinct old
close-trigger accounting diagnosis.

Original v2 results, preregistration and forward-log statements are labeled
historical in `research/`. The old mean-reversion entry point delegates to this
EMA bot. The old ML/grid-search executables are retired rather than being
presented as validated parts of the paper. See `API-SOURCES.md` for the official
adapter contracts. Current tests/replays and any remaining account-integration
limits must be recorded before migration completion is claimed.

Current recorded working-copy evidence:50 isolated tests pass, all270 paper
paths and1,632 saved arrays match, and offline restart/public-data checks pass.
See `validation/quality.json`. Installed-copy checks are in the separate
installation receipt. No authenticated broker order test or profitable edge
is claimed.
