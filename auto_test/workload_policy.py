"""Validation for frozen workload definitions, independent of experiment outputs."""
from pathlib import PurePosixPath
import re


REPRESENTATION = "frozen_workload_definition"


def validate_pins(spec, key="excluded"):
    """Check membership pins; historical performance is not replayed as evidence."""
    if spec.get("representation") != REPRESENTATION:
        raise ValueError("Expected a frozen workload definition without measurements")
    rows = spec[key]
    for field in ("query_id", "path", "sql_fingerprint"):
        if len({row[field] for row in rows}) != len(rows):
            raise ValueError("Duplicate workload identity: " + field)
    for row in rows:
        path = PurePosixPath(row["path"])
        if path.parts != (row["family"], row["query_id"] + ".sql"):
            raise ValueError("Unsafe workload query path")
        for field in ("content_sha256", "sql_fingerprint"):
            if not re.fullmatch(r"[0-9a-f]{64}", row[field]):
                raise ValueError("Invalid workload fingerprint: " + field)
    return rows
