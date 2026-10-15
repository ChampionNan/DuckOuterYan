#!/usr/bin/env python3
"""Bounded exploratory PG/OY timings; finalists require independent validation."""
import argparse
import json
from pathlib import Path
import subprocess

from benchmark_pg import load_specs, query_sha256
from datasets import fingerprint
from plans import replay_verified, sha256
from run import duck_env, write_json


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('specs', 'runner', 'duckdb-lib', 'db-root', 'capture', 'out'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--timeout', type=int, default=90)
    args = parser.parse_args()
    specs = load_specs(args.specs)
    args.out.mkdir(parents=True, exist_ok=False)
    databases = {s['family']: args.db_root / (s['family'] + '_db') for s in specs.values()}
    before = {f: fingerprint(p) for f, p in databases.items()}
    binary = sha256(args.duckdb_lib)
    write_json(args.out / 'environment.json', {'databases': before, 'duckdb_lib_sha256': binary,
               'runner_sha256': sha256(args.runner), 'purpose': 'one-run screening, not final speedups',
               'timeout_seconds': args.timeout, 'threads': 1, 'memory_limit': '4GB'})
    if json.loads((args.capture / 'environment.json').read_text())['databases'] != before:
        raise ValueError('capture database identities differ')
    summary = {}
    for case, spec in specs.items():
        dest = args.out / case
        dest.mkdir()
        source = args.capture / case
        sql = (source / 'query.sql').read_text()
        if json.loads((source / 'pg_replay.json').read_text())['query_sha256'] != query_sha256(sql):
            raise ValueError('capture SQL hash mismatch')
        record = {'source': spec['query'], 'query_file_sha256': sha256(source / 'query.sql')}
        summary[case] = record
        for mode in ('OY', 'PG'):
            command = [str(args.runner), str(databases[spec['family']]), str(source / 'query.sql'), mode,
                       str(source / 'pg_replay.json') if mode == 'PG' else '-', '-', '-']
            try:
                result = subprocess.run(command, text=True, capture_output=True, timeout=args.timeout,
                                        env=duck_env(dest / 'OY.trace' if mode == 'OY' else None))
                (dest / (mode + '.log')).write_text(result.stdout + result.stderr)
                result.check_returncode()
                rows = [json.loads(s[len('[FAIR_RUN] '):]) for s in result.stdout.splitlines()
                        if s.startswith('[FAIR_RUN] ')]
                if len(rows) != 1:
                    raise ValueError('expected one measurement')
                if mode == 'PG':
                    replay_verified(result.stdout + result.stderr, 1)
                record[mode] = rows[0]
                print(case, mode, round(rows[0]['elapsed_ms'], 3), 'ms', rows[0]['rows'], 'rows', flush=True)
            except subprocess.TimeoutExpired:
                record[mode] = {'status': 'timeout', 'timeout_seconds': args.timeout}
                print(case, mode, 'TIMEOUT', flush=True)
            except Exception as error:
                record[mode] = {'status': 'error', 'error': str(error)}
                print(case, mode, 'ERROR', str(error), flush=True)
            write_json(args.out / 'summary.json', summary)
            if mode == 'OY' and 'elapsed_ms' not in record[mode]:
                break
        if all('elapsed_ms' in record.get(m, {}) for m in ('PG', 'OY')):
            record['row_counts_equal'] = record['PG']['rows'] == record['OY']['rows']
            record['exploratory_speedup'] = record['PG']['elapsed_ms'] / record['OY']['elapsed_ms']
            print(case, 'EXPLORATORY_RATIO', record['exploratory_speedup'], flush=True)
        write_json(args.out / 'summary.json', summary)
    if before != {f: fingerprint(p) for f, p in databases.items()} or binary != sha256(args.duckdb_lib):
        raise ValueError('environment changed')
    write_json(args.out / 'status.json', {'status': 'complete', 'environment_unchanged': True})


if __name__ == '__main__':
    main()
