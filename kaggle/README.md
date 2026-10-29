# Local Kaggle entry point

`review_saved_results.ipynb` embeds the offline saved-results launcher.
Attach the public `quant-research-release-v3.zip` dataset and run all cells with
Internet and GPU disabled. Explicit source/output settings are in the first
code cell. It does not perform a fresh frozen numerical replay.

`prepare_metadata.py` stages optional upload metadata only when an actual Kaggle
owner is supplied explicitly or via the username-only KAGGLE_USERNAME setting.
It does not authenticate, upload or start a kernel. See `docs/KAGGLE.md` for the
UI route, local command, runtime limits, rights and execution scope.
