# Cost-aware Bitcoin trend research

A reproducible diagnostic study of sequential strategy validation under uncertain
execution costs, with an audited Bitcoin trend-following application and a
separate operational simulation bot. The statistical constructions use
established methods; no new general theorem or demonstrated adaptive trading
edge is claimed.

The current manuscript is [the technical report](output/pdf/cost-aware-bitcoin-research-v5.pdf).
The [research overview](docs/publication/README.md),
[reproduction guide](docs/publication/REPRODUCE.md),
[GitHub release guide](docs/GITHUB.md), and [Kaggle guide](docs/KAGGLE.md)
explain the scientific and platform scopes.

The public technical-report release is being prepared as **v1.0.1** for the
existing [Quant repository](https://github.com/abdullah2hamza-blip/Quant) and
the author's Kaggle account `abdullah2hamza`. Hosting, the final tag/commit,
public accessibility and hosted notebook execution remain unverified until
the publication record reports their actual results. GitHub/Kaggle hosting
does not constitute journal acceptance or independent human peer review.

## What is included

- Two synthetic studies: 24 baseline and 25 follow-up cases, each with
  4,000 independent worlds within the case and an 800-step horizon.
- Six retrospective market cases, nine portfolios and five assumed cost levels:
  270 registered portfolio paths, plus a separately dated exploratory 40-path
  daily SMA/EMA contrast and preserved delivered-bot evidence.
- Exact frozen specifications, executed source archives, accepted results,
  ledger snapshots, generated displays and a standalone LaTeX manuscript.
- A separately packaged [Bitcoin bot](bots/btc_trend_bot/README.md) with local
  simulation and broker paper/testnet adapters. Its default is fixed EMA 50/200
  on four-hour UTC candles; the corrected daily SMA policy is explicit.

At 25 bps per traded side, the primary January 2025--October 2026 fixed and
adaptive EMA paths both returned 2.6067%, with no evaluation-window switches.
The daily SMA extension is exploratory and its two central matched-settings
contrast intervals include zero. Conditional synthetic error guarantees do not
transfer to these historical market comparisons.

## Install and verify

Use Python 3.13.7 and uv 0.13.4 with the included lock:

```sh
uv sync --locked --python 3.13.7
uv run --locked pytest -q
uv run --locked python -m scripts.reproduce_complete_study --verify-only --output runs/verify-local
```

These checks use saved evidence and fabricated test fixtures; vendor candles are
not needed. Pytest uses its normal temporary directory on a fresh checkout.

To rebuild the displays and paper without vendor candles:

```sh
uv run --locked python -m scripts.reproduce_complete_study --results-only --output runs/rebuild-local --tectonic /path/to/tectonic
```

Tectonic 0.17.0 is required for the recorded PDF workflow. This saved-results
build is distinct from recomputing the original experiments. Exact-input
restoration and `--full` archived-source replay are documented in the
[reproduction guide](docs/publication/REPRODUCE.md).

## Offline Kaggle review

The executable notebook reviews the preserved results, validates release hashes
and plots saved paths without network access or exchange credentials. It
records the actual platform runtime; it does not claim a fresh frozen replay.
Upload the prepared release ZIP as a Kaggle dataset and attach it to the
notebook, following [the platform instructions](docs/KAGGLE.md).
The notebook explains the question, inputs, methods, key findings, limitations
and citation, and links to the bundled manuscript and full reproduction guide.

## Data, evidence and release scope

Raw/normalized exchange candles, virtual environments, credentials and runtime
state are excluded. Four pinned input manifests identify separately restored
market inputs. Source snapshots and accepted result collections retain their
original hashes; repeated replay creates no new independent market evidence.
Protocol freezes are local records, not externally witnessed preregistrations.

The public tree is built from an explicit allowlist. Superseded PDFs, internal
working records, older submission archives and temporary files remain local.
The generated `PUBLICATION-RELEASE.json` inventories every delivered public
file and anchors the three scientific registries. Local archive/notebook checks
are separate from remote GitHub CI and execution on Kaggle's hosted service.

## Rights

Original software is [MIT licensed](LICENSE). Original paper text and synthetic
material are [CC BY 4.0](LICENSE-PAPER.md). Binance-derived market material has an
explicit CC BY-NC-SA 4.0 exception, with Bitstamp attribution where applicable;
see [THIRD_PARTY.md](THIRD_PARTY.md). A mixed Kaggle dataset must retain those
component rights rather than relabeling every file as MIT or CC0.

## AI assistance and responsibility

OpenAI Codex was used for literature research, experimental design, code
preparation and testing, statistical analysis, interpretation, figure generation,
manuscript drafting and revision, and reproducibility and release checks.
Exact model versions were not consistently recorded. The human author retains
responsibility for the final work. Automated checks and AI-assisted reviews are
not independent human peer review or evidence of completed human-author review.
