#!/usr/bin/env python3
"""Capture PG plans for unchanged, explicitly listed benchmark queries."""
import argparse
import fcntl
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import tempfile

from datasets import assert_unchanged, export_tables, fingerprint, ident
from fair_baseline import query_sha256 as simple_query_sha256
from postgres_runtime import stop_private_postgres
from plans import pg_tree, sha256
from run import DuckDB, write_json

ROOT = Path(__file__).resolve().parents[2]
SPECS = {
    'job17': {
        'family': 'job', 'source_benchmark': 'current benchmark, JOB 17a seed',
        'query': 'job/join__job__job_17a_movie_annotations__left_deep__irfl__4c344f38__sel_low.sql',
        'aliases': {'ci': 'cast_info', 'n': 'name', 't': 'title', 'mk': 'movie_keyword', 'k': 'keyword'},
        'columns': 6},
    'job20': {
        'family': 'job', 'source_benchmark': 'current benchmark, JOB 20a seed',
        'query': 'job/join__job__job_20a_skeleton__bushy__irlf__5fcbf753__sel_low.sql',
        'aliases': {'cc': 'complete_cast', 'cct1': 'comp_cast_type', 'cct2': 'comp_cast_type',
                    'ci': 'cast_info', 't': 'title'}, 'columns': 7},
    'tpch8': {
        'family': 'tpch', 'source_benchmark': 'current benchmark, TPC-H Q8 seed',
        'query': 'tpch/join__tpch__tpch_q08_market_share__bushy__frifl__dba94a3f__sel_low.sql',
        'aliases': {'n': 'nation', 'r': 'region', 'c': 'customer', 'p': 'part',
                    'o': 'orders', 'l': 'lineitem'}, 'columns': 10},
}


def load_specs(path):
    if path is None:
        return SPECS
    specs = json.loads(path.read_text())
    if not isinstance(specs, dict) or not specs:
        raise ValueError('expected a nonempty case manifest')
    for case, spec in specs.items():
        if not re.fullmatch(r'[a-zA-Z0-9_-]+', case):
            raise ValueError('invalid case identifier')
        if spec['family'] not in ('job', 'tpch', 'tpcds') or not spec['aliases']:
            raise ValueError('invalid family or alias inventory')
        for alias, relation in spec['aliases'].items():
            ident(alias)
            ident(relation)
        if type(spec['columns']) is not int or not 1 <= spec['columns'] <= 64:
            raise ValueError('unsupported result width')
        if not spec['query'] or not spec['source_benchmark']:
            raise ValueError('missing query provenance')
    return specs


def query_sha256(sql):
    # The corpus adds leading line comments. Replay hashes from the first SQL
    # token; keep the executed file unchanged and hash the same SELECT text.
    remaining = sql.replace('\r\n', '\n').replace('\r', '\n').lstrip()
    while remaining.startswith('--'):
        remaining = remaining.partition('\n')[2].lstrip()
    return simple_query_sha256(remaining)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', type=Path, default=ROOT)
    for option in ('duckdb', 'job-db', 'tpch-db', 'pg-bin-dir', 'pgdata', 'out'):
        parser.add_argument('--' + option, type=Path, required=True)
    parser.add_argument('--tpcds-db', type=Path)
    parser.add_argument('--specs', type=Path)
    parser.add_argument('--seed-capture', type=Path, action='append', required=True)
    parser.add_argument('--timeout', type=int, default=600)
    parser.add_argument('--load-timeout', type=int, default=3600)
    args = parser.parse_args()
    specs = load_specs(args.specs)
    families = sorted({spec['family'] for spec in specs.values()})
    for family in families:
        if getattr(args, family + '_db') is None:
            parser.error('--' + family + '-db is required by the case manifest')
    for key, value in vars(args).items():
        if isinstance(value, Path):
            setattr(args, key, value.resolve())
    args.out.mkdir(parents=True, exist_ok=False)
    signal.signal(signal.SIGTERM, lambda *_: (_ for _ in ()).throw(KeyboardInterrupt()))
    if (args.pgdata / 'PG_VERSION').read_text().strip() != '16':
        raise ValueError('expected the stopped private PostgreSQL 16 study cluster')
    lock = (args.pgdata.parent / 'pg-study-reuse.lock').open('a')
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    if (args.pgdata / 'postmaster.pid').exists():
        raise RuntimeError('private cluster is running; refusing to interrupt it')
    # Existing tables may be reused only from a recorded import of these same
    # unchanged DuckDB files. New imports are recorded before loading as well.
    trusted = {}
    for path in (p for seed in args.seed_capture for p in seed.resolve().rglob('data.json')):
        data = json.loads(path.read_text())
        if data.get('family') not in families:
            continue
        source = getattr(args, data['family'] + '_db')
        if data.get('source_db') == str(source) and data.get('source_files') == fingerprint(source):
            for table in data['tables']:
                trusted[(data['family'], table['relation'])] = table
    snapshots = {family: fingerprint(getattr(args, family + '_db')) for family in families}
    write_json(args.out / 'specs.json', specs)
    write_json(args.out / 'environment.json', {
        'databases': snapshots, 'duckdb_sha256': sha256(args.duckdb),
        'postgres_sha256': sha256(args.pg_bin_dir / 'postgres'),
        'seed_capture': [str(p.resolve()) for p in args.seed_capture], 'pgdata': str(args.pgdata),
        'data_policy': 'reuse full original tables, no sampling or generation'})
    with tempfile.TemporaryDirectory(prefix='oypg-bench-') as socket:
        start_attempted = False
        try:
            start_attempted = True
            subprocess.run([str(args.pg_bin_dir / 'pg_ctl'), '-D', str(args.pgdata), '-l',
                            str(args.out / 'postgres.log'), '-o',
                            f"-h '' -k {socket} -p 55440 -c autovacuum=off", '-w', 'start'],
                           check=True, timeout=90, env={**os.environ, 'PG_OJ_TRACE': '1'})

            def pg(sql, stem, timeout=None):
                (args.out / (stem + '.sql')).write_text(sql)
                result = subprocess.run([str(args.pg_bin_dir / 'psql'), '-X', '-w', '-h', socket,
                                         '-p', '55440', '-U', 'oy_study', '-d', 'postgres', '-qAt',
                                         '-v', 'ON_ERROR_STOP=1'], input=sql, text=True,
                                        capture_output=True, timeout=timeout or args.timeout)
                (args.out / (stem + '.stdout')).write_text(result.stdout)
                (args.out / (stem + '.log')).write_text(result.stderr)
                result.check_returncode()
                return result

            version = pg('SHOW server_version_num;', 'version').stdout.strip()
            if version != '160002':
                raise ValueError('expected PostgreSQL 16.2, got ' + version)
            for family in families:
                required = sorted({table for spec in specs.values() if spec['family'] == family
                                   for table in spec['aliases'].values()})
                setup = f'SET search_path=pgplan_{family},pg_catalog;\n'
                existing = set(pg("SELECT tablename FROM pg_tables WHERE schemaname='pgplan_" +
                                  family + "';", family + '-existing').stdout.splitlines())
                for table in required:
                    if table in existing:
                        if (family, table) not in trusted:
                            raise ValueError(f'existing table has no matching import provenance: {family}.{table}')
                        count = int(pg(setup + 'SELECT count(*) FROM ' + ident(table) + ';',
                                       family + '-' + table + '-reuse-count', args.load_timeout).stdout)
                        if count != trusted[(family, table)]['rows']:
                            raise ValueError('existing PG table row count changed: ' + table)
                missing = [table for table in required if table not in existing]
                if missing:
                    directory = args.out / family
                    directory.mkdir()
                    spec = {'family': family, 'tables': missing,
                            'source_benchmark': 'explicit unchanged benchmark case manifest',
                            'derivation': 'full original tables; query files are unchanged'}
                    data = export_tables(args, DuckDB(args), spec, directory, getattr(args, family + '_db'))
                    write_json(directory / 'data.json', data)
                    pg('CREATE SCHEMA IF NOT EXISTS ' + ident('pgplan_' + family) + ';', family + '-schema')
                    for table in data['tables']:
                        name = table['relation']
                        filename = str(directory / (name + '.csv')).replace("'", "''")
                        sql = setup + table['pg_ddl'] + '\n'
                        sql += f"\\copy {ident(name)} FROM '{filename}' WITH (FORMAT csv, HEADER true, NULL '\\N')\n"
                        print('IMPORT', family, name, table['rows'], flush=True)
                        pg(sql, family + '-' + name + '-load', args.load_timeout)
                        count = int(pg(setup + 'SELECT count(*) FROM ' + ident(name) + ';',
                                       family + '-' + name + '-count', args.load_timeout).stdout)
                        if count != table['rows']:
                            raise ValueError('import row count mismatch: ' + name)
                    assert_unchanged(data)
                # Refresh all referenced tables, including the existing ones.
                pg(setup + '\n'.join('ANALYZE ' + ident(t) + ';' for t in required),
                   family + '-analyze', args.load_timeout)
            summary = {}
            for case, spec in specs.items():
                directory = args.out / case
                directory.mkdir()
                source = args.repo / 'auto_test/outerjoin_benchmark/benchmark' / spec['query']
                sql = source.read_text()
                (directory / 'query.sql').write_text(sql)
                setup = f"SET search_path=pgplan_{spec['family']},pg_catalog; SET max_parallel_workers_per_gather=0; SET statement_timeout={args.timeout * 1000};\n"
                settings = pg(setup + "SELECT json_build_object('version_num',current_setting('server_version_num'), 'join_collapse_limit',current_setting('join_collapse_limit'), 'from_collapse_limit',current_setting('from_collapse_limit'), 'geqo_threshold',current_setting('geqo_threshold'), 'max_parallel_workers_per_gather',current_setting('max_parallel_workers_per_gather'), 'work_mem',current_setting('work_mem'));", case + '-settings')
                result = pg(setup + 'EXPLAIN (VERBOSE, FORMAT JSON, COSTS true) ' + sql, case + '-explain')
                explain = json.loads(result.stdout)
                counts, occurrences = {}, {}
                # Alias order is source scan order, independent of the PG
                # selected tree traversal (cct1/cct2 must remain distinct).
                for alias, relation in spec['aliases'].items():
                    occurrences[alias] = counts.get(relation, 0)
                    counts[relation] = occurrences[alias] + 1
                tree = pg_tree(explain[0]['Plan'], 'pgplan_' + spec['family'], spec['aliases'], occurrences)
                artifact = {'format': 'duckyan.pg_join_tree.v1', 'query_sha256': query_sha256(sql),
                            'query_sha256_canonicalization': 'duckyan.sql_text.v1',
                            'postgres': {'version_num': 160002,
                                         'settings': {'max_parallel_workers_per_gather': '0',
                                                      'search_path': 'pgplan_' + spec['family'] + ', pg_catalog'},
                                         'plan_schema': 'pgplan_' + spec['family'],
                                         'plan_data': spec['family'] + '-duckdb-full'},
                            'data_provenance': {'kind': 'existing_benchmark_full_tables', 'family': spec['family'],
                                                'source_db': str(getattr(args, spec['family'] + '_db')),
                                                'source_benchmark': spec['source_benchmark'],
                                                'query_sha256': query_sha256(sql)}, 'tree': tree}
                write_json(directory / 'pg_explain.json', explain)
                write_json(directory / 'pg_replay.json', artifact)
                (directory / 'pg_trace.log').write_text(result.stderr)
                summary[case] = {'source': str(source), 'query_file_sha256': sha256(source), 'tree': tree,
                                 'occurrences': occurrences, 'settings': json.loads(settings.stdout)}
                write_json(args.out / 'capture_summary.json', summary)
                print('CAPTURED', case, json.dumps(tree), flush=True)
            for family, snapshot in snapshots.items():
                if fingerprint(getattr(args, family + '_db')) != snapshot:
                    raise ValueError('source database changed')
        finally:
            if start_attempted and (args.pgdata / 'postmaster.pid').exists():
                stop_private_postgres(args.pg_bin_dir, args.pgdata)


if __name__ == '__main__':
    main()
