# Kaggle technical report and saved-results review

The Kaggle entry point is an **offline review of preserved results**. It verifies
the public release manifest, reads recorded scientific CSVs, checks the primary
fixed/adaptive saved paths, and plots those saved records. It does not generate
new synthetic worlds, download vendor candles, audit raw inputs, place orders
or rerun the frozen numerical study. Historical path identity is not a claim
about future uncertainty or profitability.

The intended owner is `abdullah2hamza`, as supplied by the author. The technical
report is being prepared as public release v1.0.0; final asset URLs, versions,
public visibility and completed hosted execution are not yet established by
this guide. The existing GitHub identity is `abdullah2hamza-blip/Quant`.

## Local verification first

Use a new output directory on each run. From the repository root:

```sh
uv run --locked python scripts/kaggle_review.py --archive output/release-v4/quant-research-release-v4.zip --output runs/kaggle-local-review
```

The `--archive` path is the actual newly prepared public release ZIP, not the
superseded submission/private replication archive. An already extracted release
with its `PUBLICATION-RELEASE.json` can instead be passed with `--root`.
The output must be outside that source directory. Without either option, the
launcher discovers exactly one attached release under `--input-root`, default
`/kaggle/input`; multiple candidates require an explicit choice.

Output includes `review-summary.json`, two saved-result plots, copied scientific
CSV tables and attribution. The receipt records the actual Python, NumPy and
Matplotlib versions, the source archive/manifest hashes and scientific registry
anchors. It always says that a fresh numerical replay was not performed.

The frozen studies used Python 3.13.7 and NumPy 2.5.4. A different installed
runtime may inspect saved results, with that difference recorded. The optional
`--require-recorded-runtime` rejects mismatched key versions; matching them is
only a necessary runtime check, not evidence that a replay ran. Exact replay
also needs the locked dependencies, archived source and permitted exact inputs;
use [the full reproduction guide](publication/REPRODUCE.md).

## Kaggle UI route

The current task authorizes the Kaggle release after checks pass. The staging
helper itself performs no authentication, upload or hosted execution. Inspect
the signed-in owner and existing project assets first; version the matching
asset rather than creating a duplicate. Stage privately where practical and
record the exact final public dataset/notebook versions after execution.

1. Create or update the matching Kaggle Dataset with the prepared public release ZIP. Keep its
   byte identity. Include the accompanying `THIRD_PARTY.md`, `LICENSE-PAPER.md`
   and attribution text. Select **Other** for the mixed-rights dataset license
   and put the component rights in its description; do not label the whole
   collection MIT, CC0 or unrestricted commercial data.
2. Create/import a notebook using `kaggle/review_saved_results.ipynb`. Attach
   that dataset through Add Input. Keep Internet and GPU disabled.
3. Run all cells. The notebook embeds the exact launcher, so it does not depend
   on a neighboring Python file being uploaded with the notebook. It finds the
   attached release or accepts explicit `ARCHIVE`/`ROOT` settings in its first
   code cell. Write output beneath `/kaggle/working`, not the attached input.
4. Start a fresh hosted run, monitor it to completion and inspect the actual
   logs, hash/runtime/scope receipt and figures. Quick Save or an upload alone
   is not successful execution. Confirm that the public notebook is the tested
   version and that unauthenticated readers can access its required inputs.

The notebook defaults to `/kaggle/working/quant-review`. Choose a new output
name when rerunning in the same session. The explicit paths can also be provided
through `QUANT_REVIEW_ARCHIVE`, `QUANT_REVIEW_ROOT`, `QUANT_REVIEW_INPUT_ROOT`
and `QUANT_REVIEW_OUTPUT`. It never reads API credentials. No account username
is needed for the offline review or the UI-upload route.

## Optional CLI metadata preparation

The owner is your actual **Kaggle** account slug; it is not inferred from GitHub:

```sh
uv run --locked python kaggle/prepare_metadata.py --owner abdullah2hamza --archive output/release-v4/quant-research-release-v4.zip --output runs/kaggle-upload-candidate
```

Alternatively set the username-only `KAGGLE_USERNAME` environment variable.
Missing/invalid ownership fails before staging. This helper creates:

- `dataset/`: the research ZIP, separately readable manuscript PDF when present,
  notices, dataset card and `dataset-metadata.json`.
- `kernel/`: a self-contained executable notebook and `kernel-metadata.json`.

The dataset metadata uses one `other` license entry with explicit component
rights. Kernel defaults are private, CPU and offline, with the supplied dataset
reference. Account existence/ownership is not checked remotely. Preparing these
files does not create a Kaggle object. The official CLI's dataset-create command
defaults to skipping subdirectories, so this staging puts the research archive
as an explicit root payload rather than relying on an implicit recursive upload.
The kernel-push command uploads **and runs** by default; the release workflow
must treat it as the authorized publishing/execution action, not as metadata
validation. The staging helper does not invoke it. Final public state and
cross-platform links must be checked after the actual publishing steps.

## Research narrative and disclosure

The notebook and dataset card explain the paired-cost research question,
synthetic and retrospective inputs, established methods, recorded findings,
limitations and citation. The notebook links to the bundled manuscript,
machine-readable citation and full reproduction guide from its execution
output. The canonical repository is linked as a source location; public
accessibility and final release URLs must be verified before they are reported
as hosted. No DOI, journal acceptance or independent human peer review is claimed.

OpenAI Codex was used for literature research, experimental design, code
preparation and testing, statistical analysis, interpretation, figure generation,
manuscript drafting and revision, and reproducibility and release checks.
Exact model versions were not consistently recorded. The human author retains
responsibility for the final work. Automated checks and AI-assisted reviews are
not independent human peer review or evidence of completed human-author review.

## Rights and portability

Original code is MIT; original prose and synthetic displays are CC BY 4.0.
Binance-derived market plots/results retain Binance Vision attribution,
CC BY-NC-SA 4.0 and applicable provider terms; Bitstamp material retains its
provider terms. No raw or normalized vendor candles are included in the public
profile. Copying a dataset to Kaggle does not enlarge any of these grants.

The launcher rejects unsafe paths, duplicate/case-aliased members, symlinks,
encrypted ZIP entries, file/directory collisions and inventory/hash mismatches
before extraction. It bounds declared sizes. It writes its own outputs only
beneath the configured output directory and leaves attached sources unchanged.
This is internal integrity checking, not a digital signature certifying an
unknown publisher. Compare the archive digest with the author's release receipt.

Kaggle's maintained image and preinstalled packages change. The official current
Dockerfile uses Python 3.13 paths, which does not guarantee the exact frozen
patch or NumPy version for any future notebook. The saved-results review avoids
altering the platform interpreter or installing packages into its environment.

## Official platform references checked 2026-10-28

- [Kernel metadata](https://github.com/Kaggle/kaggle-cli/blob/main/docs/kernels_metadata.md)
- [Dataset metadata and license identifiers](https://github.com/Kaggle/kaggle-cli/blob/main/docs/datasets_metadata.md)
- [Kernel commands](https://github.com/Kaggle/kaggle-cli/blob/main/docs/kernels.md)
- [Dataset commands and directory handling](https://github.com/Kaggle/kaggle-cli/blob/main/docs/datasets.md)
- [Kaggle notebook environment](https://www.kaggle.com/docs/notebooks)
- [Maintained Python image](https://github.com/Kaggle/docker-python/blob/main/Dockerfile.tmpl)
