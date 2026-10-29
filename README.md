# Cost-aware Bitcoin trend research

A reproducible diagnostic study of sequential strategy validation under uncertain
execution costs, with an audited Bitcoin trend-following application and a
separate operational simulation bot. The statistical constructions use
established methods; no new general theorem or demonstrated adaptive trading
edge is claimed.

The current manuscript is [the technical report](output/pdf/cost-aware-bitcoin-research-v6.pdf).
The [research overview](docs/publication/README.md),
[reproduction guide](docs/publication/REPRODUCE.md),
[GitHub release guide](docs/GITHUB.md), and [Kaggle guide](docs/KAGGLE.md)
explain the scientific and platform scopes.

This disclosure-only update is prepared as **[v1.0.2](https://github.com/abdullah2hamza-blip/Quant/releases/tag/v1.0.2)**.
It adds the requested explicit manuscript-editing/code-preparation sentence while
preserving the broader AI disclosure, human authorship and accepted science.
The immutable source commit is resolved by the release tag and manifest.
The existing [Kaggle dataset](https://www.kaggle.com/datasets/abdullah2hamza/quant-cost-aware-bitcoin-research)
and [public notebook](https://www.kaggle.com/code/abdullah2hamza/quant-bitcoin-synthetic-evidence-release-audit)
will receive new versions. Current hosting and fresh execution evidence are
recorded in the release's publication-verification.json after actual completion.
The prior v1.0.1 release is preserved. Hosting is not journal acceptance or
independent human peer review.

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

The [hosted wrapper](kaggle/hosted_review.ipynb) verifies the full released
inventory and saved primary-path identity in temporary scratch. It publishes
only two synthetic tables, one synthetic figure, attribution and an integrity
receipt. It does not perform a fresh frozen experiment. Attach Dataset Version 3,
keep Internet off and accelerator None, and use Kaggle's Output tab for downloads.

Kaggle recursively expands nested ZIPs: the dataset therefore supplies the exact
canonical research ZIP as `.zip.bin`; compare its observed digest with the
release SHA256SUMS.
The prior hosted runtime was Python 3.13.15 / NumPy 2.1.3 / Matplotlib 3.10.0; the new receipt reports the observed environment.
this differs from the recorded scientific runtime. See [Kaggle instructions](docs/KAGGLE.md)
and [wrapper provenance and rights](kaggle/HOSTED-REVIEW.md).

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

Original repository software is [MIT licensed](LICENSE), with the separately
authorized hosted wrapper [Apache-2.0](kaggle/APACHE-2.0.txt). Its embedded viewer
retains its MIT notice. Original paper text and synthetic
material are [CC BY 4.0](LICENSE-PAPER.md). Binance-derived market material has an
explicit CC BY-NC-SA 4.0 exception, with Bitstamp attribution where applicable;
see [THIRD_PARTY.md](THIRD_PARTY.md). A mixed Kaggle dataset must retain those
component rights rather than relabeling every file as MIT or CC0.

## AI assistance and responsibility

Artificial intelligence (AI) tools were used for manuscript editing and code preparation.

OpenAI Codex was used for literature research, experimental design, code
preparation and testing, statistical analysis, interpretation, figure generation,
manuscript drafting and revision, and reproducibility and release checks.
Exact model versions were not consistently recorded. The human author retains
responsibility for the final work. Automated checks and AI-assisted reviews are
not independent human peer review or evidence of completed human-author review.
