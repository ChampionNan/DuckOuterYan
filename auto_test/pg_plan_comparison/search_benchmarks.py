#!/usr/bin/env python3
"""Inspect unchanged benchmark joins before selecting bounded timing candidates."""
import argparse
from collections import Counter
import json
import os
from pathlib import Path
import re
import subprocess

from datasets import fingerprint
from plans import decision, duck_tree, grouping, semantic, sha256
from run import duck_env, write_json


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('queries', 'duckdb', 'db-root', 'out'):
        parser.add_argument('--' + name, type=Path, required=True)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=False)
    families = ('job', 'tpch', 'tpcds')
    before = {f: fingerprint(args.db_root / (f + '_db')) for f in families}
    write_json(args.out / 'environment.json', {
        'databases': before, 'duckdb_sha256': sha256(args.duckdb),
        'purpose': 'EXPLAIN only; no runtime conclusions', 'threads': 1, 'memory_limit': '4GB'})
    records = {}
    for family in families:
        for query in sorted((args.queries / family).glob('*.sql')):
            if query.name.startswith('aggregate__'):
                continue
            sql = query.read_text()
            key = query.stem
            dest = args.out / key
            dest.mkdir()
            (dest / 'query.sql').write_text(sql)
            record = {'family': family, 'source': str(query), 'sha256': sha256(query)}
            records[key] = record
            # The current generated corpus uses simple unquoted table aliases.
            pairs = re.findall(r'\b(?:FROM|JOIN)\b\s*\(*\s*([a-z_][a-z_0-9]*)(?:\s+(?:AS\s+)?([a-z_][a-z_0-9]*))?', sql, re.I)
            keywords = {'on', 'inner', 'left', 'right', 'full', 'where', 'join'}
            record['aliases'] = {(alias.lower() if alias and alias.lower() not in keywords else table.lower()): table.lower()
                                 for table, alias in pairs}
            for mode in ('OY', 'native'):
                trace = dest / (mode + '.trace')
                setup = "SET threads=1; SET memory_limit='4GB'; SET disabled_optimizers='" + ('outer_yan' if mode == 'native' else '') + "';\n"
                setup += 'RESET VARIABLE pgplan; RESET VARIABLE outer_yan_pg_replay_plan;\n'
                command = [str(args.duckdb), str(args.db_root / (family + '_db')),
                           '-readonly', '-init', os.devnull, '-batch', '-bail']
                try:
                    result = subprocess.run(command, input=setup + 'EXPLAIN (FORMAT JSON) ' + sql,
                                            text=True, capture_output=True, timeout=60,
                                            env=duck_env(trace if mode == 'OY' else None))
                    (dest / (mode + '.explain.txt')).write_text(result.stdout)
                    (dest / (mode + '.log')).write_text(result.stderr)
                    result.check_returncode()
                    start = result.stdout.index('[\n')
                    physical = json.loads(result.stdout[start:])[0]
                    tree = duck_tree(physical)
                    record[mode] = {'grouping': grouping(tree), 'semantic': semantic(tree), 'tree': tree}
                    if mode == 'OY':
                        record['decision'] = decision(trace.read_text())
                        if record['decision'].get('selected_plan') != 'OUTERYAN':
                            break
                except Exception as error:
                    record['error'] = f'{mode}: {type(error).__name__}: {error}'
                    break
            if 'native' in record:
                record['different_grouping'] = record['native']['grouping'] != record['OY']['grouping']
            write_json(args.out / 'summary.json', records)
            chosen = record.get('decision', {}).get('selected_plan', 'ERROR')
            print(len(records), family, key, chosen, record.get('error', ''), flush=True)
    after = {f: fingerprint(args.db_root / (f + '_db')) for f in families}
    if before != after:
        raise RuntimeError('source databases changed')
    write_json(args.out / 'status.json', {'status': 'complete', 'source_databases_unchanged': True,
               'counts': dict(Counter(r.get('decision', {}).get('selected_plan', 'ERROR') for r in records.values()))})


if __name__ == '__main__':
    main()
