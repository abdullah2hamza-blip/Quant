# Technical report release v1.0.1

The public-release candidate pairs a disclosed manuscript (artifact revision v5)
with the complete distributable research companion. Publication here means a
public technical report and software/results release; no external peer review,
journal acceptance or DOI is claimed. Live publication and hosted-run status
are recorded in the release verification receipt after those actions occur.

The private v1.0.0 preparation tag is preserved. Actual GitHub execution found
two CI setup defects: an absent parent for a custom pytest temporary directory,
and the moving Ubuntu image lacking Python 3.13.7 binaries. The patch uses
pytest's default temporary directory and pins Ubuntu 24.04 / Windows 2025.
It changes release setup and metadata, with no change to scientific algorithms,
accepted result registries or manuscript claims.

The contribution is a controlled diagnosis of paired-cost and temporal-nuisance
information loss with established sequential methods. It retains a negative
adaptive EMA Bitcoin result and a separately dated exploratory daily-bot
comparison. The mathematical assumptions, unsuccessful controls, assumed-cost
sensitivities and short-window uncertainty limits remain visible.

Changes since the local v3 preparation are explicit AI-assistance disclosures,
claim-to-evidence and dataset documentation, release/citation metadata, fuller
Kaggle explanations, and publication packaging. The accepted scientific
registries, source freezes and substantive results are preserved. Current
documentation/release source differs from the frozen result-producing source;
the exact archived-source replay route is retained rather than silently
substituting current code for past computations.

The public file list is `PUBLICATION-RELEASE.json`. The final tagged-revision
asset manifest supplies the tag/commit and archive/PDF checksums without
inventorying its own digest. Raw/normalized provider candles, environments,
caches, credentials, unrelated work and private review histories are excluded.

Verification categories are separate: source inspection; regression tests;
24/25-case smoke runs; direct analysis of saved outcomes; display/manuscript
rebuilds; and traceable prior full replay. Actual counts, runtimes and result
identities belong in the validation receipt. Kaggle executes a useful offline
saved-results review, not the full frozen study. Hosted execution and public
access are separate gates and are never inferred from a local test.

Reproduction begins with `REPRODUCE.md`; claims and their exact evidence are in
`CLAIM-EVIDENCE.md`; component rights and data scope are in `DATASET-CARD.md`,
`LICENSE-PAPER.md` and `THIRD_PARTY.md`. Cite the report using `CITATION.cff`.
