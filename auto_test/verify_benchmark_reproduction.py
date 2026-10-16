#!/usr/bin/env python3
"""Regenerate twice in isolated directories and compare every published input byte.

This validates query reproduction, not equality of performance across machines.
No database or historical measurement files are needed by generation.
"""
import argparse
import contextlib
import io
from pathlib import Path
import tempfile

import balanced_benchmark as benchmark


def snapshot(path):
    # Finder metadata is not a published benchmark input.
    return {str(p.relative_to(path)): benchmark.digest(p) for p in sorted(path.rglob("*"))
            if p.is_file() and p.name != ".DS_Store"}


def verify():
    active = benchmark.ROOT / "benchmark"
    rows = benchmark.validate(active)
    original = snapshot(active)
    with tempfile.TemporaryDirectory(prefix="outeryan-reproduce-") as temp:
        for run in ("first", "second"):
            destination = Path(temp) / run
            with contextlib.redirect_stdout(io.StringIO()):
                benchmark.generate(destination)
            benchmark.validate(destination / "benchmark")
            generated = snapshot(destination / "benchmark")
            if original != generated:
                changed = sorted(k for k in set(original) | set(generated)
                                 if original.get(k) != generated.get(k))
                raise ValueError("Generated inputs differ from active benchmark: " + ", ".join(changed[:10]))
    return dict(query_count=len(rows), generations=2, byte_identical=True,
                manifest_sha256=benchmark.digest(active / "manifest.csv"), files=original)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--validate-only", action="store_true", help="Read/validate existing inputs without generating SQL")
    args = parser.parse_args(argv)
    if args.validate_only:
        rows = benchmark.validate(benchmark.ROOT / "benchmark")
        print(f"Validated {len(rows)} committed queries; no query generation performed.")
        return
    result = verify()
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        benchmark.write_json(args.output, result)
    print(f"Reproduced {result['query_count']} queries twice; all {len(result['files'])} files byte-identical.")


if __name__ == "__main__":
    main()
