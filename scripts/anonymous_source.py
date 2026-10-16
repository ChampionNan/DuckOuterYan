#!/usr/bin/env python3
"""Check or export the current source tree without outputs or Git metadata."""
import argparse
import csv
import io
import json
from pathlib import Path
import re
import subprocess
import tarfile


ROOT = Path(__file__).resolve().parents[1]
MEASUREMENT_FIELDS = frozenset("""tm_off tm_on tm_speedup duckdb_s outeryan_s speedup
historical_duckdb_s historical_outeryan_s historical_speedup
reference_duckdb_s reference_outeryan_s reference_off_s reference_on_s
old_speedup_reference_only new_speedup measurement_snapshot
observed_tm_speedup historical_full_join_tm_speedup historical_v1_observed_tm_speedup
""".split())
PERSONAL_PATH = re.compile(r"/(?:Users|home)/[^\s/\"'<>]+(?:/[^\s\"'<>]*)?")
EMAIL = re.compile(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}")
HOST = re.compile(r"\b[\w-]+\.(?:cse\.[\w.-]+\.[a-z]{2,}|[\w.-]+\.(?:edu|ac\.[a-z]+|edu\.[a-z]+))\b")


def git(root, *args, data=None):
    return subprocess.run(["git", "-C", str(root), *args], input=data,
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True).stdout


def inventory(root):
    tracked = set(git(root, "ls-files", "-z").decode().split("\0")) - {""}
    others = set(git(root, "ls-files", "--others", "--exclude-standard", "-z").decode().split("\0")) - {""}
    candidates = sorted(tracked | others)
    result = subprocess.run(
        ["git", "-C", str(root), "check-ignore", "--no-index", "-z", "--stdin"],
        input=("\0".join(candidates) + "\0").encode(), stdout=subprocess.PIPE,
        stderr=subprocess.PIPE)
    if result.returncode not in (0, 1):
        raise RuntimeError(result.stderr.decode())
    ignored = set(result.stdout.decode().split("\0")) - {""}
    files = [p for p in candidates if p not in ignored and
             ((root / p).is_file() or (root / p).is_symlink())]
    return files, sorted(tracked & ignored)


def first_party(path):
    return path in {"README.md", "AUTHORS"} or path.startswith((
        "auto_test/", "src/optimizer/outer_yan/", "src/include/duckdb/optimizer/outer_yan/"))


def measurement_keys(value):
    if isinstance(value, dict):
        for key, child in value.items():
            if key in MEASUREMENT_FIELDS:
                yield key
            yield from measurement_keys(child)
    elif isinstance(value, list):
        for child in value:
            yield from measurement_keys(child)


def check(root, files):
    errors = []
    root = root.resolve()
    for name in files:
        path = root / name
        if ".git" in Path(name).parts:
            errors.append(name + ": Git metadata cannot be published")
            continue
        if path.is_symlink():
            target = path.readlink()
            resolved = (path.parent / target).resolve()
            if target.is_absolute() or root not in resolved.parents:
                errors.append(name + ": symlink escapes the source tree")
            continue
        if not first_party(name) or path.name in {"LICENSE", "COPYING"}:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            errors.append(name + ": unexpected binary in research sources")
            continue
        for label, pattern in (("personal absolute path", PERSONAL_PATH), ("email address", EMAIL),
                               ("institutional hostname", HOST)):
            # Public dataset attribution is required for reproducibility.
            inspected = text.replace("https://snap.stanford.edu", "PUBLIC_DATASET")
            if pattern.search(inspected):
                errors.append(name + ": " + label)
        if name.startswith("auto_test/") and path.suffix in {".json", ".csv"}:
            if path.suffix == ".json":
                keys = set(measurement_keys(json.loads(text)))
            else:
                keys = set(next(csv.reader(io.StringIO(text)), ())) & MEASUREMENT_FIELDS
            if keys:
                errors.append(name + ": experimental fields: " + ", ".join(sorted(keys)))
    return errors


def export(root, files, destination):
    """Write only the checked inventory, with neutral archive ownership metadata."""
    destination = destination.resolve()
    if destination.exists():
        raise FileExistsError("Refusing to overwrite " + str(destination))
    if root.resolve() in destination.parents:
        result = subprocess.run(["git", "-C", str(root), "check-ignore", "--no-index", "-q",
                                 "--", str(destination)], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if result.returncode != 0:
            raise ValueError("Source archives must be ignored or written outside the repository")
    destination.parent.mkdir(parents=True, exist_ok=True)
    created = False
    try:
        with destination.open("xb") as output:
            created = True
            with tarfile.open(fileobj=output, mode="w:gz") as archive:
                for name in files:
                    path = root / name
                    info = archive.gettarinfo(str(path), arcname="outeryan/" + name)
                    info.uid = info.gid = info.mtime = 0
                    info.uname = info.gname = ""
                    info.pax_headers = {}
                    if info.isfile():
                        with path.open("rb") as source:
                            archive.addfile(info, source)
                    else:
                        archive.addfile(info)
    except BaseException:
        if created:
            destination.unlink(missing_ok=True)
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    files, tracked_outputs = inventory(ROOT)
    errors = [name + ": ignored artifact is still tracked; remove this exact index entry"
              for name in tracked_outputs]
    errors.extend(check(ROOT, files))
    if errors:
        parser.exit(1, "\n".join(errors) + "\n")
    print("Checked {} publication files; no tracked ignored artifacts.".format(len(files)))
    if args.output:
        export(ROOT, files, args.output)
        print("Anonymous source archive: " + str(args.output.resolve()))


if __name__ == "__main__":
    main()
