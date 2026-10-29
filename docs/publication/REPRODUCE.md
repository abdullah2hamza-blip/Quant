# Reproduction and data access

Run from the repository/release root. Use Python 3.13.7, uv 0.13.4 and `uv.lock`.
The original computations used NumPy 2.5.4. Do not silently substitute a mutable
hosted notebook environment for the frozen numerical runtime.

```sh
uv sync --locked --python 3.13.7
uv run --locked pytest -q
```

The single manuscript entrypoint offers four distinct modes. Always choose a
new output directory; earlier attempts and accepted results are not overwritten.

## Integrity only: no vendor data or compiler

```sh
uv run --locked python -m scripts.reproduce_complete_study --verify-only --output runs/verify-local
```

This verifies saved collections, source archives, scientific summaries and
ledger chains. It does not run new Monte Carlo experiments or certify market
assumptions.

## Saved-results paper build: no vendor candles

```sh
uv run --locked python -m scripts.reproduce_complete_study --results-only --output runs/paper-local --tectonic /path/to/tectonic
```

This rebuilds the registered and exploratory displays, bibliography and paper
from verified outputs. It explicitly performs no raw-data audit or substantive
compute replay. Tectonic 0.17.0 is required; its executable and TeX package cache
are not bundled. A first compile may fetch standard TeX packages. PDF metadata
can change bytes; numerical agreement and rendered-page layout are separate
checks.

## Restore exact market inputs

Four adjacent `data/*.manifest.json` files identify the pinned snapshots. Raw
and normalized vendor candles are excluded from the public release. Restore
from a legally obtained cache of the original bytes:

```sh
uv run --locked python -m scripts.restore_market_inputs --cache-root /path/to/data/raw --receipt runs/restoration.json
```

Alternatively add `--download` to fetch missing files from the recorded vendor
URLs. Vendor archive/response hashes, available checksum records, timestamp
normalization, quarantines and normalized CSV bytes are checked. Independent
raw-to-CSV auditors reconcile all four datasets. Revised vendor bytes fail;
they are not relabeled as the original snapshot. Existing conflicting files
are refused. Exact market replay needs matching snapshots if a vendor revises
or removes them; preserved-result review remains possible without them.

Coverage is September 1, 2017--October 20, 2026, with Binance native 1h/4h/1d and
Bitstamp 4h inputs. Current snapshots do not prove historical point-in-time
availability. USD and USDT histories concern the same underlying asset and are
not independent markets. Provider reuse terms remain in THIRD_PARTY.md.

## Raw-audited paper build and full numerical replay

After restoration, the ordinary default independently audits raw versus
normalized data before building the paper:

```sh
uv run --locked python -m scripts.reproduce_complete_study --output runs/audited-paper --tectonic /path/to/tectonic
```

The full mode also launches the original source versions in separate processes:

```sh
uv run --locked python -m scripts.reproduce_complete_study --full --output runs/full-replay --tectonic /path/to/tectonic
```

It compares 24+25 synthetic cases, six market cases and the separate daily bot
extension against accepted arrays and scientific JSON. Reusing the same seeds
and history creates no new independent evidence. `--full`, `--verify-only` and
`--results-only` are exclusive. An explicitly reverified earlier baseline replay
may be reused only through the documented `--reuse-baseline-replay` full-mode
option; it must have a completed matching ledger receipt.

Accepted collections are `results/publication-v1`, `results/publication-v2`
and `results/bot-extension-v1`. Their source ZIPs, protocol bytes, arrays and
ledger snapshots are immutable. Line-ending conversion is disabled for hashed
artifacts. Current helper changes do not authorize edits to old frozen sources.

## Kaggle and the operational bot

[The Kaggle notebook](../KAGGLE.md) is an offline saved-results review, records
its actual runtime and writes to a working output directory. It does not claim
that frozen simulation replay ran in Kaggle's mutable environment.

The standalone bot defaults to fixed four-hour EMA and has 50 recorded regression
tests, separate from root research tests. From `bots/btc_trend_bot`, run:

```sh
uv sync --locked
uv run --locked python trend_bot.py doctor
uv run --locked python research/checks.py
```

Doctor reports missing seeds without pretending a historical replay ran. The
public tree omits bot vendor seed CSVs/manifests. After exact root restoration,
copy the pinned daily/four-hour CSVs and adjacent manifests to the bot's
`data/btc-1d.*` and `data/btc-4h.*` names to replay that implementation. Historical
installation receipts describe the original complete local installation.
