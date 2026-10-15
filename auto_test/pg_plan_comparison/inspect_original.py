#!/usr/bin/env python3
"""Inspect unchanged benchmark SQL files; optionally cover all three suites."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess

from query_variants import strip_outer_order_limit


def sha(data):
    return hashlib.sha256(data).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', type=Path, required=True)
    parser.add_argument('--duckdb', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--all', action='store_true', help='inspect all 113 JOB, 22 TPC-H and 99 TPC-DS files')
    parser.add_argument('--timeout', type=int, default=90, help='per-mode EXPLAIN timeout in seconds')
    parser.add_argument('--strip-outer-order-limit', action='store_true',
                        help='remove only the terminal outer ORDER BY/LIMIT, preserving all predicates and inner query blocks')
    args = parser.parse_args()
    args.repo = args.repo.resolve()
    args.duckdb = args.duckdb.resolve()
    args.out = args.out.resolve()
    args.out.mkdir(parents=True, exist_ok=False)
    queries = [('tpcds_' + q, 'tpcds_db', f'extension/tpcds/dsdgen/queries/{q}.sql')
               for q in ('05', '40', '49', '51', '72', '75', '77', '78', '80', '93', '97')]
    queries += [('tpch_13', 'tpch_db', 'extension/tpch/dbgen/queries/q13.sql')]
    queries += [('job_' + q, 'job_db', f'benchmark/imdb_plan_cost/queries/{q}.sql')
                for q in ('03c', '11a', '21a', '32a', '32b')]
    if args.all:
        queries = []
        for family, database, relative_dir, expected in (
                ('job', 'job_db', 'benchmark/imdb_plan_cost/queries', 113),
                ('tpch', 'tpch_db', 'extension/tpch/dbgen/queries', 22),
                ('tpcds', 'tpcds_db', 'extension/tpcds/dsdgen/queries', 99)):
            sources = sorted((args.repo / relative_dir).glob('*.sql'))
            if len(sources) != expected:
                raise ValueError(f'{family}: expected {expected} original queries, found {len(sources)}')
            queries.extend((family + '_' + source.stem, database, str(source.relative_to(args.repo))) for source in sources)
    def database_state():
        paths = [args.repo / name for name in ('job_db', 'tpch_db', 'tpcds_db')]
        paths += [Path(str(path) + '.wal') for path in paths]
        return {str(path): {'size': path.stat().st_size, 'mtime_ns': path.stat().st_mtime_ns}
                if path.exists() else None for path in paths}
    before = database_state()
    metadata = {'purpose': 'original-SQL plan eligibility, not a timing benchmark',
                'revision': subprocess.check_output(['git', '-C', str(args.repo), 'rev-parse', 'HEAD'], text=True).strip(),
                'binary': str(args.duckdb), 'binary_sha256': sha(args.duckdb.read_bytes()),
                'threads': 1, 'memory_limit': '4GB', 'database_before': before,
                'all_original_queries': args.all, 'query_count': len(queries), 'timeout_s': args.timeout,
                'strip_outer_order_limit': args.strip_outer_order_limit}
    (args.out / 'environment.json').write_text(json.dumps(metadata, indent=2) + '\n')
    env = {key: value for key, value in os.environ.items() if not key.startswith(('DUCKDB_OY', 'DUCKDB_SJ'))}
    summary = {}
    for index, (name, db, relative) in enumerate(queries):
        directory = args.out / name
        directory.mkdir()
        raw = (args.repo / relative).read_bytes()
        tracked = subprocess.check_output(['git', '-C', str(args.repo), 'show', 'HEAD:' + relative])
        if raw != tracked:
            raise ValueError('canonical SQL differs from HEAD: ' + relative)
        original = raw
        transformation = {'changed': False, 'removed_suffix': ''}
        if args.strip_outer_order_limit:
            transformed, transformation = strip_outer_order_limit(raw.decode())
            raw = transformed.encode()
            (directory / 'original.sql').write_bytes(original)
        (directory / 'query.sql').write_bytes(raw)
        row = {'source': str(args.repo / relative), 'sha256': sha(raw), 'source_sha256': sha(original),
               'byte_identical_to_head': raw == original, 'source_byte_identical_to_head': True,
               'transformation': transformation, 'mode_status': {}}
        trees = {}
        for mode in ('DuckDB', 'OuterYan'):
            trace = directory / (mode + '.trace')
            setup = "SET threads=1; SET memory_limit='4GB'; SET disabled_optimizers='"
            setup += ('outer_yan' if mode == 'DuckDB' else '') + "';\n"
            sql = setup.encode() + b'EXPLAIN (FORMAT JSON) ' + raw
            (directory / (mode + '.explain.sql')).write_bytes(sql)
            try:
                completed = subprocess.run([str(args.duckdb), str(args.repo / db), '-readonly', '-init', os.devnull,
                                            '-batch', '-bail'], input=sql, capture_output=True,
                                           env={**env, 'DUCKDB_OYTRACE': str(trace)}, timeout=args.timeout)
            except subprocess.TimeoutExpired as error:
                (directory / (mode + '.explain.txt')).write_bytes(error.stdout or b'')
                (directory / (mode + '.log')).write_bytes(error.stderr or b'')
                row['mode_status'][mode] = 'timeout'
                continue
            (directory / (mode + '.explain.txt')).write_bytes(completed.stdout)
            (directory / (mode + '.log')).write_bytes(completed.stderr)
            if completed.returncode:
                row['mode_status'][mode] = 'error'
                row.setdefault('errors', {})[mode] = completed.stderr.decode(errors='replace')[-2000:]
                continue
            output = completed.stdout.decode()
            try:
                trees[mode] = json.loads(output[output.index('[\n'):])
                row['mode_status'][mode] = 'ok'
            except (ValueError, json.JSONDecodeError) as error:
                row['mode_status'][mode] = 'unreadable_plan'
                row.setdefault('errors', {})[mode] = str(error)
        trace_path = directory / 'OuterYan.trace'
        decisions = [line for line in (trace_path.read_text() if trace_path.exists() else '').splitlines()
                     if line.startswith('[OY_DECISION] ')]
        row['decision_count'] = len(decisions)
        if len(decisions) == 1:
            fields = dict(re.findall(r'(\w+)=(\S+)', decisions[0]))
            row.update(selected_plan=fields['selected_plan'], reason=fields['reason'], decision=fields)
        else:
            row.update(selected_plan='UNKNOWN', reason='NO_UNIQUE_DECISION')
        row['physical_explain_exact_equal'] = trees['DuckDB'] == trees['OuterYan'] if len(trees) == 2 else None
        row['root_operator'] = trees['OuterYan'][0]['name'] if 'OuterYan' in trees else None
        if original != (args.repo / relative).read_bytes():
            raise ValueError('query changed during inspection')
        summary[name] = row
        (args.out / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
        if not args.all or (index + 1) % 10 == 0 or row['reason'] != 'INAPPLICABLE':
            print(f'{index + 1}/{len(queries)}', name, row['selected_plan'], row['reason'],
                  'identical_plan=' + str(row['physical_explain_exact_equal']), flush=True)
    if database_state() != before or sha(args.duckdb.read_bytes()) != metadata['binary_sha256']:
        raise ValueError('source database or binary changed during inspection')
    (args.out / 'database_after.json').write_text(json.dumps(database_state(), indent=2) + '\n')
    final = {'status': 'complete', 'queries': len(summary),
             'all_modes_succeeded': all(all(value == 'ok' for value in row['mode_status'].values()) for row in summary.values()),
             'all_physical_plans_equal': all(row['physical_explain_exact_equal'] for row in summary.values()),
             'outeryan_selected': [name for name, row in summary.items() if row['selected_plan'] == 'OUTERYAN'],
             'different_plans': [name for name, row in summary.items() if row['physical_explain_exact_equal'] is False],
             'unresolved': [name for name, row in summary.items() if row['physical_explain_exact_equal'] is None]}
    (args.out / 'status.json').write_text(json.dumps(final, indent=2) + '\n')
    print(json.dumps(final), flush=True)


if __name__ == '__main__':
    main()
