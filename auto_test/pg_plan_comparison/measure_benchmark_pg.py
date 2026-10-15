#!/usr/bin/env python3
"""Four-way correctness and same-engine timings for the three benchmark cases."""
import argparse
from collections import Counter
import fcntl
import json
import math
import os
from pathlib import Path
import platform
import re
import signal
import statistics
import subprocess
import tempfile
import time

from benchmark_pg import load_specs, query_sha256
from datasets import fingerprint
from measure_additional import interrupt, save, stop_private_postgres
from plans import decision, duck_tree, nodes, replay_verified, sha256
from run import duck_env


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('runner', 'duckdb-lib', 'job-db', 'tpch-db', 'capture', 'pg-bin-dir',
                 'pg-stream', 'pgdata', 'out'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--runs', type=int, default=5)
    parser.add_argument('--tpcds-db', type=Path)
    parser.add_argument('--specs', type=Path)
    args = parser.parse_args()
    specs = load_specs(args.specs)
    if args.runs < 3:
        raise ValueError('at least three timed runs required')
    signal.signal(signal.SIGTERM, interrupt)
    for key, value in vars(args).items():
        if isinstance(value, Path):
            setattr(args, key, value.expanduser().resolve())
    args.out.mkdir(parents=True, exist_ok=False)
    modes = ['PG', 'native', 'OY']
    cases = list(specs)
    families = sorted({spec['family'] for spec in specs.values()})
    databases = {family: getattr(args, family + '_db') for family in families}
    if any(path is None for path in databases.values()):
        parser.error('a database required by the case manifest is missing')
    before = {family: fingerprint(path) for family, path in databases.items()}
    engine = {str(path): sha256(path) for path in (args.runner, args.duckdb_lib, args.pg_stream,
                                                 args.pg_bin_dir / 'postgres')}
    capture_env = json.loads((args.capture / 'environment.json').read_text())
    if capture_env['databases'] != before:
        raise ValueError('databases differ from the PostgreSQL capture inputs')
    save(args.out / 'environment.json', {
        'time_utc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
        'host': platform.node(), 'platform': platform.platform(), 'databases': before,
        'engine': engine, 'threads': 1, 'memory_limit': '4GB', 'runs': args.runs,
        'warmups': 1, 'timing': 'SendQuery + full Fetch drain, no profile or serialization',
        'correctness': 'original bare SELECT, sorted full integer/text/NULL JSONL byte comparison',
        'capture': str(args.capture), 'pgdata': str(args.pgdata),
    })
    summary = {}
    for case in cases:
        dest, source = args.out / case, args.capture / case
        dest.mkdir()
        sql = (source / 'query.sql').read_text()
        artifact = json.loads((source / 'pg_replay.json').read_text())
        if artifact['query_sha256'] != query_sha256(sql):
            raise ValueError(case + ': artifact/query mismatch')
        (dest / 'query.sql').write_text(sql)
        save(dest / 'pg_replay.json', artifact)
        summary[case] = {'query_sha256': query_sha256(sql),
                         'query_file_sha256': sha256(source / 'query.sql'),
                         'runs': {mode: [] for mode in modes}}

    def execute(case, mode, phase, validate=False):
        dest = args.out / case
        command = [str(args.runner), str(databases[specs[case]['family']]), str(dest / 'query.sql'),
                   mode, str(dest / 'pg_replay.json') if mode == 'PG' else '-',
                   str(dest / (mode + '.profile.json')) if validate else '-',
                   str(dest / (mode + '.jsonl')) if validate else '-', 'jsonl']
        result = subprocess.run(command, capture_output=True, text=True, timeout=3600,
                                env=duck_env(dest / 'outeryan.trace' if mode == 'OY' and validate else None))
        log = result.stdout + result.stderr
        (dest / (mode + '.' + phase + '.log')).write_text(log)
        if result.returncode:
            raise RuntimeError(f'{case} {mode} {phase} failed: {log[-2000:]}')
        records = [json.loads(line[len('[FAIR_RUN] '):]) for line in result.stdout.splitlines()
                   if line.startswith('[FAIR_RUN] ')]
        if len(records) != 1:
            raise ValueError('expected one runner record')
        record = records[0]
        if (record['mode'] != mode or record['profiled'] != validate or record['rows_exported'] != validate
                or record['repaired_queries'] != (1 if mode == 'PG' else 0)
                or type(record['rows']) is not int or record['rows'] < 0
                or not math.isfinite(record['elapsed_ms']) or record['elapsed_ms'] <= 0
                or len(record['types']) != specs[case]['columns']):
            raise ValueError('unexpected runner execution or invalid measurement')
        if mode == 'PG':
            replay_verified(log, 1)
        print(case, mode, phase, json.dumps(record), flush=True)
        return record

    for case in cases:
        for mode in modes:
            record = execute(case, mode, 'validation', True)
            summary[case].setdefault('validation', {})[mode] = record
            profile = json.loads((args.out / case / (mode + '.profile.json')).read_text())
            if (query_sha256(profile['query_name']) != summary[case]['query_sha256']
                    or profile['rows_returned'] != record['rows'] or len(profile['children']) != 1):
                raise ValueError('profile differs from the bare-query execution')
            tree = duck_tree(profile['children'][0], True)
            relations = Counter(n['relation'] for n in nodes(tree) if n['op'] == 'scan')
            if relations != Counter(specs[case]['aliases'].values()):
                raise ValueError('missing or unexpected scan occurrences in profile')
            joins = [n for n in nodes(tree) if n['op'] == 'join']
            # Profile scan names alone cannot distinguish cct1/cct2. The C++
            # signature uses bound scan occurrences, independently of traversal.
            summary[case].setdefault('plans', {})[mode] = {
                'semantic_signature': record['semantic_signature'],
                'physical_tree_relation_names_only': tree,
                'real_join_input_rows': sum(n['input_rows'] for n in joins),
                'max_join_output_rows': max(n['output_rows'] for n in joins),
                'max_nonroot_intermediate_rows': max(n['output_rows'] for n in joins[1:]),
            }
            if mode == 'OY':
                trace = (args.out / case / 'outeryan.trace').read_text()
                # CALL enable_profiling is a separate setup statement and can
                # emit INAPPLICABLE before the one benchmark pipeline trace.
                if trace.count('# OuterYan pipeline trace') != 1:
                    raise ValueError('expected one benchmark OuterYan pipeline')
                chosen = decision(trace.split('# OuterYan pipeline trace', 1)[1])
                if chosen.get('selected_plan') != 'OUTERYAN' or chosen.get('cost_gate_applied') != '1':
                    raise ValueError('OuterYan not selected by normal gate')
                summary[case]['outeryan_decision'] = chosen
            save(args.out / 'partial.json', summary)
        if len({tuple(r['types']) for r in summary[case]['validation'].values()}) != 1:
            raise ValueError('result types differ across DuckDB modes')

    lock = (args.pgdata.parent / 'pg-study-reuse.lock').open('a')
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    if (args.pgdata / 'postmaster.pid').exists():
        raise RuntimeError('private PG cluster already running')
    with tempfile.TemporaryDirectory(prefix='oypg-verify-') as socket:
        attempted = False
        try:
            attempted = True
            subprocess.run([str(args.pg_bin_dir / 'pg_ctl'), '-D', str(args.pgdata), '-l',
                            str(args.out / 'postgres.log'), '-o',
                            f"-h '' -k {socket} -p 55440 -c autovacuum=off", '-t', '60', '-w', 'start'],
                           check=True, timeout=90)
            for case in cases:
                dest = args.out / case
                env = {**os.environ, 'PGOPTIONS': '-c search_path=pgplan_' + specs[case]['family'] +
                       ',pg_catalog -c max_parallel_workers_per_gather=0 -c statement_timeout=600000'}
                with (dest / 'query.sql').open('rb') as source, (dest / 'PG_native.jsonl').open('wb') as output:
                    result = subprocess.run([str(args.pg_stream), socket, '55440', 'oy_study', 'postgres',
                                             str(specs[case]['columns']), 'jsonl'], stdin=source,
                                            stdout=output, stderr=subprocess.PIPE, timeout=650, env=env)
                (dest / 'PG_native.log').write_bytes(result.stderr)
                if result.returncode or not re.search(rb'\[PGSTREAM\] rows=\d+ columns=\d+ completed=1', result.stderr):
                    raise RuntimeError('native PG correctness failed: ' + result.stderr.decode()[-1000:])
                print(case, 'PG native result export complete', flush=True)
        finally:
            if attempted and (args.pgdata / 'postmaster.pid').exists():
                stop_private_postgres(args.pg_bin_dir, args.pgdata)
    fcntl.flock(lock, fcntl.LOCK_UN)
    for case in cases:
        files = {}
        for mode in modes + ['PG_native']:
            path = args.out / case / (mode + '.jsonl')
            sorted_path = path.with_suffix('.sorted.jsonl')
            subprocess.run(['sort', '-o', str(sorted_path), str(path)],
                           env={**os.environ, 'LC_ALL': 'C'}, check=True, timeout=600)
            with path.open('rb') as stream:
                count = sum(1 for _ in stream)
            files[mode] = {'rows': count, 'sorted_jsonl_sha256': sha256(sorted_path)}
            if mode == 'PG':
                baseline = sorted_path
            else:
                subprocess.run(['cmp', '-s', str(baseline), str(sorted_path)], check=True)
            if mode in modes and count != summary[case]['validation'][mode]['rows']:
                raise ValueError('incomplete result export')
        if len({r['rows'] for r in files.values()}) != 1:
            raise ValueError('result counts differ')
        summary[case]['correctness'] = {'exact_four_way_multiset_equality': True, 'results': files}
        save(args.out / 'partial.json', summary)
        # Preserve complete comparison evidence and fingerprints, not gigabytes
        # of duplicated result exports once byte equality has been established.
        for mode in modes + ['PG_native']:
            (args.out / case / (mode + '.jsonl')).unlink()
            (args.out / case / (mode + '.sorted.jsonl')).unlink()
        print(case, 'exact four-way multiset equality PASSED', flush=True)

    for case in cases:
        expected_rows = summary[case]['correctness']['results']['PG']['rows']
        for mode in modes:
            if execute(case, mode, 'warmup')['rows'] != expected_rows:
                raise ValueError('warmup result count changed')
        for index in range(args.runs):
            order = modes[index % 3:] + modes[:index % 3]
            for mode in order:
                record = execute(case, mode, f'run-{index + 1}')
                if record['rows'] != expected_rows:
                    raise ValueError('timed result count changed')
                summary[case]['runs'][mode].append(record['elapsed_ms'])
                save(args.out / 'partial.json', summary)
        medians = {m: statistics.median(values) for m, values in summary[case]['runs'].items()}
        summary[case]['median_ms'] = medians
        summary[case]['speedups'] = {m: medians[m] / medians['OY'] for m in ('PG', 'native')}
        print(case, 'FINAL', json.dumps(medians), flush=True)
    if before != {family: fingerprint(path) for family, path in databases.items()}:
        raise ValueError('source databases changed')
    if engine != {path: sha256(Path(path)) for path in engine}:
        raise ValueError('measurement binaries changed')
    for case in cases:
        if sha256(args.out / case / 'query.sql') != summary[case]['query_file_sha256']:
            raise ValueError('query file changed')
    save(args.out / 'summary.json', summary)
    save(args.out / 'status.json', {'status': 'complete', 'environment_unchanged': True})


if __name__ == '__main__':
    main()
