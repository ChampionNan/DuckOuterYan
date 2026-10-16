#!/usr/bin/env python3
"""Fetch pinned input bytes atomically; never replace a mismatching user cache."""
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile

CHECKSUMS = Path(__file__).with_name("data_checksums.json")
GRAPH_URLS = {
    "bitcoin.txt": "https://snap.stanford.edu/data/soc-sign-bitcoinalpha.csv.gz",
    "epinions.txt": "https://snap.stanford.edu/data/soc-Epinions1.txt.gz",
}


def digest(path):
    result = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            result.update(block)
    return result.hexdigest()


def fetch(path):
    expected = json.loads(CHECKSUMS.read_text())[path.name]
    if path.exists():
        if digest(path) != expected:
            raise ValueError(f"Cached data checksum mismatch: {path}; preserve/move it before retrying")
        print(f"[verified] {path}", flush=True)
        return
    url = GRAPH_URLS.get(path.name) or (
        "https://github.com/duckdb/duckdb-data/releases/download/v1.0/" + path.name)
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".download-", dir=path.parent) as temp:
        raw = Path(temp) / "raw"
        subprocess.run(["curl", "--fail", "--location", "--retry", "5",
                        "--connect-timeout", "30", "--output", str(raw), url], check=True)
        normalized = Path(temp) / "normalized"
        if path.name in GRAPH_URLS:
            with gzip.open(raw, "rb") as source, normalized.open("wb") as target:
                if path.name == "epinions.txt":
                    # Match the frozen loader's four SNAP comment-header lines.
                    for _ in range(4):
                        if not source.readline().startswith(b"#"):
                            raise ValueError("Unexpected Epinions header")
                shutil.copyfileobj(source, target)
        else:
            normalized = raw
        if digest(normalized) != expected:
            raise ValueError(f"Downloaded data checksum mismatch: {url}")
        # Exclusive installation: another invocation cannot overwrite this cache.
        import os
        os.link(normalized, path)
    print(f"[downloaded and verified] {path}", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", type=Path)
    fetch(parser.parse_args().path.resolve())
