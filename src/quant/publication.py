"""Registered synthetic paired-cost study, separate from market backtests.

No publication result is produced by a smoke run. Constant-bet mixtures use
existing bounded-betting/Hoeffding constructions. All cost units are synthetic.
"""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
import platform
import re
import time
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

import numpy as np

from .cost_evidence import counterexamples, test_level
from .data import digest, json_write
from .ledger import Ledger, code_hash, utc_now


METHODS = ("oracle_linear", "joint_linear", "separate_linear", "plugin_linear",
           "symmetric_upper_linear", "joint_hoeffding", "separate_hoeffding",
           "fixed_horizon_hoeffding", "naive_peek_hoeffding")


def wilson(values: np.ndarray) -> dict:
    values = np.asarray(values)
    if values.ndim != 1 or len(values) == 0 or not np.all((values == 0) | (values == 1)):
        raise ValueError("Wilson interval needs independent-world binary outcomes")
    n, p, z = len(values), float(values.mean()), 1.959963984540054
    center = (p + z * z / (2 * n)) / (1 + z * z / n)
    radius = z / (1 + z * z / n) * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return {"estimate": p, "independent_worlds": n, "standard_error": math.sqrt(p * (1 - p) / n),
            "confidence_interval": [max(0., center - radius), min(1., center + radius)],
            "method": "Wilson 95% Monte Carlo interval across independent worlds"}


def mean_interval(values: np.ndarray) -> dict:
    values = np.asarray(values, dtype=float)
    if values.ndim != 1 or len(values) < 2 or not np.isfinite(values).all():
        raise ValueError("Need at least two finite independent-world summaries")
    mean, se = float(values.mean()), float(values.std(ddof=1) / math.sqrt(len(values)))
    return {"estimate": mean, "standard_error": se,
            "confidence_interval": [mean - 1.959963984540054 * se, mean + 1.959963984540054 * se] if se > 0 else None,
            "sample_degenerate": se == 0,
            "independent_worlds": len(values), "method": "normal 95% Monte Carlo interval across independent worlds; unavailable for a degenerate sample",
            "caveat": "A zero empirical standard error does not establish zero Monte Carlo uncertainty; normal intervals are approximate."}


def _calibration_bounds(total: np.ndarray, n: int, cap: float, delta: float) -> tuple[np.ndarray, np.ndarray]:
    if n == 0:
        return np.zeros_like(total), np.full_like(total, cap)
    radius = cap * math.sqrt((math.log(math.pi ** 2 / (3 * delta)) + 2 * math.log(n)) / (2 * n))
    return np.maximum(0., total / n - radius), np.minimum(cap, total / n + radius)


def _mixture(logs: np.ndarray) -> np.ndarray:
    maximum = logs.max(axis=-1)
    return maximum + np.log(np.mean(np.exp(logs - maximum[..., None]), axis=-1))


def _seed(base: int, case_id: str) -> int:
    return int.from_bytes(hashlib.sha256(f"{base}:{case_id}".encode()).digest()[:8], "little")


def load_spec(path: Path) -> dict:
    raw = json.loads(path.read_text(encoding="utf-8"))
    fields = {"schema_version", "protocol_id", "status", "alpha_family", "delta_cost_envelope", "worlds", "calendar_steps", "hypotheses", "seed", "normalized_utility_bound", "true_common_cost", "cost_support_upper", "calibration_initial", "calibration_per_trial", "betting_grid", "simulation_materiality", "methods", "cases", "primary_comparison", "monte_carlo_unit", "stopping", "scope_limits"}
    if set(raw) != fields:
        raise ValueError("Unknown or missing study fields")
    for field in ("worlds", "calendar_steps", "hypotheses", "seed", "calibration_initial", "calibration_per_trial"):
        if type(raw[field]) is not int or raw[field] < (2 if field == "worlds" else 0):
            raise ValueError(f"Invalid {field}")
    if type(raw["schema_version"]) is not int or raw["schema_version"] != 1 or raw["calendar_steps"] < 20 or raw["hypotheses"] < 1:
        raise ValueError("Invalid study schema or dimensions")
    if tuple(raw["methods"]) != METHODS or raw["normalized_utility_bound"] != 1.:
        raise ValueError("Unsupported method list or utility bound")
    test_level(raw["alpha_family"], raw["delta_cost_envelope"], 1)
    for field in ("true_common_cost", "cost_support_upper", "simulation_materiality", "normalized_utility_bound"):
        value = raw[field]
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            raise ValueError(f"Invalid finite numeric setting: {field}")
    if not 0 < raw["true_common_cost"] < raw["cost_support_upper"] or raw["simulation_materiality"] < 0:
        raise ValueError("Cost coefficient must be inside calibration support")
    grid = np.asarray(raw["betting_grid"], dtype=float)
    if grid.ndim != 1 or not len(grid) or not np.isfinite(grid).all() or np.any((grid <= 0) | (grid >= 1)) or len(np.unique(grid)) != len(grid):
        raise ValueError("Invalid fixed betting mixture")
    identifiers = [x["id"] for x in raw["cases"]]
    if not identifiers or len(set(identifiers)) != len(identifiers) or any(not isinstance(x, str) or not re.fullmatch(r"[a-z][a-z0-9_]{0,63}", x) or x in {"con", "prn", "aux", "nul", *[f"com{i}" for i in range(1,10)], *[f"lpt{i}" for i in range(1,10)]} for x in identifiers):
        raise ValueError("Case identifiers must be distinct safe names")
    allowed = {"id", "effect", "overlap", "hypotheses", "label_delay", "adaptive_births", "calibration_initial", "oscillating_prefix_null", "cost_shift", "assumption_violation", "reference_more_turnover"}
    for case in raw["cases"]:
        if not {"id", "effect", "overlap"} <= set(case) or not set(case) <= allowed:
            raise ValueError("Unknown or missing simulation case fields")
        for key in ("effect", "overlap", "cost_shift"):
            if key in case and (isinstance(case[key], bool) or not isinstance(case[key], (int, float)) or not math.isfinite(case[key])):
                raise ValueError(f"Invalid case numeric field: {key}")
        if not 0 <= case["effect"] <= .1 or not 0 <= case["overlap"] <= 1:
            raise ValueError("Invalid case effect or overlap")
        for key in ("hypotheses", "label_delay", "adaptive_births", "calibration_initial"):
            if key in case and (type(case[key]) is not int or case[key] < (1 if key == "hypotheses" else 0)):
                raise ValueError(f"Invalid case count: {key}")
        if case.get("adaptive_births", 0) > case.get("hypotheses", raw["hypotheses"]):
            raise ValueError("Births cannot exceed the candidate pool")
        for key in ("oscillating_prefix_null", "assumption_violation", "reference_more_turnover"):
            if key in case and type(case[key]) is not bool:
                raise ValueError(f"Case switch must be boolean: {key}")
        if "cost_shift" in case and (not 0 < case["cost_shift"] < raw["cost_support_upper"] or not case.get("assumption_violation")):
            raise ValueError("Changing a fixed cost must be labeled an assumption violation")
        if case.get("oscillating_prefix_null") and (case["effect"] != 0 or case.get("adaptive_births")):
            raise ValueError("This weak-prefix generator requires zero effect and a fixed family")
    return raw


def _seal(payload: dict) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def _snapshot_source(root: Path, output: Path, documents: list[Path]) -> str:
    """Preserve the actual reproducible source, not only a soon-stale hash."""
    files = {p.resolve() for p in documents}
    for directory, pattern in (("src", "*.py"), ("tests", "*.py"), ("scripts", "*.py"), ("configs", "*.json"), ("configs", "*.toml"), (".github", "*.yml")):
        files.update((root / directory).rglob(pattern))
    files.update(p for p in (root / name for name in ("pyproject.toml", "uv.lock", "README.md", ".python-version", ".gitattributes", ".gitignore")) if p.is_file())
    output.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(output, "x", compression=ZIP_DEFLATED) as archive:
        for path in sorted(files):
            name = path.resolve().relative_to(root.resolve()).as_posix()
            info = ZipInfo(name, (1980, 1, 1, 0, 0, 0))
            info.compress_type = ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, path.read_bytes())
    return digest(output)


def freeze_study(spec_path: Path, protocol_path: Path, output: Path, ledger: Ledger, root: Path) -> dict:
    identifier = ledger.start("publication_simulation_freeze", {"spec": str(spec_path), "protocol": str(protocol_path), "output": str(output)}, code=code_hash(root))
    try:
        load_spec(spec_path)
        if output.exists():
            raise ValueError("Freeze already exists; preserve the previous version")
        documents = [protocol_path, *(root / "docs/publication/reviews" / name for name in
                                     ("mathematical-design-01.md", "cost-primitives-01.md", "simulation-runner-01.md"))]
        addendum = root / "docs/publication/protocol-v1-addendum-01.md"
        if addendum.exists():
            documents.append(addendum)
        snapshot = output.with_suffix(".sources.zip")
        snapshot_hash = _snapshot_source(root, snapshot, documents)
        payload = {"kind": "publication_simulation_freeze", "created_at": utc_now(),
                   "code_sha256": code_hash(root), "spec_sha256": digest(spec_path),
                   "runtime": {"python": platform.python_version(), "numpy": np.__version__},
                   "source_snapshot": snapshot.name, "source_snapshot_sha256": snapshot_hash,
                   "documents": [{"path": p.resolve().relative_to(root.resolve()).as_posix(), "sha256": digest(p)} for p in documents],
                   "scope": "Known-truth synthetic study; this does not freeze or authorize a market backtest",
                   "review_limit": "Pins reviewed documents; file existence and hashes do not certify scientific correctness"}
        payload["freeze_sha256"] = _seal(payload)
        json_write(output, payload)
        ledger.finish(identifier, "completed", {"output": str(output), "sha256": digest(output)})
        return payload
    except Exception as error:
        ledger.finish(identifier, "failed", {"error": str(error)})
        raise


def check_study_freeze(freeze: Path, spec_path: Path, root: Path) -> dict:
    payload = json.loads(freeze.read_text(encoding="utf-8"))
    saved = payload.pop("freeze_sha256", None)
    if saved != _seal(payload) or payload.get("kind") != "publication_simulation_freeze":
        raise ValueError("Study freeze integrity check failed")
    snapshot = (freeze.parent / payload["source_snapshot"]).resolve()
    if snapshot.parent != freeze.parent.resolve() or digest(snapshot) != payload["source_snapshot_sha256"]:
        raise ValueError("Study source snapshot is missing or changed")
    expected = {"code_sha256": code_hash(root), "spec_sha256": digest(spec_path),
                "runtime": {"python": platform.python_version(), "numpy": np.__version__}}
    for key, value in expected.items():
        if payload.get(key) != value:
            raise ValueError(f"Study freeze mismatch: {key}")
    for document in payload["documents"]:
        path = (root / document["path"]).resolve()
        if not path.is_relative_to(root.resolve()) or digest(path) != document["sha256"]:
            raise ValueError("Study protocol or reviewed document changed")
    return {**payload, "freeze_sha256": saved}


def simulate_case(spec: dict, case: dict, *, worlds: int | None = None,
                  calendar_steps: int | None = None) -> tuple[dict, dict[str, np.ndarray]]:
    """Vectorized independent worlds with correlated hypothesis streams.

    Current outcomes are drawn only after births, cost intervals and turnover are
    fixed. No intermediate feedback exists in delayed trials; these are not
    overlapping financial labels. Prescreening uses only past observable proxies.
    """
    started = time.perf_counter()
    w = spec["worlds"] if worlds is None else worlds
    horizon = spec["calendar_steps"] if calendar_steps is None else calendar_steps
    pool = case.get("hypotheses", spec["hypotheses"])
    births = case.get("adaptive_births", 0)
    h = births or pool
    delay = case.get("label_delay", 0)
    if any(type(x) is not int or x < 0 for x in (w, horizon, pool, births, delay)) or w < 2 or horizon < 2 or pool < 1 or h > pool:
        raise ValueError("Invalid simulation dimensions")
    overlap = float(case["overlap"])
    effect = float(case["effect"])
    if not 0 <= overlap <= 1 or not 0 <= effect <= .1:
        raise ValueError("Invalid turnover overlap or effect")
    rng = np.random.default_rng(_seed(spec["seed"], case["id"]))
    calibration_rng = np.random.default_rng(_seed(spec["seed"], case["id"] + ":calibration"))
    cap, theta = spec["cost_support_upper"], spec["true_common_cost"]
    delta = spec["delta_cost_envelope"]
    ncal = case.get("calibration_initial", spec["calibration_initial"])
    total = cap * calibration_rng.binomial(ncal, theta / cap, w).astype(float)
    grid = np.asarray(spec["betting_grid"])
    log_components = np.zeros((7, w, h, len(grid)))
    latent_hoeffding_logs = np.zeros((w, h, len(grid)))
    hit = np.zeros((len(METHODS), w, h), dtype=bool)
    first = np.full(hit.shape, horizon + 1, dtype=np.int32)
    latent_hit = np.zeros((2, w, h), dtype=bool)
    coverage_failed = np.zeros(w, dtype=bool)
    pathwise_violations = 0
    materiality_utility = np.zeros((len(METHODS), w))
    net_utility = np.zeros_like(materiality_utility)
    deployed = np.full((len(METHODS), w), -1, dtype=np.int32)
    active = np.zeros(h, dtype=bool)
    chosen = np.zeros((w, h), dtype=np.int32)
    selected_at_birth = np.full((w, h), -1, dtype=np.int32)
    selected_used = np.zeros((w, pool), dtype=bool)
    null_status = np.ones((w, h), dtype=bool)
    prescreen = np.zeros((w, pool))
    cumulative_proxy = np.zeros((w, h))
    trials = np.zeros(h, dtype=int)
    previous_common = np.zeros(w)
    pool_effects = np.where(np.arange(pool) % 2 == 0, effect, 0.)
    spacing = max(1, horizon // max(1, births))
    birth_times = np.arange(h) * spacing if births else np.zeros(h, dtype=int)
    thresholds = np.array([-math.log(test_level(spec["alpha_family"], delta, j + 1,
                                                 family_size=None if births else h)) for j in range(h)])
    trace = []
    issue_times = range(0, horizon - delay, delay + 1)
    for trial_number, issued_at in enumerate(issue_times):
        matured_at = issued_at + delay + 1
        # Birth selection occurs before drawing this trial's outcome.
        for j in range(h):
            if not active[j] and issued_at >= birth_times[j]:
                if births:
                    scores = np.where(selected_used, -np.inf, prescreen)
                    selected = np.argmax(scores, axis=1)
                    selected_used[np.arange(w), selected] = True
                else:
                    selected = np.full(w, j)
                chosen[:, j] = selected
                selected_at_birth[:, j] = selected
                null_status[:, j] = pool_effects[selected] == 0
                active[j] = True
        lower, upper = _calibration_bounds(total, ncal, cap, delta)
        estimate = total / ncal if ncal else np.full(w, cap / 2)
        true_cost = case.get("cost_shift", theta) if issued_at >= horizon // 2 else theta
        coverage_failed |= (true_cost < lower - 1e-14) | (true_cost > upper + 1e-14)
        # Turnover may adapt to the previously matured common shock.
        qa_pool = np.broadcast_to((.7 + .1 * (previous_common > 0))[:, None], (w, pool)).copy()
        qb_pool = qa_pool * overlap
        if case.get("reference_more_turnover"):
            qa_pool, qb_pool = qb_pool, qa_pool
        qa, qb = np.take_along_axis(qa_pool, chosen, axis=1), np.take_along_axis(qb_pool, chosen, axis=1)
        volatility = .2 + .2 * (1 + math.sin(2 * math.pi * issued_at / 80)) / 2 + .15 * (previous_common > 0)
        common = rng.choice([-1., 1.], w)
        individual = rng.choice([-1., 1.], (w, pool))
        noise = volatility[:, None] * (.6 * common[:, None] + .4 * individual)
        drift = np.broadcast_to(pool_effects, (w, pool)).copy()
        if case.get("oscillating_prefix_null"):
            drift[:] = -.07 if trial_number % 2 == 0 else .07
        latent_pool = noise + drift
        if np.any(np.abs(latent_pool) > spec["normalized_utility_bound"]):
            raise ValueError("Generator violated its registered latent bound")
        latent = np.take_along_axis(latent_pool, chosen, axis=1)
        gross_pool = latent_pool + (qa_pool - qb_pool) * true_cost + spec["simulation_materiality"]
        gross = np.take_along_axis(gross_pool, chosen, axis=1)
        difference = qa - qb
        joint = gross - np.maximum(difference * lower[:, None], difference * upper[:, None]) - spec["simulation_materiality"]
        separate = gross - qa * upper[:, None] + qb * lower[:, None] - spec["simulation_materiality"]
        plugin = gross - difference * estimate[:, None] - spec["simulation_materiality"]
        symmetric = gross - difference * upper[:, None] - spec["simulation_materiality"]
        observations = np.clip(np.stack([latent, joint, separate, plugin, symmetric, joint, separate]), -1., 1.)
        if np.any(joint < separate - 1e-13):
            raise AssertionError("Paired interval geometry failed")
        # An allocation begins strictly AFTER a crossing, never on its own label.
        for method in range(len(METHODS)):
            selected = deployed[method]
            eligible = selected >= 0
            materiality_utility[method, eligible] += latent[eligible, selected[eligible]]
            net_utility[method, eligible] += latent[eligible, selected[eligible]] + spec["simulation_materiality"]
        update = np.empty_like(log_components)
        update[:5] = np.log1p(observations[:5, ..., None] * grid)
        update[5:] = observations[5:, ..., None] * grid - grid ** 2 / 2
        log_components += update * active[None, None, :, None]
        latent_hoeffding_logs += (latent[..., None] * grid - grid ** 2 / 2) * active[None, :, None]
        trials += active
        wealth = _mixture(log_components)
        if np.any(wealth[1] < wealth[2] - 1e-10) or np.any(wealth[5] < wealth[6] - 1e-10):
            raise AssertionError("Same-mixture wealth domination failed")
        latent_hit[0] |= (wealth[0] >= thresholds) & active
        latent_hit[1] |= (_mixture(latent_hoeffding_logs) >= thresholds) & active
        new_hit = np.zeros_like(hit)
        new_hit[:7] = (wealth >= thresholds) & active
        cumulative_proxy += np.clip(joint, -1, 1) * active
        boundary = np.sqrt(2 * np.maximum(1, trials) * thresholds)
        fixed_reject = (cumulative_proxy >= boundary) & active
        new_hit[8] = fixed_reject
        if matured_at + delay + 1 > horizon:
            new_hit[7] = fixed_reject
        first[new_hit & ~hit] = matured_at
        hit |= new_hit
        for method in range(len(METHODS)):
            ready = (deployed[method] < 0) & hit[method].any(axis=1)
            deployed[method, ready] = np.argmax(hit[method, ready], axis=1)
        # Exact event accounting: outside calibration failure, proxy crossings
        # must be dominated by the corresponding latent mixture crossings.
        for method, latent_method in ((1, 0), (2, 0), (5, 1), (6, 1)):
            bad = hit[method] & ~latent_hit[latent_method] & ~coverage_failed[:, None]
            pathwise_violations += int(bad.sum())
        if pathwise_violations:
            raise AssertionError("Observed crossing lacks envelope failure or latent crossing")
        prescreen += gross_pool - (qa_pool - qb_pool) * estimate[:, None] - spec["simulation_materiality"]
        previous_common = common
        nadd = spec["calibration_per_trial"]
        total += cap * calibration_rng.binomial(nadd, true_cost / cap, w)
        ncal += nadd
        if matured_at % 40 == 0 or matured_at + delay + 1 > horizon:
            trace.append({"calendar_step": matured_at, "mean_joint_minus_separate_proxy": float(np.mean(joint - separate)),
                          "cost_interval_width": float(np.mean(upper - lower)),
                          "first_stream_rejection_rate": {name: float(hit[i, :, 0].mean()) for i, name in enumerate(METHODS)}})
    summaries = {}
    any_alt = (~null_status).any(axis=1)
    for i, name in enumerate(METHODS):
        false_any = (hit[i] & null_status).any(axis=1)
        alt_any = (hit[i] & ~null_status).any(axis=1)
        detected = np.min(np.where(~null_status, first[i], horizon + 1), axis=1)
        if name in ("plugin_linear", "symmetric_upper_linear", "naive_peek_hoeffding"):
            guarantee = "none: deliberately unguaranteed comparator"
        elif case.get("assumption_violation"):
            guarantee = "none for this scenario: registered model assumption deliberately violated"
        else:
            guarantee = "conditional bounded-game guarantee; cost-envelope error included; not a market guarantee"
        summaries[name] = {"null_family_rejection": wilson(false_any),
                           "any_alternative_power": wilson(alt_any[any_alt]) if any_alt.any() else None,
                           "first_stream_power": wilson(hit[i, :, 0]) if np.all(~null_status[:, 0]) else None,
                           "restricted_first_alt_detection_time": mean_interval(np.minimum(detected, horizon).astype(float)) if any_alt.all() else None,
                           "median_first_alt_detection_among_detected": float(np.median(detected[detected <= horizon])) if np.any(detected <= horizon) else None,
                           "nondetection_censoring": "Horizon-censored; restricted time uses horizon for nondetections; conditional median excludes them",
                           "materiality_adjusted_paper_utility": mean_interval(materiality_utility[i]),
                           "net_paper_utility": mean_interval(net_utility[i]), "guarantee": guarantee}
    if np.any(hit[2] & ~hit[1]):
        raise AssertionError("Separate-envelope discovery was not nested in joint discovery")
    paired = {"first_stream_joint_minus_separate_rejection_rate": wilson(hit[1, :, 0] & ~hit[2, :, 0]),
              "joint_minus_separate_materiality_utility": mean_interval(materiality_utility[1] - materiality_utility[2])}
    result = {"case": case, "worlds": w, "calendar_steps": horizon, "matured_trials_by_hypothesis": trials.tolist(),
              "candidate_pool": pool, "tested_hypotheses": h, "seed": _seed(spec["seed"], case["id"]),
              "cost_envelope_any_failure": wilson(coverage_failed), "pathwise_event_inclusion_violations": pathwise_violations,
              "methods": summaries, "paired_method_comparisons": paired, "trace": trace,
              "runtime_seconds": time.perf_counter() - started,
              "largest_mixture_state_bytes": log_components.nbytes,
              "utility_convention": "First crossing activates one candidate on subsequent matured trials; lowest index resolves simultaneous crossings; additive synthetic utility, not funded or compounded P&L",
              "detection_time_convention": "Calendar steps from study origin, not elapsed time since each adaptive birth; horizon-censored",
              "filtration": "birth, calibration and turnover precede current outcome draws; previous common shock is publicly observed at maturity; delayed trials do not overlap; no intermediate feedback",
              "null_interpretation": "Oracle-history conditional null; prefix-weak case uses nonpositive sums at every prefix and fixed mixture components"}
    arrays = {"rejected": hit, "first_crossing": first, "null_at_birth": null_status,
              "cost_envelope_failed": coverage_failed, "latent_crossed": latent_hit,
              "materiality_adjusted_paper_utility": materiality_utility,
              "net_paper_utility": net_utility, "candidate_selected_at_birth": selected_at_birth}
    return result, arrays


def run_study(spec_path: Path, output_root: Path, ledger: Ledger, root: Path, *, smoke: bool = False,
              case_id: str | None = None, freeze: Path | None = None) -> dict:
    identifier = ledger.start("publication_simulation", {"spec": str(spec_path), "smoke": smoke, "case_id": case_id, "freeze": str(freeze)}, code=code_hash(root))
    output = output_root / identifier
    try:
        spec = load_spec(spec_path)
        if not smoke and freeze is None:
            raise ValueError("Substantive study requires a source/protocol/review freeze")
        frozen = check_study_freeze(freeze, spec_path, root) if freeze else None
        cases = [c for c in spec["cases"] if case_id is None or c["id"] == case_id]
        if not cases:
            raise ValueError("Requested case is absent from the registered specification")
        output.mkdir(parents=True, exist_ok=False)
        manifest = {"run_id": identifier, "created_at": utc_now(), "kind": "smoke" if smoke else "substantive",
                    "code_sha256": code_hash(root), "spec_sha256": digest(spec_path), "spec": spec,
                    "freeze": frozen,
                    "runtime": {"python": platform.python_version(), "numpy": np.__version__, "platform": platform.platform()},
                    "case_ids": [c["id"] for c in cases], "completed": []}
        json_write(output / "manifest.json", manifest)
        json_write(output / "counterexamples.json", counterexamples())
        for case in cases:
            case_attempt = ledger.start("publication_simulation_case", {"parent": identifier, "case": case, "smoke": smoke}, code=manifest["code_sha256"])
            try:
                result, arrays = simulate_case(spec, case, worlds=128 if smoke else None, calendar_steps=60 if smoke else None)
                result["kind"] = manifest["kind"]
                result["code_sha256"], result["spec_sha256"] = manifest["code_sha256"], manifest["spec_sha256"]
                target = output / (case["id"] + ".json")
                json_write(target, result)
                np.savez_compressed(output / (case["id"] + ".npz"), **arrays)
                manifest["completed"].append({"id": case["id"], "json_sha256": digest(target),
                                               "worlds_sha256": digest(output / (case["id"] + ".npz"))})
                json_write(output / "manifest.json", manifest)
                ledger.finish(case_attempt, "completed", {"output": str(target), "sha256": digest(target)})
                print(f"Completed {case['id']} ({manifest['kind']}, {result['runtime_seconds']:.2f}s)", flush=True)
            except Exception as error:
                ledger.finish(case_attempt, "failed", {"error": str(error), "parent": identifier})
                raise
        ledger.finish(identifier, "completed", {"output": str(output.resolve()), "cases": len(cases), "kind": manifest["kind"]})
        return {"run_id": identifier, "output": str(output.resolve()), "cases": len(cases), "kind": manifest["kind"]}
    except Exception as error:
        ledger.finish(identifier, "failed", {"error": str(error), "partial_output": str(output)})
        raise
