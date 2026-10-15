#!/usr/bin/env python3
"""Validate and measure only the two additional JOB examples on cpu8."""
import argparse
import fcntl
import json
import math
import os
from pathlib import Path
import platform
import signal
import statistics
import subprocess
import tempfile
import time

from capture_additional import SPECS
from fair_baseline import query_sha256
from plans import decision, duck_tree, nodes, replay_verified, semantic, sha256
from run import clean_and_sort, duck_env


def save(path, value):
    path.write_text(json.dumps(value, indent=2) + '\n')


def snapshot(path):
    stat = path.stat()
    return {'path': str(path.resolve()), 'size': stat.st_size, 'mtime_ns': stat.st_mtime_ns,
            'wal_exists': Path(str(path) + '.wal').exists()}


def interrupt(signum, _frame):
    raise KeyboardInterrupt('interrupted by signal ' + str(signum))


def stop_private_postgres(pg_bin_dir, pgdata):
    """Finish cleanup even when a second Ctrl+C/SIGTERM arrives during pg_ctl."""
    saved = {sig: signal.signal(sig, signal.SIG_IGN) for sig in (signal.SIGINT, signal.SIGTERM)}
    try:
        subprocess.run([str(pg_bin_dir / 'pg_ctl'), '-D', str(pgdata), '-m', 'fast',
                        '-t', '60', '-w', 'stop'], check=True, timeout=90)
    finally:
        for sig, handler in saved.items():
            signal.signal(sig, handler)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('runner', 'job-db', 'capture', 'pg-bin-dir', 'pgdata', 'out'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--runs', type=int, default=5)
    args = parser.parse_args()
    if args.runs < 3:
        raise ValueError('at least three timed runs required')
    signal.signal(signal.SIGTERM, interrupt)
    for name in ('runner', 'job_db', 'capture', 'pg_bin_dir', 'pgdata', 'out'):
        setattr(args, name, getattr(args, name).expanduser().resolve())
    if (args.pgdata / 'PG_VERSION').read_text().strip() != '16':
        raise ValueError('expected the study PostgreSQL 16 cluster')
    args.out.mkdir(parents=True, exist_ok=False)
    modes = ['PG', 'native', 'OY']
    cases = ['case_c', 'case_d']
    original = snapshot(args.job_db)
    runner_hash = sha256(args.runner)
    save(args.out / 'environment.json', {
        'time_utc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
        'host': platform.node(), 'platform': platform.platform(),
        'database_before': original, 'runner_sha256': runner_hash,
        'pg_stream_client_sha256': sha256(args.pg_bin_dir / 'pg_bare_query'),
        'threads': 1, 'memory_limit': '4GB', 'runs': args.runs,
        'timing': 'steady clock around SendQuery and full Fetch drain; no profiling or row serialization',
        'selection': 'two targeted additional examples selected for stronger improvements',
    })
    summary = {}
    for case in cases:
        (args.out / case).mkdir()
        source = args.capture / case
        sql = (source / 'query.sql').read_text()
        artifact = json.loads((source / 'pg_replay.json').read_text())
        if artifact['query_sha256'] != query_sha256(sql):
            raise ValueError(case + ': PostgreSQL artifact/query identity mismatch')
        (args.out / case / 'query.sql').write_text(sql)
        save(args.out / case / 'pg_replay.json', artifact)
        summary[case] = {'query_sha256': query_sha256(sql),
                         'query_file_sha256': sha256(source / 'query.sql'),
                         'runs': {m: [] for m in modes}}

    def execute(case, mode, phase, profile=False, rows=False):
        dest = args.out / case
        profile_path = dest / (mode + '.profile.json')
        row_path = dest / (mode + '.csv')
        command = [str(args.runner), str(args.job_db), str(dest / 'query.sql'), mode,
                   str(dest / 'pg_replay.json') if mode == 'PG' else '-',
                   str(profile_path) if profile else '-', str(row_path) if rows else '-']
        env = duck_env(dest / 'outeryan.trace' if mode == 'OY' and profile else None)
        result = subprocess.run(command, capture_output=True, text=True, timeout=3600, env=env)
        (dest / (mode + '.' + phase + '.log')).write_text(result.stdout + result.stderr)
        if result.returncode:
            raise RuntimeError(f'{case} {mode} {phase} failed: {result.stderr[-2000:]}')
        records = [json.loads(line[len('[FAIR_RUN] '):]) for line in result.stdout.splitlines()
                   if line.startswith('[FAIR_RUN] ')]
        if len(records) != 1:
            raise RuntimeError('missing unique runner result')
        record = records[0]
        if (record['mode'] != mode or record['profiled'] != profile or record['rows_exported'] != rows or
                record['repaired_queries'] != (1 if mode == 'PG' else 0)):
            raise ValueError('runner executed an unexpected measurement configuration')
        if (type(record['rows']) is not int or record['rows'] < 0 or
                not math.isfinite(record['elapsed_ms']) or record['elapsed_ms'] <= 0):
            raise ValueError('invalid runner row count or timing')
        if mode == 'PG':
            replay_verified(result.stdout + result.stderr, 1)
        print(case, mode, phase, json.dumps(record), flush=True)
        return record

    # Full multiset validation precedes every reported timing. Profiling and
    # integer/NULL export share this separate, untimed validation execution.
    for case in cases:
        for mode in modes:
            record = execute(case, mode, 'validation', profile=True, rows=True)
            summary[case].setdefault('validation', {})[mode] = record
            profile = json.loads((args.out / case / (mode + '.profile.json')).read_text())
            if (query_sha256(profile['query_name']) != summary[case]['query_sha256'] or
                    len(profile['children']) != 1 or profile['rows_returned'] != record['rows']):
                raise ValueError('profile does not match the complete bare-query execution')
            tree = duck_tree(profile['children'][0], True)
            relations = [node['relation'] for node in nodes(tree) if node['op'] == 'scan']
            if len(relations) != len(SPECS[case]['tables']) or set(relations) != set(SPECS[case]['tables']):
                raise ValueError('profile has missing, duplicate or unexpected base-table leaves')
            joins = [node for node in nodes(tree) if node['op'] == 'join']
            summary[case].setdefault('plans', {})[mode] = {
                'tree': tree, 'semantic': semantic(tree),
                'real_join_input_rows': sum(node['input_rows'] for node in joins),
                'max_nonroot_intermediate_rows': max(node['output_rows'] for node in joins[1:]),
                'result_rows': profile['rows_returned'],
            }
            if mode == 'PG':
                artifact = json.loads((args.out / case / 'pg_replay.json').read_text())
                if semantic(tree) != semantic(artifact['tree']):
                    raise ValueError('replayed PG tree changed')
            if mode == 'OY':
                selected = decision((args.out / case / 'outeryan.trace').read_text())
                if selected.get('selected_plan') != 'OUTERYAN' or selected.get('cost_gate_applied') != '1':
                    raise ValueError('OuterYan was not selected by the normal cost gate')
                summary[case]['outeryan_decision'] = selected
            save(args.out / 'partial.json', summary)

    lock = (args.pgdata.parent / 'pg-study-reuse.lock').open('a')
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    if (args.pgdata / 'postmaster.pid').exists():
        raise RuntimeError('private PG cluster is already running')
    with tempfile.TemporaryDirectory(prefix='oypg-verify-') as socket:
        start_attempted = False
        try:
            start_attempted = True
            subprocess.run([str(args.pg_bin_dir / 'pg_ctl'), '-D', str(args.pgdata),
                            '-l', str(args.out / 'postgres.log'), '-o',
                            f"-h '' -k {socket} -p 55440 -c autovacuum=off", '-t', '60', '-w', 'start'],
                           check=True, timeout=90)
            for case in cases:
                dest = args.out / case
                env = {**os.environ, 'PGOPTIONS': '-c search_path=pgplan_job,pg_catalog -c max_parallel_workers_per_gather=0 -c statement_timeout=600000'}
                with (dest / 'query.sql').open('rb') as source, (dest / 'PG_native.csv').open('wb') as output:
                    result = subprocess.run([str(args.pg_bin_dir / 'pg_bare_query'), socket, '55440',
                                             'oy_study', 'postgres', '5'], stdin=source, stdout=output,
                                            stderr=subprocess.PIPE, timeout=650, env=env)
                (dest / 'PG_native.log').write_bytes(result.stderr)
                if result.returncode:
                    raise RuntimeError('native PostgreSQL correctness execution failed')
        finally:
            # pg_ctl may fail/interrupted after launching the postmaster. The
            # absent PID file was checked under the lock before this attempt.
            if start_attempted and (args.pgdata / 'postmaster.pid').exists():
                stop_private_postgres(args.pg_bin_dir, args.pgdata)
    fcntl.flock(lock, fcntl.LOCK_UN)
    for case in cases:
        files = {}
        for mode in modes + ['PG_native']:
            sorted_path, count = clean_and_sort(args.out / case / (mode + '.csv'), 600, columns=5)
            files[mode] = {'rows': count, 'sorted_csv_sha256': sha256(sorted_path)}
            if mode != 'PG':
                subprocess.run(['cmp', '-s', str(sorted_path), str(baseline)], check=True)
            else:
                baseline = sorted_path
        if len({value['rows'] for value in files.values()}) != 1:
            raise ValueError('correctness result counts differ')
        for mode in modes:
            if files[mode]['rows'] != summary[case]['validation'][mode]['rows']:
                raise ValueError('exported result file is incomplete')
        summary[case]['correctness'] = {'exact_four_way_multiset_equality': True, 'results': files}
        save(args.out / 'partial.json', summary)
        print(case, 'exact four-way multiset equality PASSED', flush=True)

    # One unprofiled warmup per mode, followed by rotating interleaved rounds.
    # Keep all execution sequential: concurrent tests distort CPU/memory costs.
    for case in cases:
        for mode in modes:
            record = execute(case, mode, 'warmup')
            if record['rows'] != summary[case]['correctness']['results'][mode]['rows']:
                raise ValueError('warmup returned a different result count')
        for round_index in range(args.runs):
            order = modes[round_index % 3:] + modes[:round_index % 3]
            for mode in order:
                record = execute(case, mode, f'run-{round_index + 1}')
                if record['rows'] != summary[case]['correctness']['results'][mode]['rows']:
                    raise ValueError('timed execution returned a different result count')
                summary[case]['runs'][mode].append(record['elapsed_ms'])
                save(args.out / 'partial.json', summary)
        summary[case]['median_ms'] = {mode: statistics.median(values) for mode, values in summary[case]['runs'].items()}
        medians = summary[case]['median_ms']
        summary[case]['speedups'] = {mode: medians[mode] / medians['OY'] for mode in ('PG', 'native')}
        print(case, 'FINAL', json.dumps({'median_ms': medians, 'speedups': summary[case]['speedups']}), flush=True)
    if snapshot(args.job_db) != original:
        raise ValueError('source database changed')
    if sha256(args.runner) != runner_hash:
        raise ValueError('runner binary changed during the measurement')
    save(args.out / 'summary.json', summary)
    save(args.out / 'database_after.json', snapshot(args.job_db))


if __name__ == '__main__':
    main()
