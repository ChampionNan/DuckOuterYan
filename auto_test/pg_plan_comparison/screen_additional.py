#!/usr/bin/env python3
"""Screen a named, bounded set of additional queries using the native baseline."""
import argparse
import json
import os
from pathlib import Path
import subprocess

from plans import decision, duck_tree, grouping, nodes, semantic, sha256


def literal(value):
    return "'" + str(value).replace("'", "''") + "'"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--duckdb', type=Path, required=True)
    parser.add_argument('--db', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--queries', type=Path, nargs='+', required=True)
    parser.add_argument('--timeout', type=int, default=600)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=False)
    env = {k: v for k, v in os.environ.items() if not k.startswith(('DUCKDB_OY', 'DUCKDB_SJ'))}
    before = args.db.stat()
    records = {}
    metadata = {'binary': str(args.duckdb), 'binary_sha256': sha256(args.duckdb),
                'database': str(args.db), 'size': before.st_size, 'mtime_ns': before.st_mtime_ns,
                'threads': 1, 'memory_limit': '4GB', 'purpose': 'targeted candidate screening; profiled times only'}
    (args.out/'environment.json').write_text(json.dumps(metadata, indent=2)+'\n')
    for query in args.queries:
        out = args.out/query.stem
        out.mkdir()
        sql = '\n'.join(l for l in query.read_text().splitlines() if not l.lstrip().startswith('--')).strip()
        if not sql.endswith(';'):
            sql += ';'
        (out/'query.sql').write_text(sql+'\n')
        row = {}
        for mode in ['OuterYan', 'DuckDB']:
            setup = "SET threads=1; SET memory_limit='4GB';\n"
            setup += 'SET disabled_optimizers='+literal('' if mode=='OuterYan' else 'outer_yan')+';\n'
            setup += 'RESET VARIABLE pgplan; RESET VARIABLE outer_yan_pg_replay_plan;\n'
            argv = [str(args.duckdb), str(args.db), '-readonly', '-init', os.devnull, '-batch', '-bail']
            trace_env = dict(env)
            trace_env['DUCKDB_OYTRACE'] = str(out/(mode+'.trace'))
            explain_sql = setup+'EXPLAIN (FORMAT JSON) '+sql+'\n'
            explained = subprocess.run(argv, input=explain_sql, text=True, capture_output=True,
                                       env=trace_env, timeout=args.timeout, check=True)
            (out/(mode+'.explain.txt')).write_text(explained.stdout)
            (out/(mode+'.explain.log')).write_text(explained.stderr)
            start = explained.stdout.find('[\n')
            tree = duck_tree(json.loads(explained.stdout[start:])[0])
            info = {'grouping': grouping(tree), 'semantic': semantic(tree)}
            if mode=='OuterYan':
                info['decision'] = decision((out/(mode+'.trace')).read_text())
                print(query.stem, info['decision'].get('selected_plan'), info['grouping'], flush=True)
            print('profile', query.stem, mode, flush=True)
            profile = out/(mode+'.profile.json')
            profiled_sql = setup+".mode trash\nPRAGMA enable_profiling='json';\nPRAGMA profiling_output="+literal(profile)+';\n'+sql+'\n'
            (out/(mode+'.profile.sql')).write_text(profiled_sql)
            with (out/(mode+'.profile.stdout')).open('w') as stdout, (out/(mode+'.profile.log')).open('w') as stderr:
                subprocess.run(argv, input=profiled_sql, text=True, stdout=stdout, stderr=stderr,
                               env=env, timeout=args.timeout, check=True)
            result = json.loads(profile.read_text())
            actual_tree = duck_tree(result['children'][0], True)
            assert semantic(actual_tree)==semantic(tree), 'profile grouping changed'
            joins = [n for n in nodes(actual_tree) if n['op']=='join']
            info.update(profile_seconds=result['latency'], result_rows=result['rows_returned'],
                        join_input=sum(n['input_rows'] for n in joins),
                        max_nonroot=max((n['output_rows'] for n in joins[1:]), default=0))
            row[mode] = info
        assert row['DuckDB']['result_rows']==row['OuterYan']['result_rows'], 'result cardinality mismatch'
        row['profile_speedup'] = row['DuckDB']['profile_seconds']/row['OuterYan']['profile_seconds']
        records[query.stem] = row
        (args.out/'screen.json').write_text(json.dumps(records, indent=2)+'\n')
        print(query.stem, json.dumps(row), flush=True)
    after = args.db.stat()
    assert (before.st_size,before.st_mtime_ns)==(after.st_size,after.st_mtime_ns), 'database changed'


if __name__=='__main__':
    main()
