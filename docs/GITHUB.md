# GitHub technical report release

The existing repository is `abdullah2hamza-blip/Quant`; do not substitute a new
repository. The proposed release tag is v1.0.0; verify that it is unused before
creation. Hosting is not journal acceptance or human peer review.

Use the generated `output/release-v4/github` tree as the explicit public file
set. `PUBLICATION-RELEASE.json` inventories its bytes and scientific registry
anchors. The release builder rejects unsafe paths, raw vendor candle CSVs,
private-key/token patterns and files exceeding GitHub's 100 MiB regular-file
limit. It preserves the accepted studies and their frozen source ZIPs.

The root ignore rules exclude raw data, credentials, runtime state, superseded
PDFs and older submission archives. Four pinned data manifests are included.
Individual scientific NPZ files fit regular Git; no Git LFS pointer replaces a
required result. The roughly 300 MB replication ZIP belongs in a GitHub Release
asset or a separately licensed dataset, rather than regular Git history.

Before committing, compare the staged paths and bytes to the generated
allowlist. Use the verified current manuscript, code, tests, protocols and
accepted results; leave internal review histories and old local distributions
outside the public tree. Do not use an unreviewed recursive add of every local
artifact. The existing remote is the author's Quant repository; preparation
does not assert that its scaffold revision already contains this release.

The included Actions workflows run locked dependencies, research regression
checks, both smoke studies, and the bot doctor/tests on Windows and Linux.
Local execution is recorded separately from actual remote CI status. Pushing,
creating a release and public deposition are subsequent publishing actions;
the current task authorizes them after the appropriate checks. Before changing
visibility, review accessible history, branches/tags, release assets, Actions
logs/artifacts and other exposed repository surfaces. A clean latest tree alone
does not clear old content. Preserve history; destructive rewriting or credential
rotation requires separate instructions if an actual exposure is discovered.

Release assets must be built from and bound to the actual clean tagged commit.
Record artifact checksums without circular self-hashes. Verify the final public
repository/release and downloads without relying solely on the owner's session,
and use the actual tested Kaggle dataset/notebook versions for cross-links.
No successful remote run, public transition or hosting is asserted here until
the publication record provides its observed evidence.

See the final release validation receipt for exact current artifacts and
executed checks, and [KAGGLE.md](KAGGLE.md) for the separate notebook route.
