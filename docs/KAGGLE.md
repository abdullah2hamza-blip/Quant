# Kaggle technical report and saved-results review

The canonical resources are the [research dataset](https://www.kaggle.com/datasets/abdullah2hamza/quant-cost-aware-bitcoin-research)
and [public Apache notebook](https://www.kaggle.com/code/abdullah2hamza/quant-bitcoin-synthetic-evidence-release-audit).
Owner: abdullah2hamza. This disclosure-only source release is
[v1.0.2](https://github.com/abdullah2hamza-blip/Quant/releases/tag/v1.0.2), artifact
revision v6. The final source commit, public dataset/notebook versions and actual
execution outcome are recorded in the release manifest and publication receipt.
Prior v1.0.1 assets remain available as immutable historical versions.

Verified hosted release: Dataset Version 3 and Notebook Version 3, script
`363616953`. Fresh Save & Run All succeeded in 31.9 seconds with Internet off and
no accelerator. All 417 payload files verified; the public source's seven cells
match the tagged wrapper. Anonymous PDF and full research-bundle downloads match
the prepared bytes. See the GitHub Release publication-verification.json and
hosted-review-summary.json for evidence and exact hashes.

## Run the real saved-results implementation

Copy/edit the public notebook or import `kaggle/hosted_review.ipynb`. Attach the
companion's Version 3 for v1.0.2; retain Internet off and accelerator None.
Choose Save & Run All for a fresh session. No dependency installation, API keys,
exchange account or paid accelerator is required. The first cell selects exactly
one `quant-research-release-v6.zip.bin` under `/kaggle/input`.

This is the canonical research ZIP with a byte-preserving suffix: Kaggle expands
ordinary ZIP uploads recursively and would remove the nested frozen source ZIPs.
Python zipfile reads the .zip.bin directly; a desktop reader can rename a
copy to .zip. Compare the reported archive digest with SHA256SUMS on the GitHub
Release. The input is verified against its internal PUBLICATION-RELEASE.json;
matching internal hashes alone is not a digital publisher signature.

The embedded `scripts/kaggle_review.py` implementation is unchanged. It verifies
the entire inventory and three scientific registry anchors, reads accepted
216/250/270/40-row tables and checks preserved primary fixed/adaptive path
identity in temporary scratch. The hosted wrapper then removes scratch and
publishes exactly five files in `/kaggle/working/quant-synthetic-review`:
ATTRIBUTION.md, baseline.csv, followup.csv, review-summary.json and
saved-baseline-power.png. Use Kaggle's Output tab to download them.

Only the separately authorized wrapper's original code/text/synthetic displays
are Apache-2.0, with the embedded viewer's MIT notice retained. Original repository
code remains MIT; the paper is CC BY 4.0 subject to component exceptions. The
mixed-rights input dataset uses Other and retains Binance-derived CC BY-NC-SA
4.0 and provider terms plus Bitstamp attribution/terms. Market plots/files and
the manuscript are accessed through that separately licensed dataset and GitHub
assets, rather than being redistributed as Apache notebook outputs. The earlier
full-output audit notebook remains private in its separate resource.

## Scope and recorded environment

This is an executable saved-record review, not a fresh full experiment. It does
not generate new Monte Carlo worlds, fetch candles, audit raw inputs, rerun the
full frozen study or place orders. Historical path identity does not establish
future equality or profitability. The locked scientific environment is Python
3.13.7 / NumPy 2.5.4. Kaggle's verified Version 3 run used Python 3.13.15 / NumPy 2.1.3 /
Matplotlib 3.10.0; the receipt records its actual versions and container. Matching
key versions alone would not prove exact replay. See
[full reproduction instructions](publication/REPRODUCE.md) for archived-source
replay and separately restored permitted inputs.

The source includes the research question, controlled methods, conditional
synthetic findings, negative/imprecise Bitcoin results, retrospective/exploratory
limits, citation and full AI disclosure. The manuscript itself is included in
the dataset, along with source, results, configurations, figures and acquisition
manifests. No model weights exist in this project and no model resource is needed.
Hosting is a technical-report release; no DOI, journal acceptance or human peer
review is asserted.

## Local full-output review

Download the research ZIP from the GitHub Release and use a new output directory:

```sh
uv run --locked python scripts/kaggle_review.py --archive output/release-v6/quant-research-release-v6.zip --output runs/kaggle-local-review
```

An extracted inventory-bound tree can be passed with --root. The environment
variables QUANT_REVIEW_ARCHIVE, QUANT_REVIEW_ROOT, QUANT_REVIEW_INPUT_ROOT and
QUANT_REVIEW_OUTPUT select explicit paths. The original local launcher/base
notebook emits mixed-rights market displays too; use the Apache hosted wrapper
for public Kaggle output. `kaggle/prepare_metadata.py` is a private/local staging
helper, not an uploader or a claim that its metadata has been published.

## AI assistance and responsibility

Artificial intelligence (AI) tools were used for manuscript editing and code preparation. OpenAI Codex was used for literature research, experimental design, code preparation and testing, statistical analysis, interpretation, figure generation, manuscript drafting and revision, and reproducibility and release checks. Exact model versions were not consistently recorded. The human author retains responsibility for the final work. Automated checks and AI-assisted reviews are not independent human peer review or evidence of completed human-author review.

## Official platform references

- [Notebook versions and environment](https://www.kaggle.com/docs/notebooks)
- [Kernel metadata](https://github.com/Kaggle/kaggle-cli/blob/main/docs/kernels_metadata.md)
- [Dataset metadata/licenses](https://github.com/Kaggle/kaggle-cli/blob/main/docs/datasets_metadata.md)
- [Kernel commands](https://github.com/Kaggle/kaggle-cli/blob/main/docs/kernels.md)
- [Dataset commands](https://github.com/Kaggle/kaggle-cli/blob/main/docs/datasets.md)
