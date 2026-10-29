"""Preserve completed substantive runs and their exact sources in a portable result tree."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil

from quant.data import digest, json_write
from quant.ledger import Ledger, code_hash, utc_now
from quant.publication import _seal


def collect(simulation: Path, market: Path, simulation_freeze: Path, market_freeze: Path, output: Path, ledger: Ledger, root: Path) -> dict:
    identifier = ledger.start("publication_result_collection", {"simulation": str(simulation), "market": str(market), "output": str(output)}, code=code_hash(root))
    try:
        if output.exists():
            raise ValueError("Result collection already exists; preserve it")
        sim = json.loads((simulation / "manifest.json").read_text())
        mkt = json.loads((market / "manifest.json").read_text())
        if sim["kind"] != "substantive" or sim["case_ids"] != [c["id"] for c in sim["spec"]["cases"]] or [c["id"] for c in sim["completed"]] != sim["case_ids"]:
            raise ValueError("Need every registered substantive simulation case")
        if mkt["status"] != "completed" or [c["case_id"] for c in mkt["cases"]] != [c["id"] for c in mkt["spec"]["cases"]]:
            raise ValueError("Need every registered completed market case")
        rows = ledger.rows()
        for manifest, kind in ((sim, "publication_simulation"), (mkt, "publication_market")):
            matches = [r for r in rows if r["id"] == manifest["run_id"] and r["kind"] == kind and r["status"] == "completed"]
            if len(matches) != 1:
                raise ValueError("Study parent completion is not verified by the ledger")
        for case in sim["completed"]:
            if digest(simulation / (case["id"] + ".json")) != case["json_sha256"] or digest(simulation / (case["id"] + ".npz")) != case["worlds_sha256"]:
                raise ValueError("Simulation case artifact hash mismatch")
            result = json.loads((simulation / (case["id"] + ".json")).read_text())
            if result["kind"] != "substantive" or result["worlds"] != sim["spec"]["worlds"] or result["calendar_steps"] != sim["spec"]["calendar_steps"]:
                raise ValueError("Substantive simulation dimensions do not match")
        for case in mkt["cases"]:
            for name, expected in case["sha256"].items():
                if digest(market / case["case_id"] / name) != expected:
                    raise ValueError("Market case artifact hash mismatch")
        freezes = {}
        for name, source, manifest in (("simulation", simulation_freeze, sim), ("market", market_freeze, mkt)):
            freeze = json.loads(source.read_text())
            seal = freeze.pop("freeze_sha256")
            if seal != _seal(freeze) or manifest["freeze"]["freeze_sha256"] != seal:
                raise ValueError("Run and source freeze do not match")
            archive = source.parent / freeze["source_snapshot"]
            if digest(archive) != freeze["source_snapshot_sha256"]:
                raise ValueError("Frozen source archive changed")
            freezes[name] = (source, archive)
        output.mkdir(parents=True)
        shutil.copytree(simulation, output / "simulation")
        shutil.copytree(market, output / "market")
        source_dir = output / "source-snapshots"
        source_dir.mkdir()
        for pair in freezes.values():
            for file in pair:
                shutil.copy2(file, source_dir / file.name)
        registry = {"schema_version": 1, "collected_at": utc_now(), "simulation_run_id": sim["run_id"], "market_run_id": mkt["run_id"],
                    "simulation": "simulation", "market": "market", "source_freezes": {key: f"source-snapshots/{pair[0].name}" for key, pair in freezes.items()},
                    "simulation_manifest_sha256": digest(output / "simulation/manifest.json"), "market_manifest_sha256": digest(output / "market/manifest.json"),
                    "status": "completed substantive artifacts preserved; collection does not certify scientific interpretation or publication readiness"}
        registry["collection_attempt_id"] = identifier
        registry["ledger_snapshot_timing"] = "Immediately before collection finalization; this collection's own row is still started. Study parents/children are terminal. Consult the live ledger for collection completion."
        json_write(output / "attempt-ledger.json", ledger.rows())
        with ledger.connect() as original:
            import sqlite3
            with sqlite3.connect(output / "research.sqlite") as copy:
                original.backup(copy)
        registry["ledger_json_sha256"] = digest(output / "attempt-ledger.json")
        registry["ledger_sqlite_sha256"] = digest(output / "research.sqlite")
        json_write(output / "registry.json", registry)
        ledger.finish(identifier, "completed", {"output": str(output.resolve()), "simulation_run": sim["run_id"], "market_run": mkt["run_id"], "registry_sha256": digest(output / "registry.json")})
        return registry
    except Exception as error:
        # Exports precede finalization, so even a late disk/export failure is logged.
        if any(r["id"] == identifier and r["status"] == "started" for r in ledger.rows()):
            ledger.finish(identifier, "failed", {"error": str(error), "partial_output": str(output)})
        raise


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--simulation", type=Path, required=True)
    p.add_argument("--market", type=Path, required=True)
    p.add_argument("--simulation-freeze", type=Path, required=True)
    p.add_argument("--market-freeze", type=Path, required=True)
    p.add_argument("--output", type=Path, default=Path("results/publication-v1"))
    p.add_argument("--ledger", type=Path, default=Path("runs/research.sqlite"))
    a = p.parse_args()
    print(json.dumps(collect(a.simulation, a.market, a.simulation_freeze, a.market_freeze, a.output, Ledger(a.ledger), Path(__file__).resolve().parents[1]), indent=2))
