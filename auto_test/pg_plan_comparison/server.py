#!/usr/bin/env python3
"""Build this OuterYan checkout and traced PG 16.2 on Linux, then run the study."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import tarfile

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
PG_VERSION = "16.2"
PG_SHA256 = "2b8201047ec81acd1bad29dba278d788e7891b9c3e8232eda16bb29dec8131c7"
PG_URL = "https://ftp.postgresql.org/pub/source/v16.2/postgresql-16.2.tar.gz"


def digest(path):
    h = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def run(argv, cwd=None, log=None, env=None):
    print("+ " + " ".join(map(str, argv)), flush=True)
    if log:
        with log.open("w") as output:
            result = subprocess.run(list(map(str, argv)), cwd=cwd, stdout=output,
                                    stderr=subprocess.STDOUT, env=env)
        if result.returncode:
            print(log.read_text(errors="replace")[-6000:], file=sys.stderr)
            raise RuntimeError("command failed; full log: " + str(log))
    else:
        subprocess.run(list(map(str, argv)), cwd=cwd, check=True, env=env)


def extract_pg(archive, parent):
    # A pinned official archive, also checked for traversal and special files.
    with tarfile.open(archive, "r:gz") as source:
        for member in source.getmembers():
            p = Path(member.name)
            if p.is_absolute() or ".." in p.parts or p.parts[0] != "postgresql-16.2":
                raise ValueError("unsafe PostgreSQL archive path")
            if not member.isfile() and not member.isdir():
                raise ValueError("unexpected link/device in PostgreSQL archive")
        source.extractall(parent)


def verify_bundle():
    path = ROOT / "bundle_manifest.json"
    if not path.exists():
        print("Using current checkout; no bundle manifest present.", flush=True)
        return None
    manifest = json.loads(path.read_text())
    for name, value in manifest["files"].items():
        file = ROOT / name
        if not file.is_file() or digest(file) != value:
            raise ValueError("bundle file missing/modified: " + name + "; create a new bundle after edits")
    print(f"Verified {len(manifest['files'])} bundled files.", flush=True)
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", nargs="?", choices=("all", "build", "run", "check"), default="all")
    parser.add_argument("--work-dir", type=Path, default=ROOT / "auto_test/results/pg-plan-comparison-work")
    parser.add_argument("--duckdb-build-dir", type=Path,
                        help="separate DuckDB build directory; defaults to WORK_DIR/duckdb-release")
    parser.add_argument("--jobs", type=int, default=2, help="compiler jobs; increase when RAM permits")
    parser.add_argument("--pg-source", type=Path, help="optional official PostgreSQL 16.2 tar.gz")
    args, forwarded = parser.parse_known_args()
    if forwarded[:1] == ["--"]:
        forwarded = forwarded[1:]
    if args.action in ("build", "check") and forwarded:
        parser.error("experiment flags apply only to all/run")
    if args.action in ("all", "run"):
        if not any(arg == "--out" or arg.startswith("--out=") for arg in forwarded):
            parser.error("provide --out NEW_RESULT_DIRECTORY")
        if any(arg.split("=", 1)[0] in {"--duckdb", "--pg-bin-dir"} for arg in forwarded):
            parser.error("server.sh uses its verified builds; use run.sh to supply other binaries")
    if args.jobs < 1:
        parser.error("jobs must be positive")
    if platform.system() != "Linux" or platform.machine() not in ("x86_64", "amd64"):
        parser.error("this entry point targets x86_64 Linux; use run.sh with local binaries on other platforms")
    if os.geteuid() == 0:
        parser.error("run as a regular user; PostgreSQL initdb refuses root")
    if sys.version_info < (3, 9):
        parser.error("Python 3.9 or newer is required")
    dependencies = ["cmake", "ninja", "make", "cc", "c++", "patch", "sort"]
    missing = [name for name in dependencies if not shutil.which(name)]
    if missing:
        parser.error("missing tools: " + ", ".join(missing) + ". Debian/Ubuntu packages: "
                     "build-essential cmake ninja-build python3 patch curl; RHEL: gcc gcc-c++ make cmake ninja-build python3 patch curl")
    manifest = verify_bundle()
    print("OuterYan source: " + str(ROOT), flush=True)
    if args.action == "check":
        print("Dependencies and source bundle verified. Graphviz 'dot' is optional.")
        return
    work = args.work_dir.resolve()
    work.mkdir(parents=True, exist_ok=True)
    build = args.duckdb_build_dir.resolve() if args.duckdb_build_dir else work / "duckdb-release"
    prefix = work / "pg-install"
    cache = build / "CMakeCache.txt"
    if cache.exists():
        for line in cache.read_text().splitlines():
            if line.startswith("CMAKE_HOME_DIRECTORY:INTERNAL="):
                if Path(line.split("=", 1)[1]).resolve() != ROOT:
                    raise ValueError("DuckDB build directory belongs to another source tree; "
                                     "choose a new --duckdb-build-dir")
    print("DuckDB build directory: " + str(build), flush=True)
    logs = work / "build-logs"
    logs.mkdir(exist_ok=True)
    patch = HERE / "patches/postgresql-16.2-ojtrace.patch"
    env = os.environ.copy()
    # A source build must not inherit local experimental force knobs.
    for key in list(env):
        if key.startswith(("DUCKDB_OY", "DUCKDB_SJ")):
            del env[key]
    stamp = work / "build.json"
    identity = {"root": str(ROOT), "duckdb_build_dir": str(build),
                "machine": platform.machine(), "pg_patch_sha256": digest(patch),
                "pg_stream_source_sha256": digest(HERE / "pg_bare_query.c"),
                "manifest_sha256": digest(ROOT / "bundle_manifest.json") if manifest else None}
    if args.action in ("all", "build"):
        stamp.unlink(missing_ok=True)
        archive = args.pg_source.resolve() if args.pg_source else ROOT / "vendor/postgresql-16.2.tar.gz"
        if not archive.exists() and args.pg_source:
            raise ValueError("missing --pg-source: " + str(archive))
        if not archive.exists():
            archive = work / "postgresql-16.2.tar.gz"
            if not archive.exists():
                if not shutil.which("curl"):
                    raise ValueError("curl is required when the PG source tarball is not bundled")
                partial = archive.with_suffix(".partial")
                run(["curl", "--fail", "--location", "--retry", "3", "--proto", "=https", "-o", partial, PG_URL])
                partial.replace(archive)
        if digest(archive) != PG_SHA256:
            raise ValueError("PostgreSQL source SHA256 mismatch")
        source = work / "postgresql-16.2"
        pg_stamp = work / "pg-build.json"
        pg_identity = {"archive": PG_SHA256, "patch": digest(patch), "prefix": str(prefix)}
        if pg_stamp.exists() and json.loads(pg_stamp.read_text()) != pg_identity:
            raise ValueError("PG build inputs changed; use a new --work-dir")
        if not pg_stamp.exists():
            if source.exists():
                raise ValueError("incomplete PG build exists; retain logs and choose a new --work-dir")
            extract_pg(archive, work)
            run(["patch", "--batch", "--fuzz=0", "-p1", "-i", patch], cwd=source, log=logs / "pg-patch.log")
            run([source / "configure", "--prefix=" + str(prefix), "--without-readline", "--without-zlib", "--without-icu"],
                cwd=source, log=logs / "pg-configure.log", env=env)
            run(["make", "-j", args.jobs], cwd=source, log=logs / "pg-make.log", env=env)
            run(["make", "install"], cwd=source, log=logs / "pg-install.log", env=env)
            pg_stamp.write_text(json.dumps(pg_identity, indent=2) + "\n")
        run(["cc", "-O2", "-std=c11", "-Wall", "-Wextra", "-Werror", "-I", prefix / "include",
             HERE / "pg_bare_query.c", "-L", prefix / "lib", "-Wl,-rpath," + str(prefix / "lib"),
             "-lpq", "-o", prefix / "bin/pg_bare_query"], log=logs / "pg-stream-build.log", env=env)
        options = ["cmake", "-S", ROOT, "-B", build, "-G", "Ninja", "-DCMAKE_BUILD_TYPE=Release",
                   "-DBUILD_UNITTESTS=ON"]
        if manifest:
            options += ["-DOVERRIDE_GIT_DESCRIBE=" + manifest["version"]]
        run(options, log=logs / "duckdb-configure.log", env=env)
        run(["cmake", "--build", build, "--target", "duckdb", "unittest", "-j", args.jobs],
            log=logs / "duckdb-build.log", env=env)
        run([build / "test/unittest", "[pgplan]"], cwd=ROOT, log=logs / "pgplan-tests.log", env=env)
        run([sys.executable, "-m", "unittest", "discover", "-s", HERE, "-p", "test_*.py"],
            cwd=ROOT, log=logs / "harness-tests.log", env={**env, "PGPLAN_TEST_PG_BIN_DIR": str(prefix / "bin")})
        identity.update(duckdb_sha256=digest(build / "duckdb"), pg_sha256=digest(prefix / "bin/postgres"),
                        pg_stream_sha256=digest(prefix / "bin/pg_bare_query"))
        stamp.write_text(json.dumps(identity, indent=2) + "\n")
    if args.action in ("all", "run"):
        if not stamp.exists():
            raise ValueError("build first with server.sh build (or use all)")
        saved = json.loads(stamp.read_text())
        if any(saved.get(k) != v for k, v in identity.items()):
            raise ValueError("build does not match this source/build configuration; run all/build first")
        if saved["duckdb_sha256"] != digest(build / "duckdb") or saved["pg_sha256"] != digest(prefix / "bin/postgres"):
            raise ValueError("binaries changed after verified build")
        if saved["pg_stream_sha256"] != digest(prefix / "bin/pg_bare_query"):
            raise ValueError("PG result streaming client changed after verified build")
        if not any(arg == "--out" or arg.startswith("--out=") for arg in forwarded):
            parser.error("provide --out NEW_RESULT_DIRECTORY")
        run([sys.executable, HERE / "run.py", "--duckdb", build / "duckdb", "--pg-bin-dir", prefix / "bin", *forwarded],
            cwd=ROOT, env=env)


if __name__ == "__main__":
    try:
        main()
    except (ValueError, RuntimeError, OSError, subprocess.CalledProcessError) as error:
        sys.exit("ERROR: " + str(error))
