#!/usr/bin/env python3
"""Validate forced distinct-grouping candidates; these are not default-ON timings."""
import argparse
from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess

from query_variants import strip_outer_order_limit


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', type=Path, required=True)
    parser.add_argument('--duckdb', type=Path, required=True)
    parser.add_argument('--runner', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--queries', nargs='+', required=True, help='e.g. tpch_q10 tpcds_40')
    parser.add_argument('--variants', type=Path,
                        help='JSON map from query name to canonical source and exact predicate replacements')
    parser.add_argument('--timeout', type=int, default=650)
    args = parser.parse_args()
    args.repo = args.repo.resolve()
    args.duckdb = args.duckdb.resolve()
    args.runner = args.runner.resolve()
    args.out = args.out.resolve()
    args.out.mkdir(parents=True, exist_ok=False)
    def fingerprint(path):
        state = path.stat()
        return {'path': str(path), 'size': state.st_size, 'mtime_ns': state.st_mtime_ns}

    engine = [args.duckdb, args.runner]
    engine += [path for path in (args.duckdb.parent / 'src').glob('libduckdb.*')
               if path.suffix in ('.so', '.dylib')]
    environment = {'engine': [{**fingerprint(path), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}
                              for path in engine],
                   'database': {family: fingerprint(args.repo / (family + '_db'))
                                for family in sorted({name.split('_')[0] for name in args.queries})}}
    (args.out / 'environment.json').write_text(json.dumps(environment, indent=2) + '\n')
    clean_env = {key: value for key, value in os.environ.items()
                 if not key.startswith(('DUCKDB_OY', 'DUCKDB_SJ'))}
    summary = {}
    variants = json.loads(args.variants.read_text()) if args.variants else {}

    def save():
        (args.out / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')

    for name in args.queries:
        family, query_id = name.split('_', 1)
        if name in variants:
            relative = variants[name]['source']
            if Path(relative).is_absolute() or '..' in Path(relative).parts:
                raise ValueError('variant source must be relative to the repository')
        elif family == 'tpch' and re.fullmatch(r'q\d+', query_id):
            relative = f'extension/tpch/dbgen/queries/{query_id}.sql'
        elif family == 'tpcds' and re.fullmatch(r'\d+', query_id):
            relative = f'extension/tpcds/dsdgen/queries/{query_id}.sql'
        elif family == 'job' and re.fullmatch(r'\d+[a-z]', query_id):
            relative = f'benchmark/imdb_plan_cost/queries/{query_id}.sql'
        else:
            raise ValueError('unsupported query identifier: ' + name)
        directory = args.out / name
        directory.mkdir()
        original = (args.repo / relative).read_bytes()
        tracked = subprocess.check_output(['git', '-C', str(args.repo), 'show', 'HEAD:' + relative])
        if original != tracked:
            raise ValueError('canonical SQL differs from HEAD: ' + relative)
        query, transformation = strip_outer_order_limit(original.decode())
        replacements = variants.get(name, {}).get('replacements', [])
        for old, new in replacements:
            if query.count(old) != 1:
                raise ValueError('predicate replacement must match exactly once: ' + old)
            query = query.replace(old, new)
        query_path = directory / 'query.sql'
        query_path.write_text(query)
        row = {'source': relative, 'source_sha256': hashlib.sha256(original).hexdigest(),
               'query_sha256': hashlib.sha256(query.encode()).hexdigest(),
               'transformation': transformation, 'modes': {},
               'predicate_replacements': replacements,
               'purpose': 'forced-candidate correctness diagnostic; profiled/exported times are not benchmark results'}
        summary[name] = row
        database = args.repo / (family + '_db')
        trace_path = directory / 'normal.trace'
        sql = "SET threads=1; SET memory_limit='4GB'; SET disabled_optimizers='';\nEXPLAIN (FORMAT JSON) " + query
        try:
            normal = subprocess.run([str(args.duckdb), str(database), '-readonly', '-init', os.devnull,
                                     '-batch', '-bail'], input=sql, text=True, capture_output=True,
                                    timeout=90, env={**clean_env, 'DUCKDB_OYTRACE': str(trace_path)})
        except subprocess.TimeoutExpired:
            row['status'] = 'normal_explain_timeout'
            save()
            continue
        (directory / 'normal.explain.txt').write_text(normal.stdout)
        (directory / 'normal.log').write_text(normal.stderr)
        decisions = [line for line in (trace_path.read_text() if trace_path.exists() else '').splitlines()
                     if line.startswith('[OY_DECISION] ')]
        if normal.returncode or len(decisions) != 1:
            row['status'] = 'normal_explain_failed'
            save()
            continue
        row['normal_decision'] = dict(re.findall(r'(\w+)=(\S+)', decisions[0]))
        if row['normal_decision'].get('outer_reordered') != '1':
            row['status'] = 'no_distinct_grouping_candidate'
            save()
            print(name, row['status'], flush=True)
            continue
        for mode in ('OFF', 'CANDIDATE'):
            profile = directory / (mode + '.profile.json')
            rows = directory / (mode + '.rows.jsonl')
            env = dict(clean_env)
            if mode == 'CANDIDATE':
                env['DUCKDB_OY_FORCE_CANDIDATE'] = '1'
            # Trace is unnecessary here and can itself assert on unsupported
            # aggregate bindings. The real execution still has to succeed.
            command = [str(args.runner), str(database), str(query_path),
                       'OFF' if mode == 'OFF' else 'ON', str(profile), str(rows)]
            print('RUN', name, mode, flush=True)
            with (directory / (mode + '.log')).open('w') as log:
                try:
                    completed = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT,
                                               env=env, timeout=args.timeout)
                    outcome = {'returncode': completed.returncode}
                except subprocess.TimeoutExpired:
                    outcome = {'status': 'timeout'}
            row['modes'][mode] = outcome
            if outcome.get('returncode') != 0:
                row['status'] = mode.lower() + '_failed'
                break
            log_text = (directory / (mode + '.log')).read_text()
            markers = [line[len('[BARE_RUN] '):] for line in log_text.splitlines()
                       if line.startswith('[BARE_RUN] ')]
            if len(markers) != 1:
                row['status'] = mode.lower() + '_missing_completion'
                break
            outcome['run'] = json.loads(markers[0])
            save()
        else:
            # Unordered bags retain duplicates. A mismatch remains unresolved,
            # including floating-point differences requiring separate review.
            def bag(mode):
                with (directory / (mode + '.rows.jsonl')).open() as rows:
                    return Counter(rows)
            row['exact_result_bags_equal'] = (
                row['modes']['OFF']['run']['types'] == row['modes']['CANDIDATE']['run']['types']
                and bag('OFF') == bag('CANDIDATE'))
            row['status'] = 'exact_match' if row['exact_result_bags_equal'] else 'result_mismatch'
        save()
        print(name, row['status'], flush=True)
    for state in environment['database'].values():
        if fingerprint(Path(state['path'])) != state:
            raise ValueError('source database changed during validation')
    for state in environment['engine']:
        if hashlib.sha256(Path(state['path']).read_bytes()).hexdigest() != state['sha256']:
            raise ValueError('engine changed during validation')


if __name__ == '__main__':
    main()
