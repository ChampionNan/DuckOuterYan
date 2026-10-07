"""Database path defaults shared by Python benchmark helpers (no file I/O)."""

import os
from pathlib import Path


def database_path(family, repo_root, environ=None):
    """Match configs.sh; never infer scale from an existing file or its size."""
    if family not in ("graph", "tpch", "tpcds", "job"):
        raise ValueError("Unknown database family: " + str(family))
    environ = os.environ if environ is None else environ
    override = environ.get(family.upper() + "_DB")
    if override:
        return Path(override).expanduser()
    if family in ("tpch", "tpcds"):
        scale = environ.get(family.upper() + "_SF") or "50"
        return Path(repo_root) / (family + "_" + scale + ".duckdb")
    return Path(repo_root) / (family + "_db")
