"""Prepare local Kaggle upload folders; never authenticate, upload or run a kernel."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import sys
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[1]
ARCHIVE_NAME = "quant-research-release-v5.zip"
DATASET_SLUG = "quant-cost-aware-bitcoin-research"
KERNEL_TITLE = "Quant Saved Results Research Review"
KERNEL_SLUG = "quant-saved-results-research-review"
REPORT_TITLE = "Cost Uncertainty in Sequential Strategy Validation: A Diagnostic Study with Adaptive Bitcoin Trend Following"
REPORT_VERSION = "v1.0.1"
REPOSITORY_URL = "https://github.com/abdullah2hamza-blip/Quant"
REPRODUCTION_URL = REPOSITORY_URL + "/blob/main/docs/publication/REPRODUCE.md"
MANUSCRIPT_PATH = "output/pdf/cost-aware-bitcoin-research-v5.pdf"
AI_DISCLOSURE = (
    "OpenAI Codex was used for literature research, experimental design, code preparation and testing, "
    "statistical analysis, interpretation, figure generation, manuscript drafting and revision, and "
    "reproducibility and release checks. Exact model versions were not consistently recorded. "
    "The human author retains responsibility for the final work. Automated checks and AI-assisted "
    "reviews are not independent human peer review or evidence of completed human-author review."
)


def research_overview() -> str:
    return ("## Research question and inputs\n\n"
        "How much evidence is lost when sequential strategy validation ignores shared execution-cost "
        "structure, or treats a stationary cost coefficient as though it could change adversarially each period? "
        "The preserved study contains 24 baseline and 25 separately specified follow-up synthetic cases, "
        "with 4,000 independent worlds within each case and an 800-step horizon. Streams and some factorial "
        "cells are dependent. The retrospective market study has six cases, nine portfolios and five assumed "
        "cost levels, plus a separately dated exploratory daily-bot comparison. Raw and normalized vendor "
        "candles are not distributed in this companion.\n\n"
        "## Method and key recorded findings\n\n"
        "The synthetic comparisons use established bounded betting and empirical-Bernstein constructions, "
        "shared versus separate cost bounds, adaptive stakes and whole-history nuisance profiling. Fixed "
        "mixtures and adaptive betting have different null scopes. The market books use prior-close signals, "
        "next-open self-financing accounting, inherited holdings and modeled traded-notional costs.\n\n"
        "At effect 0.05 with equal turnover in the baseline bounded experiment, joint and separate "
        "first-stream powers were 92.425% and 0.025%. That controlled finding is not a market edge. "
        "At 25 bps per traded side, the primary January 2025–October 2026 fixed and adaptive four-hour "
        "EMA paths both returned 2.6067%, with no evaluation-window switches. Hourly/daily adaptive "
        "differences were negative and imprecise. Both central matched-settings daily-bot contrast intervals "
        "include zero. No new general theorem or demonstrated adaptive trading edge is claimed.\n\n"
        "## Limits\n\n"
        "Bounded-model sequential guarantees require the stated information and calibration assumptions; "
        "they are not transferred to OHLCV returns. Market costs are scenarios, not calibrated live fills. "
        "The same Bitcoin history underlies cross-venue checks, bootstrap intervals are approximate and "
        "unadjusted, and the later daily-bot contrast is post-outcome exploratory. No capacity, latency, "
        "authenticated-fill or prospective-profitability result is established. This notebook inspects saved "
        "records and does not rerun the original experiments.\n")


def notebook(source: str) -> dict:
    """Embed the launcher: a pushed notebook cannot depend on adjacent .py files."""
    def cell(kind, content):
        result = {"cell_type": kind, "id": kind[0] + "-" + hashlib.sha256(content.encode()).hexdigest()[:12],
                  "metadata": {}, "source": content.splitlines(keepends=True)}
        if kind == "code":
            result.update(execution_count=None, outputs=[])
        return result
    configuration = '''import os
from pathlib import Path

# Optional explicit archive or extracted release root; otherwise discover one attached dataset.
ARCHIVE = os.environ.get("QUANT_REVIEW_ARCHIVE") or None
ROOT = os.environ.get("QUANT_REVIEW_ROOT") or None
INPUT_ROOT = os.environ.get("QUANT_REVIEW_INPUT_ROOT", "/kaggle/input")
OUTPUT = os.environ.get("QUANT_REVIEW_OUTPUT", "/kaggle/working/quant-review")
'''
    runner = ("# The exact launcher is embedded so this notebook is independently executable.\n"
              "LAUNCHER_SOURCE = " + repr(source) + "\n"
              "namespace = {'__name__': 'quant_saved_results_review', '__file__': 'embedded_kaggle_review.py'}\n"
              "exec(compile(LAUNCHER_SOURCE, 'embedded_kaggle_review.py', 'exec'), namespace)\n"
              "summary = namespace['review'](archive=ARCHIVE, root=ROOT, input_root=INPUT_ROOT, output=OUTPUT)\n"
              "import json\nprint(json.dumps(summary, indent=2))\n")
    display = '''try:
    from IPython.display import FileLink, Image, display
except ImportError:
    print("Figures:", summary["figures"])
else:
    for relative in summary["figures"]:
        display(Image(filename=str(Path(OUTPUT) / relative)))
    release_root = Path(OUTPUT) / "release" if summary["source_kind"] == "archive" else Path(summary["source"])
    linked_files = sorted((release_root / "output/pdf").glob("*.pdf"))
    linked_files += [release_root / "docs/publication/REPRODUCE.md", release_root / "CITATION.cff"]
    for path in linked_files:
        if path.is_file():
            display(FileLink(str(path)))
'''
    return {
        "nbformat": 4, "nbformat_minor": 5,
        "metadata": {"kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
                     "language_info": {"name": "python"}},
        "cells": [
            cell("markdown", "# Quant: saved-results research review\n\n"
                 "Attach the prepared research-release dataset, keep Internet and GPU off, and run all cells. "
                 "This notebook verifies the release inventory and inspects saved records; it does not generate new "
                 "worlds, download candles, audit raw inputs or rerun the frozen study. A preserved historical "
                 "path identity does not prove future profitability.\n\n"
                 "Original software is MIT; original prose and synthetic displays are CC BY 4.0. "
                 "Binance-derived market plots/results retain Binance Vision attribution, CC BY-NC-SA 4.0 "
                 "and provider terms; see the attached release's THIRD_PARTY.md.\n"),
            cell("markdown", research_overview()),
            cell("markdown", "## AI assistance and responsibility\n\n" + AI_DISCLOSURE + "\n"),
            cell("code", configuration),
            cell("code", runner),
            cell("code", display),
            cell("markdown", "## What this execution establishes\n\n"
                 "The output directory contains a source/hash/runtime receipt, copied scientific CSVs and plots "
                 "of saved records. NumPy/Matplotlib versions are reported as observed. Matching the recorded "
                 "Python 3.13.7 and NumPy 2.5.4 versions alone is insufficient for exact replay, which additionally "
                 "requires the locked environment, archived sources and exact permitted inputs. The full "
                 "reproduction workflow is documented in the release. No broker account or credentials are used.\n\n"
                 "## Citation and full reproduction\n\n"
                 "Abdullah Hamza (2026). *" + REPORT_TITLE + "*. Technical report; public release "
                 + REPORT_VERSION + " is being prepared. No DOI, journal acceptance or independent human peer review "
                 "is claimed. Hosting and final platform versions must be confirmed in the publication record.\n\n"
                 "The manuscript, citation file and full reproduction guide are linked from the execution output "
                 "above, using files inside the attached release. Canonical source locations are the "
                 "[Quant repository](" + REPOSITORY_URL + ") and "
                 "[full reproduction guide](" + REPRODUCTION_URL + "). These canonical paths are not "
                 "a claim that public hosting has already been verified. Full instructions distinguish integrity "
                 "checks, saved-results paper builds, exact-input restoration and archived-source replay.\n"),
        ],
    }


def write_notebook(path: Path):
    source = (ROOT / "scripts/kaggle_review.py").read_text(encoding="utf-8")
    path.write_text(json.dumps(notebook(source), indent=1, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")


def prepare(*, archive: Path, output: Path, owner: str | None = None) -> dict:
    owner = owner or os.environ.get("KAGGLE_USERNAME")
    if not owner or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{1,49}", owner):
        raise ValueError("Provide your actual Kaggle username using --owner or KAGGLE_USERNAME; GitHub identity is not inferred")
    if output.exists():
        raise ValueError("Choose a new metadata output directory")
    spec = importlib.util.spec_from_file_location("quant_release_viewer", ROOT / "scripts/kaggle_review.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    manifest = module.verify_archive(archive)
    archive_hash = module.sha256(archive)
    dataset = output / "dataset"
    kernel = output / "kernel"
    dataset.mkdir(parents=True)
    kernel.mkdir()
    shutil.copyfile(archive, dataset / ARCHIVE_NAME)
    if module.sha256(dataset / ARCHIVE_NAME) != archive_hash:
        raise ValueError("Release changed while preparing Kaggle metadata")
    module.verify_archive(dataset / ARCHIVE_NAME)
    description = ("# Quant cost-aware Bitcoin research\n\nTechnical report " + REPORT_VERSION +
        " is being prepared for public release. Final hosting, release commit/tag and hosted notebook versions "
        "are not yet verified by this metadata.\n\n" + research_overview() + "\n"
        "## Rights and reproducibility\n\nThis is a mixed-rights research companion: "
        "original code MIT, original prose/synthetic displays CC BY4.0, Binance-derived market outputs CC BY-NC-SA4.0 "
        "with Binance Vision attribution and provider terms. See THIRD_PARTY.md and LICENSE-PAPER.md. "
        "The saved-results notebook does not perform a fresh numerical replay or prove profitability.\n\n"
        "## AI assistance and responsibility\n\n" + AI_DISCLOSURE + "\n\n"
        "## Citation and source\n\nAbdullah Hamza (2026), *" + REPORT_TITLE + "*. Technical report "
        + REPORT_VERSION + " in preparation; no DOI or peer-reviewed publication status asserted. "
        "The bundled CITATION.cff supplies machine-readable citation details. Canonical repository: "
        + REPOSITORY_URL + ". Full reproduction guide: " + REPRODUCTION_URL +
        ". Public accessibility and final cross-platform URLs are recorded only after verification.")
    metadata = {"title": "Quant Cost-Aware Bitcoin Research", "subtitle": "Saved research outputs and auditable source, without vendor candles",
        "id": f"{owner}/{DATASET_SLUG}", "licenses": [{"name": "other"}], "description": description,
        "keywords": ["finance", "time series", "statistics", "research"],
        "resources": [{"path": ARCHIVE_NAME, "description": "Manifest-bound source/results release, paper sources, figures, controls and reproduction guide; no vendor candles"}]}
    if MANUSCRIPT_PATH in manifest["files"]:
        with ZipFile(archive) as release:
            pdf_payload = release.read(MANUSCRIPT_PATH)
        expected = manifest["files"][MANUSCRIPT_PATH]
        if len(pdf_payload) != expected["bytes"] or hashlib.sha256(pdf_payload).hexdigest() != expected["sha256"]:
            raise ValueError("Manuscript bytes changed while preparing Kaggle metadata")
        pdf_name = Path(MANUSCRIPT_PATH).name
        (dataset / pdf_name).write_bytes(pdf_payload)
        metadata["resources"].append({"path": pdf_name, "description": "Named technical report with methods, proofs, results, uncertainty, limitations and AI assistance disclosure"})
    (dataset / "dataset-metadata.json").write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8", newline="\n")
    for name in ("LICENSE", "LICENSE-PAPER.md", "THIRD_PARTY.md"):
        shutil.copyfile(ROOT / name, dataset / name)
    (dataset / "README.md").write_text("# Research companion\n\n" + description + "\n\n"
        "Attach this dataset to the separate notebook. Do not treat its component-specific rights as MIT/CC0 "
        "for the whole dataset. Dataset metadata is prepared locally; no upload or account validation has run.\n", encoding="utf-8", newline="\n")
    write_notebook(kernel / "review_saved_results.ipynb")
    kernel_metadata = {"id": f"{owner}/{KERNEL_SLUG}", "title": KERNEL_TITLE,
        "code_file": "review_saved_results.ipynb", "language": "python", "kernel_type": "notebook",
        "is_private": True, "enable_gpu": False, "enable_internet": False,
        "dataset_sources": [metadata["id"]], "competition_sources": [], "kernel_sources": [], "model_sources": []}
    (kernel / "kernel-metadata.json").write_text(json.dumps(kernel_metadata, indent=2) + "\n", encoding="utf-8", newline="\n")
    (kernel / "README.md").write_text("# Prepared notebook\n\nUpload/import the notebook and attach the companion dataset. "
        "Metadata is private/offline/CPU by default. All code is embedded in the notebook. "
        "No Kaggle upload, account check or hosted execution has been performed.\n", encoding="utf-8", newline="\n")
    return {"status": "prepared locally; not uploaded", "owner_supplied_not_verified": owner,
            "dataset": str(dataset.resolve()), "kernel": str(kernel.resolve()),
            "archive_sha256": module.sha256(dataset / ARCHIVE_NAME)}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--owner", help="Actual Kaggle account slug; alternatively KAGGLE_USERNAME")
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        result = prepare(archive=args.archive, output=args.output, owner=args.owner)
    except (ValueError, OSError) as error:
        print(f"{type(error).__name__}: {error}", file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
