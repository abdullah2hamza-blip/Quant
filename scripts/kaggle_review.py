"""Offline saved-results review for a manifest-bound public research release.

This entry point never downloads data, places orders, generates fresh worlds,
or represents saved-record inspection as a new frozen numerical replay.
"""
from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import hashlib
import io
import json
import math
import os
from pathlib import Path
import platform
import re
import stat
import sys
from zipfile import BadZipFile, ZipFile

sys.dont_write_bytecode = True

MANIFEST = "PUBLICATION-RELEASE.json"
MAX_MANIFEST_BYTES = 10 * 1024**2
MAX_FILES = 10_000
MAX_FILE_BYTES = 256 * 1024**2
MAX_TOTAL_BYTES = 2 * 1024**3
RECORDED_RUNTIME = {"python": "3.13.7", "numpy": "2.5.4"}
CSV_FILES = {
    "baseline": "paper/generated/simulation-all-methods.csv",
    "followup": "paper/generated/followup/method-results.csv",
    "market": "paper/generated/market-all-policies-costs.csv",
    "bot_extension": "paper/generated/bot-extension/metrics.csv",
}
PRIMARY = "results/publication-v1/market/binance_primary_4h"
SCOPE = ("Offline inspection of preserved study records. No fresh Monte Carlo worlds, "
         "market data, raw-data audit, statistical discovery or numerical replay was performed. "
         "Historical path identity does not establish zero future uncertainty or profitability.")


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024**2), b""):
            h.update(chunk)
    return h.hexdigest()


def strict_json(payload: bytes):
    def object_pairs(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("Duplicate JSON key in release metadata: " + key)
            result[key] = value
        return result
    return json.loads(payload, object_pairs_hook=object_pairs)


def safe_name(name: str) -> bool:
    if not isinstance(name, str) or not name or name.startswith("/") or "\\" in name:
        return False
    reserved = {"CON", "PRN", "AUX", "NUL"}
    reserved.update(prefix + suffix for prefix in ("COM", "LPT") for suffix in "123456789¹²³")
    for part in name.split("/"):
        if (part in ("", ".", "..") or part.rstrip(" .") != part
                or any(ord(ch) < 32 or ch in '<>:"|?*' for ch in part)
                or part.split(".")[0].rstrip(" .").upper() in reserved):
            return False
    return True


def inventory(names):
    if len(names) > MAX_FILES or any(not safe_name(name) for name in names):
        raise ValueError("Unsafe path or excessive release inventory")
    folded = [name.casefold() for name in names]
    if len(set(folded)) != len(folded):
        raise ValueError("Duplicate or case-aliased release member")
    known = set(folded)
    for name in folded:
        parts = name.split("/")
        if any("/".join(parts[:i]) in known for i in range(1, len(parts))):
            raise ValueError("Release file/directory prefix collision")


def manifest_data(payload: bytes) -> dict:
    if len(payload) > MAX_MANIFEST_BYTES:
        raise ValueError("Release manifest is too large")
    manifest = strict_json(payload)
    if (not isinstance(manifest, dict) or type(manifest.get("schema_version")) is not int
            or manifest["schema_version"] != 1):
        raise ValueError("Unsupported public-release manifest")
    files = manifest.get("files")
    registries = manifest.get("scientific_registries")
    if not isinstance(files, dict) or not files or not isinstance(registries, dict) or not registries:
        raise ValueError("Release needs file inventory and scientific registry anchors")
    inventory([*files, MANIFEST])
    total = 0
    for name, record in files.items():
        if (not isinstance(record, dict) or type(record.get("bytes")) is not int
                or not 0 <= record["bytes"] <= MAX_FILE_BYTES
                or not isinstance(record.get("sha256"), str)
                or not re.fullmatch(r"[0-9a-f]{64}", record["sha256"])):
            raise ValueError("Invalid file size or digest in release manifest: " + name)
        total += record["bytes"]
    if total > MAX_TOTAL_BYTES:
        raise ValueError("Release exceeds the configured uncompressed size limit")
    for name, expected in registries.items():
        if name not in files or expected != files[name]["sha256"]:
            raise ValueError("Scientific registry anchor differs from the release inventory")
    return manifest


def verify_archive(archive: Path) -> dict:
    with ZipFile(archive) as zipped:
        names = zipped.namelist()
        inventory(names)
        if MANIFEST not in names or zipped.getinfo(MANIFEST).file_size > MAX_MANIFEST_BYTES:
            raise ValueError("Missing or oversized public-release manifest")
        manifest = manifest_data(zipped.read(MANIFEST))
        if set(names) != {*manifest["files"], MANIFEST}:
            raise ValueError("Archive inventory differs from the public-release manifest")
        for name in names:
            info = zipped.getinfo(name)
            if stat.S_ISLNK(info.external_attr >> 16) or info.flag_bits & 1:
                raise ValueError("Symlink or encrypted release member")
            if name == MANIFEST:
                continue
            expected = manifest["files"][name]
            if info.file_size != expected["bytes"]:
                raise ValueError("Release member size differs: " + name)
            h = hashlib.sha256()
            with zipped.open(info) as handle:
                for chunk in iter(lambda: handle.read(1024**2), b""):
                    h.update(chunk)
            if h.hexdigest() != expected["sha256"]:
                raise ValueError("Release member hash differs: " + name)
    return manifest


def contained_file(root: Path, name: str) -> Path:
    path = root / name
    if not path.resolve().is_relative_to(root.resolve()):
        raise ValueError("Release path escapes its source directory")
    for component in (path, *path.parents):
        if component == root.parent:
            break
        if component.is_symlink():
            raise ValueError("Symlink in release source directory")
    if not path.is_file() or not stat.S_ISREG(path.stat().st_mode):
        raise ValueError("Missing regular release file: " + name)
    return path


def verify_directory(root: Path) -> dict:
    metadata = contained_file(root, MANIFEST)
    if metadata.stat().st_size > MAX_MANIFEST_BYTES:
        raise ValueError("Release manifest is too large")
    manifest = manifest_data(metadata.read_bytes())
    for name, expected in manifest["files"].items():
        path = contained_file(root, name)
        if path.stat().st_size != expected["bytes"] or sha256(path) != expected["sha256"]:
            raise ValueError("Release source file differs: " + name)
    return manifest


def discover(input_root: Path) -> tuple[str, Path]:
    if not input_root.is_dir():
        raise ValueError("Attach the research dataset or provide --archive / --root explicitly")
    archives = sorted(input_root.rglob("quant-research-release-*.zip"))
    roots = sorted(p.parent for p in input_root.rglob(MANIFEST))
    candidates = [("archive", p) for p in archives] + [("root", p) for p in roots]
    if len(candidates) != 1:
        raise ValueError("Expected exactly one attached research release; select it with --archive or --root")
    return candidates[0]


def extract_verified(archive: Path, destination: Path, manifest: dict):
    destination.mkdir()
    with ZipFile(archive) as zipped:
        names = zipped.namelist()
        inventory(names)
        if set(names) != {*manifest["files"], MANIFEST}:
            raise ValueError("Release inventory changed during extraction")
        captured = zipped.read(MANIFEST)
        if manifest_data(captured) != manifest:
            raise ValueError("Release manifest changed between verification and extraction")
        for name in [*manifest["files"], MANIFEST]:
            info = zipped.getinfo(name)
            if stat.S_ISLNK(info.external_attr >> 16):
                raise ValueError("Release member became a symlink")
            payload = zipped.read(info)
            if name != MANIFEST:
                expected = manifest["files"][name]
                if len(payload) != expected["bytes"] or hashlib.sha256(payload).hexdigest() != expected["sha256"]:
                    raise ValueError("Release changed during extraction: " + name)
            target = destination / name
            if not target.resolve().is_relative_to(destination.resolve()):
                raise ValueError("Unsafe extraction destination")
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(payload)


def saved_tables(root: Path, manifest: dict) -> dict:
    tables = {}
    for name, relative in CSV_FILES.items():
        if relative not in manifest["files"]:
            raise ValueError("Missing scientific companion CSV: " + relative)
        with (root / relative).open(newline="", encoding="utf-8-sig") as handle:
            reader = csv.DictReader(handle)
            rows = list(reader)
            if not rows or not reader.fieldnames:
                raise ValueError("Empty scientific companion CSV: " + relative)
        tables[name] = rows
    return tables


def inspect_primary(root: Path, manifest: dict, np):
    for relative in (PRIMARY + "/report.json", PRIMARY + "/paths.npz"):
        if relative not in manifest["files"]:
            raise ValueError("Missing primary saved-path record: " + relative)
    report = strict_json((root / PRIMARY / "report.json").read_bytes())
    scenario = report["scenarios"]["25"]
    lines = {}
    with np.load(root / PRIMARY / "paths.npz", allow_pickle=False) as data:
        times = data["open_time_ms"]
        if (times.ndim != 1 or len(times) == 0 or not np.issubdtype(times.dtype, np.integer)
                or (np.diff(times) <= 0).any()):
            raise ValueError("Invalid saved primary timestamps")
        for policy in ("fixed", "adaptive", "buy_hold"):
            nav = data[f"cost25__{policy}__nav"]
            prior = float(scenario["initial_state"][policy]["nav"])
            if (nav.ndim != 1 or len(nav) != len(times) or not np.isfinite(nav).all()
                    or (nav <= 0).any() or not math.isfinite(prior) or prior <= 0):
                raise ValueError("Invalid primary saved path")
            rebased = nav / prior
            recorded = scenario["metrics"][policy]["total_return"]
            if not math.isclose(float(rebased[-1] - 1), recorded, rel_tol=1e-10, abs_tol=1e-12):
                raise ValueError("Primary saved path does not match its recorded return")
            lines[policy] = rebased.copy()
    difference = lines["adaptive"] - lines["fixed"]
    summary = {
        "case": "binance_primary_4h", "assumed_cost_bps_per_side": 25,
        "recorded_metrics": {name: scenario["metrics"][name] for name in lines},
        "fixed_adaptive_rebased_arrays_equal": bool(np.array_equal(lines["fixed"], lines["adaptive"])),
        "fixed_adaptive_rebased_max_abs_difference": float(np.max(np.abs(difference))),
        "scope": "Identity of these preserved historical paths; no claim about future equality or uncertainty",
    }
    return summary, times.copy(), lines


def plot_saved(output: Path, tables: dict, times, lines, np):
    import matplotlib
    matplotlib.use("Agg", force=True)
    from matplotlib.figure import Figure
    from matplotlib.backends.backend_agg import FigureCanvasAgg
    figures = output / "figures"
    figures.mkdir()
    fig = Figure(figsize=(9, 4.8), layout="constrained")
    FigureCanvasAgg(fig)
    ax = fig.subplots()
    for name, values in lines.items():
        ax.plot(times.astype("datetime64[ms]"), values, label=name,
                linestyle="--" if name == "adaptive" else "-")
    ax.set(title="Saved primary Bitcoin paths, modeled 25 bps per side",
           ylabel="Wealth / inherited prewindow wealth", xlabel="UTC date")
    ax.grid(alpha=.25); ax.legend()
    first = figures / "saved-market-paths.png"
    fig.savefig(first, dpi=160)

    rows = [r for r in tables["baseline"] if r.get("case") == "effect05_equal_turnover"]
    if not rows:
        raise ValueError("Missing prespecified baseline display case")
    fig = Figure(figsize=(10, 5.5), layout="constrained")
    FigureCanvasAgg(fig); ax = fig.subplots()
    values = [100 * float(r["first_stream_power"]) for r in rows]
    errors = [[v - 100 * float(r["first_stream_power_lower"]) for v, r in zip(values, rows)],
              [100 * float(r["first_stream_power_upper"]) - v for v, r in zip(values, rows)]]
    ax.errorbar(range(len(rows)), values, yerr=errors, fmt="o", capsize=3)
    ax.set_xticks(range(len(rows)), [r["method"] for r in rows], rotation=45, ha="right")
    ax.set(title="Saved bounded experiment: effect 0.05, equal turnover",
           ylabel="Recorded first-stream power (%)", ylim=(-3, 103))
    ax.set_xlabel("Methods have different guarantees; these are recorded Monte Carlo summaries")
    ax.grid(axis="y", alpha=.25)
    second = figures / "saved-baseline-power.png"
    fig.savefig(second, dpi=160)
    return matplotlib.__version__, [str(p.relative_to(output)) for p in (first, second)]


def review(*, archive=None, root=None, input_root="/kaggle/input",
           output="/kaggle/working/quant-review", require_recorded_runtime=False) -> dict:
    if archive is not None and root is not None:
        raise ValueError("Choose one source: archive or root")
    if archive is None and root is None:
        kind, source = discover(Path(input_root))
        archive, root = (source, None) if kind == "archive" else (None, source)
    source = Path(archive if archive is not None else root).resolve()
    output = Path(output).resolve()
    if output.exists():
        raise ValueError("Choose a new output directory; previous reviews are preserved")
    if root is not None and output.is_relative_to(source):
        raise ValueError("Review output must be outside the read-only source release")
    manifest = verify_archive(source) if archive is not None else verify_directory(source)
    source_archive_hash = sha256(source) if archive is not None else None
    output.mkdir(parents=True)
    os.environ["MPLCONFIGDIR"] = str(output / "matplotlib-cache")
    # Imports are deferred so caches and all durable review outputs are writable
    # only beneath the configured output, never the attached input dataset.
    import numpy as np
    runtime = {"python": platform.python_version(), "numpy": np.__version__}
    matches = runtime == RECORDED_RUNTIME
    if require_recorded_runtime and not matches:
        raise ValueError("Recorded frozen runtime is Python3.13.7 / NumPy2.5.4; viewing saved data is not exact replay")
    if archive is not None:
        root = output / "release"
        extract_verified(source, root, manifest)
    else:
        root = source
    tables = saved_tables(root, manifest)
    primary, times, lines = inspect_primary(root, manifest, np)
    matplotlib_version, figures = plot_saved(output, tables, times, lines, np)
    copied = output / "tables"
    copied.mkdir()
    for name, relative in CSV_FILES.items():
        (copied / (name + ".csv")).write_bytes((root / relative).read_bytes())
    attribution = ("Saved-results research review. No new experiment or market evidence.\n\n"
        "Original software: MIT; original prose/synthetic displays: CC BY4.0.\n"
        "Binance-derived market outputs/plots: Binance Vision attribution, CC BY-NC-SA4.0 "
        "and applicable provider terms. Bitstamp material retains its provider terms.\n"
        "See the release's THIRD_PARTY.md and LICENSE-PAPER.md.\n")
    (output / "ATTRIBUTION.md").write_text(attribution, encoding="utf-8")
    for filename in ("THIRD_PARTY.md", "LICENSE-PAPER.md", "LICENSE"):
        if filename in manifest["files"]:
            (output / filename).write_bytes((root / filename).read_bytes())
    if archive is not None:
        if sha256(source) != source_archive_hash:
            raise ValueError("Source release archive changed during review")
    else:
        if verify_directory(root) != manifest:
            raise ValueError("Source release directory changed during review")
    summary = {
        "status": "completed saved-results review", "scope": SCOPE,
        "source": str(source), "source_kind": "archive" if archive is not None else "directory",
        "archive_sha256": source_archive_hash,
        "release_manifest_sha256": sha256(root / MANIFEST),
        "files_verified": len(manifest["files"]), "scientific_registries": manifest["scientific_registries"],
        "runtime": {**runtime, "matplotlib": matplotlib_version, "platform": platform.platform()},
        "recorded_runtime": RECORDED_RUNTIME, "matches_recorded_python_numpy": matches,
        "exact_numerical_replay_performed": False,
        "runtime_interpretation": "Matching key versions alone does not prove exact replay; locked dependencies, archived sources and exact inputs are also required",
        "csv_row_counts": {name: len(rows) for name, rows in tables.items()},
        "primary": primary, "figures": figures,
        "finished_at": datetime.now(timezone.utc).isoformat(),
    }
    (output / "review-summary.json").write_text(json.dumps(summary, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    return summary


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--archive", type=Path)
    source.add_argument("--root", type=Path)
    parser.add_argument("--input-root", type=Path, default=Path("/kaggle/input"))
    parser.add_argument("--output", type=Path, default=Path("/kaggle/working/quant-review"))
    parser.add_argument("--require-recorded-runtime", action="store_true")
    args = parser.parse_args(argv)
    try:
        result = review(archive=args.archive, root=args.root, input_root=args.input_root,
                        output=args.output, require_recorded_runtime=args.require_recorded_runtime)
        print(json.dumps(result, indent=2, allow_nan=False))
        return 0
    except (ValueError, OSError, KeyError, TypeError, BadZipFile) as error:
        print(f"{type(error).__name__}: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
