#!/usr/bin/env python3
"""Time previously validated forced candidates, without profiling or row export."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import statistics
import subprocess


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', type=Path, required=True)
    parser.add_argument('--runner', type=Path, required=True)
    parser.add_argument('--validated', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--queries', nargs='+', required=True)
    parser.add_argument('--repeats', type=int, default=5)
    args = parser.parse_args()
    if args.repeats < 3:
        parser.error('at least three measured repetitions are required')
    args.repo = args.repo.resolve()
    args.runner = args.runner.resolve()
    args.validated = args.validated.resolve()
    args.out = args.out.resolve()
    args.out.mkdir(parents=True, exist_ok=False)
    validation = json.loads((args.validated / 'summary.json').read_text())
    environment = json.loads((args.validated / 'environment.json').read_text())
    if str(args.runner) not in [state['path'] for state in environment['engine']]:
        raise ValueError('runner differs from the validated client')
    def verify_environment():
        for state in environment['engine']:
            if hashlib.sha256(Path(state['path']).read_bytes()).hexdigest() != state['sha256']:
                raise ValueError('engine changed after correctness validation')
        for name in args.queries:
            family = name.split('_')[0]
            path = args.repo / (family + '_db')
            current = path.stat()
            state = environment['database'][family]
            if {'path': str(path), 'size': current.st_size, 'mtime_ns': current.st_mtime_ns} != state:
                raise ValueError('database differs from correctness validation')
    verify_environment()
    (args.out / 'environment.json').write_text(json.dumps(environment, indent=2) + '\n')
    clean_env = {key: value for key, value in os.environ.items()
                 if not key.startswith(('DUCKDB_OY', 'DUCKDB_SJ'))}
    summary = {'configuration': {'threads': 1, 'memory_limit': '4GB',
               'repetitions': args.repeats, 'warmups_per_mode': 1,
               'profiled': False, 'exported': False,
               'candidate_forced': True, 'default_optimizer_speedup': False,
               'validated': str(args.validated)}, 'queries': {}}
    for name in args.queries:
        check = validation[name]
        if check.get('status') != 'exact_match' or not check.get('exact_result_bags_equal'):
            raise ValueError('missing successful exact correctness check: ' + name)
        if not check['modes']['OFF']['run']['rows']:
            raise ValueError('empty-output predicate variants are excluded from candidate timing: ' + name)
        query = args.validated / name / 'query.sql'
        if hashlib.sha256(query.read_bytes()).hexdigest() != check['query_sha256']:
            raise ValueError('query changed after validation: ' + name)
        directory = args.out / name
        directory.mkdir()
        family = name.split('_')[0]
        row = {'query': str(query), 'query_sha256': check['query_sha256'],
               'normal_decision': check['normal_decision'], 'runs': []}
        summary['queries'][name] = row
        for repetition in range(args.repeats + 1):
            for mode in (('OFF', 'CANDIDATE') if repetition % 2 == 0 else ('CANDIDATE', 'OFF')):
                env = dict(clean_env)
                if mode == 'CANDIDATE':
                    env['DUCKDB_OY_FORCE_CANDIDATE'] = '1'
                completed = subprocess.run([str(args.runner), str(args.repo / (family + '_db')),
                                           str(query), 'OFF' if mode == 'OFF' else 'ON', '-', '-'],
                                          text=True, capture_output=True, env=env, timeout=650)
                (directory / f'{repetition}_{mode}.log').write_text(completed.stdout + completed.stderr)
                completed.check_returncode()
                lines = [line[len('[BARE_RUN] '):] for line in completed.stdout.splitlines()
                         if line.startswith('[BARE_RUN] ')]
                if len(lines) != 1:
                    raise ValueError('missing execution completion marker')
                measured = json.loads(lines[0])
                expected = check['modes'][mode]['run']
                if measured['rows'] != expected['rows'] or measured['types'] != expected['types']:
                    raise ValueError('result schema/cardinality changed since correctness check')
                measured.update(mode=mode, repetition=repetition, warmup=repetition == 0)
                row['runs'].append(measured)
                (args.out / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
        row['median_ms'] = {mode: statistics.median(run['elapsed_ms'] for run in row['runs']
                             if run['mode'] == mode and not run['warmup']) for mode in ('OFF', 'CANDIDATE')}
        row['forced_candidate_speedup'] = row['median_ms']['OFF'] / row['median_ms']['CANDIDATE']
        (args.out / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
        print(name, row['median_ms'], 'forced_speedup', row['forced_candidate_speedup'], flush=True)
    verify_environment()


if __name__ == '__main__':
    main()
