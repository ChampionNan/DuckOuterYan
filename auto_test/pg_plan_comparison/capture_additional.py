#!/usr/bin/env python3
"""Capture PG evidence for C/D using this study's stopped private PG cluster."""
import argparse
import fcntl
import json
import os
from pathlib import Path
import signal
import subprocess
import tempfile

from datasets import export_tables, assert_unchanged, ident
from fair_baseline import query_sha256, verify_shared_baseline
from plans import duck_tree, pg_tree, semantic, trace_evidence, sha256
from run import DuckDB, literal, write_json


SPECS = {
    'case_c': {'source_benchmark': 'JOB 21a', 'tables': ['company_name','company_type','movie_info','movie_companies','movie_keyword'],
               'aliases': {'cn':'company_name','ct':'company_type','mi':'movie_info','mc':'movie_companies','mk':'movie_keyword'}},
    'case_d': {'source_benchmark': 'JOB 11a', 'tables': ['company_name','company_type','movie_companies','movie_keyword','keyword'],
               'aliases': {'cn':'company_name','ct':'company_type','mc':'movie_companies','mk':'movie_keyword','k':'keyword'}}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--duckdb', type=Path, required=True)
    parser.add_argument('--job-db', type=Path, required=True)
    parser.add_argument('--pg-bin-dir', type=Path, required=True)
    parser.add_argument('--pgdata', type=Path, required=True)
    parser.add_argument('--screen', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--timeout', type=int, default=600)
    parser.add_argument('--load-timeout', type=int, default=1800)
    args = parser.parse_args()
    signal.signal(signal.SIGTERM, lambda *_: (_ for _ in ()).throw(KeyboardInterrupt()))
    args.out.mkdir(parents=True, exist_ok=False)
    assert (args.pgdata/'PG_VERSION').read_text().strip()=='16'
    lock = (args.pgdata.parent/'pg-study-reuse.lock').open('a')
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    if (args.pgdata/'postmaster.pid').exists():
        raise RuntimeError('private study cluster is already running; refusing to touch it')
    with tempfile.TemporaryDirectory(prefix='oypg-add-') as socket:
        started = False
        try:
            env = dict(os.environ, PG_OJ_TRACE='1')
            subprocess.run([str(args.pg_bin_dir/'pg_ctl'),'-D',str(args.pgdata),'-l',str(args.out/'postgres.log'),
                            '-o',f"-h '' -k {socket} -p 55440 -c autovacuum=off",'-w','start'],env=env,check=True)
            started = True
            def pg(sql, stem, timeout=None):
                (args.out/(stem+'.sql')).write_text(sql)
                x=subprocess.run([str(args.pg_bin_dir/'psql'),'-X','-w','-h',socket,'-p','55440','-U','oy_study','-d','postgres',
                                  '-qAt','-v','ON_ERROR_STOP=1'],input=sql,text=True,capture_output=True,
                                 timeout=timeout or args.timeout,check=True)
                (args.out/(stem+'.stdout')).write_text(x.stdout)
                (args.out/(stem+'.log')).write_text(x.stderr)
                return x
            setup="SET search_path=pgplan_job,pg_catalog; SET max_parallel_workers_per_gather=0; SET statement_timeout=600000;\n"
            settings=json.loads(pg(setup+"SELECT json_build_object('version_num',current_setting('server_version_num'),'geqo_threshold',current_setting('geqo_threshold'),'join_collapse_limit',current_setting('join_collapse_limit'),'from_collapse_limit',current_setting('from_collapse_limit'),'max_parallel_workers_per_gather',current_setting('max_parallel_workers_per_gather'));",'settings').stdout)
            assert settings['version_num']=='160002'
            write_json(args.out/'pg_settings.json',settings)
            required=['company_name','company_type','movie_companies','keyword']
            existing=set(pg(setup+"SELECT tablename FROM pg_tables WHERE schemaname='pgplan_job';",'existing_tables').stdout.splitlines())
            missing=[name for name in required if name not in existing]
            if missing:
                export_dir=args.out/'data';export_dir.mkdir()
                spec={'family':'job','tables':missing,'source_benchmark':'JOB 21a and JOB 11a',
                      'derivation':'additional original tables for C/D; full original rows, columns and constraints'}
                data=export_tables(args,DuckDB(args),spec,export_dir,args.job_db)
                write_json(export_dir/'data.json',data)
                for table in data['tables']:
                    name=table['relation']
                    sql=setup+table['pg_ddl']+'\n'
                    sql+=f"\\copy {ident(name)} FROM '{export_dir/(name+'.csv')}' WITH (FORMAT csv, HEADER true, NULL '\\N')\n"
                    sql+='ANALYZE '+ident(name)+';\n'
                    print('load',name,table['rows'],flush=True)
                    pg(sql,'load_'+name,args.load_timeout)
                    count=int(pg(setup+'SELECT count(*) FROM '+ident(name)+';','count_'+name,args.load_timeout).stdout)
                    assert count==table['rows']
                assert_unchanged(data)
            summary={}
            for case,spec in SPECS.items():
                source=args.screen/case;out=args.out/case;out.mkdir()
                sql=(source/'query.sql').read_text();(out/'query.sql').write_text(sql)
                result=pg(setup+'EXPLAIN (VERBOSE, FORMAT JSON, COSTS true) '+sql,case+'_explain')
                explain=json.loads(result.stdout);tree=pg_tree(explain[0]['Plan'],'pgplan_job',spec['aliases'])
                write_json(out/'pg_explain.json',explain);write_json(out/'pg_tree.json',tree)
                (out/'pg_trace.log').write_text(result.stderr)
                native_text=(source/'DuckDB.explain.txt').read_text()
                native=json.loads(native_text[native_text.index('[\n'):])[0]
                native_tree=duck_tree(native)
                profile=json.loads((source/'DuckDB.profile.json').read_text())
                profile_tree=duck_tree(profile['children'][0],True)
                try:
                    shared=verify_shared_baseline(tree,native_tree,spec['tables'],sql=sql,
                        pg_query_sha256=query_sha256(sql),native_query_sha256=query_sha256(sql),
                        profile_tree=profile_tree,profile_sql=profile['query_name'])
                except ValueError as ex:
                    shared={'status':'different_typed_trees','reason':str(ex),'pg':semantic(tree),'native':semantic(native_tree)}
                write_json(out/'shared_baseline.json',shared)
                outer_profile=json.loads((source/'OuterYan.profile.json').read_text())
                outer_tree=duck_tree(outer_profile['children'][0],True)
                relids={str(i+1):name for i,name in enumerate(spec['tables'])}
                evidence=trace_evidence(result.stderr,outer_tree,'A',relids)
                if evidence['status']=='unproven':evidence=trace_evidence(result.stderr,outer_tree,'B',relids)
                write_json(out/'search_space_evidence.json',evidence)
                artifact={'format':'duckyan.pg_join_tree.v1','query_sha256':query_sha256(sql),
                          'query_sha256_canonicalization':'duckyan.sql_text.v1',
                          'postgres':{'version_num':160002,'settings':{'max_parallel_workers_per_gather':'0','search_path':'pgplan_job, pg_catalog'},
                                      'plan_schema':'pgplan_job','plan_data':'job-duckdb-full'},
                          'data_provenance':{'kind':'existing_benchmark_full_tables','family':'job',
                                             'source_db':str(args.job_db),'source_benchmark':spec['source_benchmark'],
                                             'table_row_policy':'all rows and columns; no sampling, filter, LIMIT or data generation',
                                             'query_sha256':query_sha256(sql)},'tree':tree}
                write_json(out/'pg_replay.json',artifact)
                summary[case]={'shared':shared,'evidence':evidence}
                print(case,json.dumps(summary[case]),flush=True)
            write_json(args.out/'capture_summary.json',summary)
        finally:
            if started:
                signal.signal(signal.SIGINT, signal.SIG_IGN)
                signal.signal(signal.SIGTERM, signal.SIG_IGN)
                subprocess.run([str(args.pg_bin_dir/'pg_ctl'),'-D',str(args.pgdata),'-m','fast','-w','stop'],check=True)


if __name__=='__main__':
    main()
