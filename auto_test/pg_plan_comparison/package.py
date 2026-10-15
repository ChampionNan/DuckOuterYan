#!/usr/bin/env python3
"""Package current source changes, harness, and pinned PG source; exclude databases/builds."""
import argparse
import io
import json
import os
from pathlib import Path
import sys
import tarfile
import time

from server import PG_SHA256, digest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import anonymous_source


def anonymous_metadata(info):
    info.uid = info.gid = info.mtime = 0
    info.uname = info.gname = ""
    info.pax_headers = {}
    return info


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True, help="new .tar.gz path")
    parser.add_argument("--pg-source", type=Path, default=ROOT / "postgres/postgresql-16.2.tar.gz")
    parser.add_argument("--without-pg-source", action="store_true", help="server downloads pinned official source instead")
    args = parser.parse_args()
    out = args.out.resolve()
    if out.exists() or Path(str(out) + ".sha256").exists():
        parser.error("output already exists; choose a new path")
    if not args.without_pg_source and (not args.pg_source.is_file() or digest(args.pg_source) != PG_SHA256):
        parser.error("supply the official PG 16.2 archive with --pg-source or use --without-pg-source")
    published, tracked_outputs = anonymous_source.inventory(ROOT)
    errors = anonymous_source.check(ROOT, published)
    if tracked_outputs or errors:
        parser.error("Run scripts/anonymous_source.py --check and resolve publication issues first")
    # Include actual working-tree bytes, including user changes and new source files;
    # honor ignored files and deletions. Never copy the working .git directory.
    files = {}
    allowed = {"src", "test", "tools", "extension", "third_party", "cmake", "scripts", "benchmark", ".github", "auto_test"}
    excluded = {"__pycache__", "results", "node_modules", ".DS_Store"}
    for name in published:
        if not name:
            continue
        p = Path(name)
        if (len(p.parts) > 1 and p.parts[0] not in allowed) or any(part in excluded for part in p.parts):
            continue
        file = ROOT / p
        if not file.is_file() or file == out:
            continue
        if file.is_symlink():
            # Materialize only links whose target stays within the source checkout.
            file.resolve().relative_to(ROOT)
        if file.stat().st_size > 25 * 1024 * 1024:
            raise ValueError("unexpected large source file (not a database bundle): " + name)
        files[name] = file
    if not args.without_pg_source:
        files["vendor/postgresql-16.2.tar.gz"] = args.pg_source.resolve()
    manifest = {"format": "outeryan.pg_study.source.v1",
                "version": "v0.0.1-0-g0000000000",
                "created_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "source_policy": "current working-tree bytes; deleted files omitted; no .git, benchmark databases, root data directory, results, or binaries",
                "files": {name: digest(file) for name, file in files.items()}}
    out.parent.mkdir(parents=True, exist_ok=True)
    temporary = out.with_name(out.name + ".partial")
    with temporary.open("xb") as target:
        with tarfile.open(fileobj=target, mode="w:gz", dereference=True) as archive:
            for name, file in files.items():
                archive.add(file, arcname="outeryan/" + name, recursive=False, filter=anonymous_metadata)
                if digest(file) != manifest["files"][name]:
                    raise ValueError("source changed during packaging: " + name)
            body = (json.dumps(manifest, indent=2) + "\n").encode()
            info = tarfile.TarInfo("outeryan/bundle_manifest.json")
            info.size, info.mode = len(body), 0o644
            archive.addfile(info, io.BytesIO(body))
    temporary.replace(out)
    checksum = digest(out)
    Path(str(out) + ".sha256").write_text(checksum + "  " + out.name + "\n")
    print(f"{out}\n{out.stat().st_size / 1024**2:.1f} MiB; {len(files)} files\nSHA256 {checksum}")


if __name__ == "__main__":
    main()
