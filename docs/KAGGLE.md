# Public Kaggle saved-results review

Use the [research dataset, Version 2](https://www.kaggle.com/datasets/abdullah2hamza/quant-cost-aware-bitcoin-research)
and [public notebook, tested Version 2](https://www.kaggle.com/code/abdullah2hamza/quant-bitcoin-synthetic-evidence-release-audit?scriptVersionId=363526570).
Owner: abdullah2hamza. Source release: [v1.0.1](https://github.com/abdullah2hamza-blip/Quant/releases/tag/v1.0.1),
commit 7f847ff354e6cadb1c46fe9e0cb4d122842f4ed2. Final notebook source is
`kaggle/hosted_review.ipynb`; its original code/text/synthetic displays are the
separately authorized Apache-2.0 wrapper. The embedded viewer's MIT notice is
retained. The mixed-rights dataset uses Other, retaining original MIT/CC BY 4.0
and Binance-derived CC BY-NC-SA4.0/provider-term exceptions. The paper remains
CC BY 4.0, subject to its stated component exceptions.

## Run on Kaggle

Copy/edit the public notebook or import `kaggle/hosted_review.ipynb`. Attach
Dataset Version 2 with Add Input, keep Internet off and accelerator None, then
Save & Run All in a fresh session. No dependency installation, broker account or
credentials are needed. The input selector requires exactly one
`quant-research-release-v5.zip.bin`. This is the exact canonical ZIP with SHA-256
`95333cb8f4d81daefc82c9d08e97eeeb191808091a528d67128023123cfba429`.
Python zipfile reads it without renaming; rename a downloaded copy to `.zip`
for a desktop archive tool. Ordinary ZIP uploads recursively expanded the nested
source capsules on Kaggle and correctly failed the first private integrity check.

The unchanged embedded viewer verifies 414 inventory entries and registry anchors,
reads saved 216/250/270/40-row study tables and checks the primary fixed/adaptive
path identity in temporary scratch. The wrapper then removes scratch and leaves
exactly five files in `/kaggle/working/quant-synthetic-review`: baseline.csv,
followup.csv, saved-baseline-power.png, ATTRIBUTION.md and review-summary.json.
Use the notebook Output tab for downloads. Market files/plots and the manuscript
are accessed through the separately licensed dataset/GitHub assets, rather than
being redistributed as Apache notebook outputs. Earlier full-output audit
versions remain private in a separate notebook.

The tested public Version 2 (script 363526570) ran all three cells in 36.8 seconds.
Actual runtime: Python 3.13.15, NumPy 2.1.3, Matplotlib 3.10.0, CPU, Internet off.
The pinned Kaggle container is
`gcr.io/kaggle-images/python@sha256:17b2fc7f27c25c6c2fd4230ec8e66097ab2b89fc88e1e4d6f338b72e1ee0bc3e`.
Future copied sessions may use a different environment; the receipt reports the
observed versions. This review does not generate fresh worlds, acquire candles,
audit raw inputs or rerun the full numerical experiments. Matching recorded
scientific Python 3.13.7/NumPy 2.5.4 alone would not establish an exact replay.

## Local full-output review

The original local launcher and base notebook remain available for inspection
under their original terms. From a locked research environment:

```sh
uv run --locked python scripts/kaggle_review.py --archive output/release-v5/quant-research-release-v5.zip --output runs/kaggle-local-review
```

Download the research ZIP from the GitHub Release first, or pass an extracted
release using `--root`. Choose a new output directory outside the source on each
run. `QUANT_REVIEW_ARCHIVE`, `QUANT_REVIEW_ROOT`, `QUANT_REVIEW_INPUT_ROOT` and
`QUANT_REVIEW_OUTPUT` can select explicit paths. The original launcher emits
mixed-rights market displays as well as synthetic displays, so those full-output
versions were not published as Apache notebooks. `kaggle/prepare_metadata.py`
retains the original private staging workflow and performs no authentication or
upload; the separately versioned hosted wrapper is the final public entry point.

The launcher checks inventory hashes, bounds sizes, and rejects unsafe paths,
case aliases, symlinks, encrypted archives and prefix collisions. It leaves
inputs unchanged. Integrity hashes are not a digital publisher signature.
`transport-provenance.json` in Dataset V2 records the earlier transport/private
wrapper at creation; final public wrapper identity and hosted/access checks are
in the GitHub Release's `publication-verification.json` and `SHA256SUMS`.

## Research, limits and citation

The notebook explains the paired-cost/nuisance question, established methods,
conditional simulations, negative/imprecise retrospective Bitcoin findings,
exploratory daily-bot contrasts and component rights. It links to the manuscript,
citation and [full reproduction instructions](publication/REPRODUCE.md).
No new general theorem, prospective trading edge, DOI, independent human peer
review or journal acceptance is claimed. See [STATUS.md](publication/STATUS.md).

OpenAI Codex was used for literature research, experimental design, code
preparation and testing, statistical analysis, interpretation, figure generation,
manuscript drafting and revision, and reproducibility and release checks.
Exact model versions were not consistently recorded. The human author retains
responsibility for the final work. Automated checks and AI-assisted reviews are
not independent human peer review or evidence of completed human-author review.


## Official platform references

- [Notebook environments and versions](https://www.kaggle.com/docs/notebooks)
- [Kernel metadata](https://github.com/Kaggle/kaggle-cli/blob/main/docs/kernels_metadata.md)
- [Dataset metadata/licenses](https://github.com/Kaggle/kaggle-cli/blob/main/docs/datasets_metadata.md)
- [Kernel commands](https://github.com/Kaggle/kaggle-cli/blob/main/docs/kernels.md)
- [Dataset commands](https://github.com/Kaggle/kaggle-cli/blob/main/docs/datasets.md)
