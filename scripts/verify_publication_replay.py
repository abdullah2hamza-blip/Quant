"""Compare all scientific outputs of a replay against preserved study artifacts.

Only explicitly listed operational metadata may differ. Result manifests and
their referenced file hashes are checked before ignoring the necessarily new
run identifiers, output-file hashes, wall times and relocated local paths.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
import math
from pathlib import Path

import numpy as np


_SIMULATION_MANIFEST_VOLATILE = {
    ("run_id",), ("created_at",), ("runtime", "platform"),
    ("completed", "*", "json_sha256"),
    ("completed", "*", "worlds_sha256"),
}
_MARKET_MANIFEST_VOLATILE = {
    ("run_id",), ("created_at",), ("finished_at",),
    ("retrospective_access_number",),
    ("cases", "*", "elapsed_seconds"),
    ("cases", "*", "sha256", "report.json"),
    ("cases", "*", "sha256", "selections.json"),
    ("cases", "*", "sha256", "base-cost-trades.json"),
    ("cases", "*", "sha256", "paths.npz"),
}
_MARKET_REPORT_VOLATILE = {
    ("created_at",), ("effective_settings", "source"),
    ("audit", "as_of"), ("provenance", "local_path"),
}
_MARKET_FILES = {"report.json", "selections.json", "base-cost-trades.json", "paths.npz"}


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _read(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _volatile(path: tuple, patterns: set[tuple]) -> bool:
    return any(len(path) == len(pattern) and all(
        expected == actual or expected == "*" and isinstance(actual, int)
        for expected, actual in zip(pattern, path, strict=True)
    ) for pattern in patterns)


def _location(file: str, path: tuple) -> str:
    return file + ":" + ".".join(map(str, path))


@dataclass
class _Comparison:
    atol: float
    rtol: float
    files: int = 0
    arrays: int = 0
    all_values_exact: bool = True
    all_bits_equal: bool = True
    largest_float_difference: float = 0.
    json_files: int = 0
    json_values: int = 0
    json_float_values_exact: bool = True
    largest_json_float_difference: float = 0.
    ignored: set[str] = field(default_factory=set)

    def json(self, left, right, file: str, patterns: set[tuple], path: tuple = ()) -> None:
        location = _location(file, path)
        if type(left) is not type(right):
            raise ValueError(f"Replay JSON type differs at {location}")
        if _volatile(path, patterns):
            self.ignored.add(location)
            return
        if isinstance(left, dict):
            if left.keys() != right.keys():
                raise ValueError(f"Replay JSON fields differ at {location}")
            for key in sorted(left):
                self.json(left[key], right[key], file, patterns, (*path, key))
        elif isinstance(left, list):
            if len(left) != len(right):
                raise ValueError(f"Replay JSON list length differs at {location}")
            for index, (a, b) in enumerate(zip(left, right, strict=True)):
                self.json(a, b, file, patterns, (*path, index))
        elif isinstance(left, float):
            if not math.isfinite(left) or not math.isfinite(right):
                raise ValueError(f"Nonfinite replay JSON number at {location}")
            difference = abs(left - right)
            self.largest_json_float_difference = max(self.largest_json_float_difference, difference)
            self.json_float_values_exact &= left == right
            if not math.isclose(left, right, rel_tol=self.rtol, abs_tol=self.atol):
                raise ValueError(f"Replay JSON number differs at {location}")
            self.json_values += 1
        else:
            if left != right:
                raise ValueError(f"Replay JSON value differs at {location}")
            self.json_values += 1

    def json_file(self, original: Path, replay: Path, relative: str, patterns: set[tuple]) -> None:
        self.json(_read(original), _read(replay), relative, patterns)
        self.json_files += 1

    def npz(self, original: Path, replay: Path, relative: str) -> None:
        with np.load(original, allow_pickle=False) as left, np.load(replay, allow_pickle=False) as right:
            if set(left.files) != set(right.files):
                raise ValueError(f"Replay array keys differ: {relative}")
            if not left.files:
                raise ValueError(f"Replay NPZ has no arrays: {relative}")
            for name in left.files:
                a, b = left[name], right[name]
                if a.shape != b.shape:
                    raise ValueError(f"Replay array shape differs: {relative}:{name}")
                if a.dtype != b.dtype:
                    raise ValueError(f"Replay array dtype differs: {relative}:{name}")
                self.all_values_exact &= bool(np.array_equal(a, b))
                self.all_bits_equal &= a.tobytes(order="C") == b.tobytes(order="C")
                if a.dtype.kind in "fc":
                    if not np.isfinite(a).all() or not np.isfinite(b).all():
                        raise ValueError(f"Replay floating array is nonfinite: {relative}:{name}")
                    if a.size:
                        self.largest_float_difference = max(
                            self.largest_float_difference, float(np.max(np.abs(a - b)))
                        )
                    if not np.allclose(a, b, atol=self.atol, rtol=self.rtol, equal_nan=False):
                        raise ValueError(f"Replay floating array differs: {relative}:{name}")
                elif not np.array_equal(a, b):
                    raise ValueError(f"Replay event, truth, time or exact array differs: {relative}:{name}")
                self.arrays += 1
        self.files += 1


def _inventory(path: Path, expected: set[str]) -> None:
    if not path.is_dir() or {p.name for p in path.iterdir()} != expected:
        raise ValueError(f"Replay artifact file set differs or is incomplete: {path}")


def _manifest(root: Path, *, market: bool) -> tuple[dict, list[str]]:
    manifest = _read(root / "manifest.json")
    ids = [case["id"] for case in manifest["spec"]["cases"]]
    if not ids or len(set(ids)) != len(ids) or any(
        not isinstance(cid, str) or not cid or "/" in cid or "\\" in cid or cid in (".", "..")
        for cid in ids
    ):
        raise ValueError("Replay manifest needs distinct nonempty safe case identifiers")
    if market:
        if manifest["status"] != "completed" or [r["case_id"] for r in manifest["cases"]] != ids:
            raise ValueError("Replay market case set/order is incomplete")
        _inventory(root, {"manifest.json", *ids})
        for record in manifest["cases"]:
            folder = root / record["case_id"]
            _inventory(folder, _MARKET_FILES)
            if set(record["sha256"]) != _MARKET_FILES:
                raise ValueError("Replay market manifest does not hash every case artifact")
            for name, expected in record["sha256"].items():
                if _digest(folder / name) != expected:
                    raise ValueError(f"Replay market artifact hash differs: {record['case_id']}/{name}")
    else:
        if manifest["kind"] != "substantive" or manifest["case_ids"] != ids or [r["id"] for r in manifest["completed"]] != ids:
            raise ValueError("Replay simulation case set/order is incomplete or not substantive")
        _inventory(root, {"manifest.json", "counterexamples.json", *(f"{cid}.{extension}" for cid in ids for extension in ("json", "npz"))})
        for record in manifest["completed"]:
            for extension, field in (("json", "json_sha256"), ("npz", "worlds_sha256")):
                name = f"{record['id']}.{extension}"
                if _digest(root / name) != record[field]:
                    raise ValueError(f"Replay simulation artifact hash differs: {name}")
    return manifest, ids


def compare_replay(original: Path, reproduced: Path, *, market: bool,
                   atol: float = 1e-12, rtol: float = 1e-12) -> dict:
    """Check all declared scientific artifacts, with enumerated metadata exclusions.

    Integer/boolean/string JSON values and nonfloating arrays are exact. JSON
    numeric types, NPZ dtypes/shapes/keys, and case/file sets must agree. Float
    values use the documented relative/absolute tolerance; nonfinite values are
    rejected. Bitwise array equality means matching dtype and canonical element
    bytes, so it distinguishes signed zero. This function does not recompute
    statistics or establish the validity of the original scientific experiment.
    """
    for name, value in (("atol", atol), ("rtol", rtol)):
        if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
            raise ValueError(f"{name} must be a finite nonnegative tolerance")
    expected, ids = _manifest(original, market=market)
    replayed, other_ids = _manifest(reproduced, market=market)
    if ids != other_ids:
        raise ValueError("Expected and replayed case sets/order differ")
    comparison = _Comparison(float(atol), float(rtol))
    comparison.json(expected, replayed, "manifest.json",
                    _MARKET_MANIFEST_VOLATILE if market else _SIMULATION_MANIFEST_VOLATILE)
    comparison.json_files += 1
    if market:
        for cid in ids:
            for name in ("report.json", "selections.json", "base-cost-trades.json"):
                comparison.json_file(original / cid / name, reproduced / cid / name, f"{cid}/{name}",
                                     _MARKET_REPORT_VOLATILE if name == "report.json" else set())
            comparison.npz(original / cid / "paths.npz", reproduced / cid / "paths.npz", f"{cid}/paths.npz")
    else:
        comparison.json_file(original / "counterexamples.json", reproduced / "counterexamples.json", "counterexamples.json", set())
        for cid in ids:
            comparison.json_file(original / f"{cid}.json", reproduced / f"{cid}.json", f"{cid}.json", {("runtime_seconds",)})
            comparison.npz(original / f"{cid}.npz", reproduced / f"{cid}.npz", f"{cid}.npz")
    return {"kind": "market" if market else "simulation", "case_ids": ids, "cases_compared": len(ids),
            "files_compared": comparison.files, "arrays_compared": comparison.arrays,
            "array_dtypes_exact": True, "all_array_values_exact": comparison.all_values_exact,
            "all_bitwise_equal": comparison.all_bits_equal,
            "largest_absolute_float_difference": comparison.largest_float_difference,
            "json_files_compared": comparison.json_files, "json_values_compared": comparison.json_values,
            "all_json_float_values_exact": comparison.json_float_values_exact,
            "largest_absolute_json_float_difference": comparison.largest_json_float_difference,
            "ignored_operational_metadata_paths": sorted(comparison.ignored),
            "numeric_tolerance": {"relative": float(rtol), "absolute": float(atol),
                                  "exact": "JSON types/nonfloats; NPZ dtypes, shape, keys and nonfloating elements"},
            "limit": "Stable-output replay agreement; not independent validation of statistical assumptions or PDF layout"}
