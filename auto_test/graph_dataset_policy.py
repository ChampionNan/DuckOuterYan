"""Validate frozen Graph dataset definitions used by benchmark regeneration."""
import json
from pathlib import Path

from workload_policy import validate_pins

POLICY = Path(__file__).resolve().parent / "outerjoin_benchmark/sources/graph_dataset_retest_20261010.json"


def load_policy(path=POLICY):
    """Load pinned definitions without calibration, candidate search, or timings."""
    spec = json.loads(Path(path).read_text())
    pins = validate_pins(spec, "replacements")
    if len(pins) != spec["expected_queries"] or spec["target_dataset"] != "epinions":
        raise ValueError("Unexpected Graph dataset policy")
    for field in ("query_id", "path", "sql_fingerprint"):
        if len({r[field] for r in pins}) != len(pins):
            raise ValueError("Duplicate Graph dataset " + field)
    for row in pins:
        if row["family"] != "graph" or row["semantic_tier"] not in ("low", "medium"):
            raise ValueError("Invalid frozen Graph query definition")
        path = Path(row["path"])
        if path.parts != ("graph", row["query_id"] + ".sql"):
            raise ValueError("Unsafe Graph SQL path")
    return spec
