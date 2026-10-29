"""Compare every stable v2 report field and saved array after frozen replay."""
from __future__ import annotations

from pathlib import Path

from quant.ledger import Ledger
from scripts.collect_followup_results import verify_followup
from scripts.verify_publication_replay import _Comparison


VOLATILE = {("run_id",),("created_at",),("completed_at",),("runtime","platform"),
            ("cases","*","attempt_id"),("cases","*","report_sha256"),("cases","*","arrays_sha256")}


def compare_followup(original: Path, reproduced: Path, freeze: Path, *, replay_ledger: Path,
                     atol: float = 1e-12, rtol: float = 1e-12) -> dict:
    import math
    for tolerance in (atol,rtol):
        if type(tolerance) not in (float,int) or not math.isfinite(tolerance) or tolerance<0:
            raise ValueError("Replay tolerances must be finite nonnegative numbers")
    left,_,_ = verify_followup(original,freeze)
    right,_,_ = verify_followup(reproduced,freeze,ledger=Ledger(replay_ledger))
    comparison = _Comparison(float(atol),float(rtol))
    comparison.json(left,right,"manifest.json",VOLATILE)
    comparison.json_files += 1
    for record in left["cases"]:
        cid = record["case_id"]
        comparison.json_file(original/(cid+".json"),reproduced/(cid+".json"),cid+".json",{("runtime_seconds",),("arrays_sha256",)})
        comparison.npz(original/(cid+".npz"),reproduced/(cid+".npz"),cid+".npz")
    return {"cases_compared":len(left["cases"]),"files_compared":comparison.files,"arrays_compared":comparison.arrays,
            "json_files_compared":comparison.json_files,"json_values_compared":comparison.json_values,
            "array_dtypes_exact":True,"all_array_values_exact":comparison.all_values_exact,"all_bitwise_equal":comparison.all_bits_equal,
            "largest_absolute_float_difference":comparison.largest_float_difference,
            "all_json_float_values_exact":comparison.json_float_values_exact,
            "largest_absolute_json_float_difference":comparison.largest_json_float_difference,
            "ignored_operational_metadata_paths":sorted(comparison.ignored),
            "numeric_tolerance":{"relative":float(rtol),"absolute":float(atol),"exact":"JSON types/nonfloats; NPZ dtypes, shapes, keys and nonfloating values"},
            "limit":"Same-seed numerical reproduction, not additional independent worlds, external peer review or market validity"}
