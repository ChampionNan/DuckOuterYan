-- ----------------------------------------------------------------------------
-- build_job_db.sql
--
-- Populate the JOB (Join Order Benchmark) IMDb database for DuckYanOuter.
--
-- Schema + parquet origin: official DuckDB benchmark/imdb assets, hosted as
-- the duckdb/duckdb-data v1.0 GitHub release. See:
--   https://github.com/duckdb/duckdb/blob/main/benchmark/imdb/init/load.sql
--
-- This SQL reads parquet files from a LOCAL directory, identified by the
-- duckdb variable 'job_dir'. The companion build_job_db.sh wrapper takes
-- care of downloading the 21 parquet files into that directory before
-- invoking this script.
--
-- Manual usage (when parquets are already on disk):
--   duckdb $JOB_DB \
--     -cmd "SET VARIABLE job_dir='/abs/path/to/job_parquet';" \
--     -f auto_test/build_job_db.sql
-- ----------------------------------------------------------------------------

CREATE OR REPLACE TABLE aka_name        AS SELECT * FROM read_parquet(getvariable('job_dir') || '/job_aka_name.parquet');
CREATE OR REPLACE TABLE aka_title       AS SELECT * FROM read_parquet(getvariable('job_dir') || '/job_aka_title.parquet');
CREATE OR REPLACE TABLE cast_info       AS SELECT * FROM read_parquet(getvariable('job_dir') || '/job_cast_info.parquet');
CREATE OR REPLACE TABLE char_name       AS SELECT * FROM read_parquet(getvariable('job_dir') || '/job_char_name.parquet');
CREATE OR REPLACE TABLE comp_cast_type  AS SELECT * FROM read_parquet(getvariable('job_dir') || '/job_comp_cast_type.parquet');
CREATE OR REPLACE TABLE company_name    AS SELECT * FROM read_parquet(getvariable('job_dir') || '/job_company_name.parquet');
CREATE OR REPLACE TABLE company_type    AS SELECT * FROM read_parquet(getvariable('job_dir') || '/job_company_type.parquet');
CREATE OR REPLACE TABLE complete_cast   AS SELECT * FROM read_parquet(getvariable('job_dir') || '/job_complete_cast.parquet');
CREATE OR REPLACE TABLE info_type       AS SELECT * FROM read_parquet(getvariable('job_dir') || '/job_info_type.parquet');
CREATE OR REPLACE TABLE keyword         AS SELECT * FROM read_parquet(getvariable('job_dir') || '/job_keyword.parquet');
CREATE OR REPLACE TABLE kind_type       AS SELECT * FROM read_parquet(getvariable('job_dir') || '/job_kind_type.parquet');
CREATE OR REPLACE TABLE link_type       AS SELECT * FROM read_parquet(getvariable('job_dir') || '/job_link_type.parquet');
CREATE OR REPLACE TABLE movie_companies AS SELECT * FROM read_parquet(getvariable('job_dir') || '/job_movie_companies.parquet');
CREATE OR REPLACE TABLE movie_info      AS SELECT * FROM read_parquet(getvariable('job_dir') || '/job_movie_info.parquet');
CREATE OR REPLACE TABLE movie_info_idx  AS SELECT * FROM read_parquet(getvariable('job_dir') || '/job_movie_info_idx.parquet');
CREATE OR REPLACE TABLE movie_keyword   AS SELECT * FROM read_parquet(getvariable('job_dir') || '/job_movie_keyword.parquet');
CREATE OR REPLACE TABLE movie_link      AS SELECT * FROM read_parquet(getvariable('job_dir') || '/job_movie_link.parquet');
CREATE OR REPLACE TABLE name            AS SELECT * FROM read_parquet(getvariable('job_dir') || '/job_name.parquet');
CREATE OR REPLACE TABLE person_info     AS SELECT * FROM read_parquet(getvariable('job_dir') || '/job_person_info.parquet');
CREATE OR REPLACE TABLE role_type       AS SELECT * FROM read_parquet(getvariable('job_dir') || '/job_role_type.parquet');
CREATE OR REPLACE TABLE title           AS SELECT * FROM read_parquet(getvariable('job_dir') || '/job_title.parquet');

-- Verify load: print row counts (should match canonical JOB sizes).
SELECT 'aka_name'        AS tbl, COUNT(*) AS n FROM aka_name
UNION ALL SELECT 'aka_title',        COUNT(*) FROM aka_title
UNION ALL SELECT 'cast_info',        COUNT(*) FROM cast_info
UNION ALL SELECT 'char_name',        COUNT(*) FROM char_name
UNION ALL SELECT 'comp_cast_type',   COUNT(*) FROM comp_cast_type
UNION ALL SELECT 'company_name',     COUNT(*) FROM company_name
UNION ALL SELECT 'company_type',     COUNT(*) FROM company_type
UNION ALL SELECT 'complete_cast',    COUNT(*) FROM complete_cast
UNION ALL SELECT 'info_type',        COUNT(*) FROM info_type
UNION ALL SELECT 'keyword',          COUNT(*) FROM keyword
UNION ALL SELECT 'kind_type',        COUNT(*) FROM kind_type
UNION ALL SELECT 'link_type',        COUNT(*) FROM link_type
UNION ALL SELECT 'movie_companies',  COUNT(*) FROM movie_companies
UNION ALL SELECT 'movie_info',       COUNT(*) FROM movie_info
UNION ALL SELECT 'movie_info_idx',   COUNT(*) FROM movie_info_idx
UNION ALL SELECT 'movie_keyword',    COUNT(*) FROM movie_keyword
UNION ALL SELECT 'movie_link',       COUNT(*) FROM movie_link
UNION ALL SELECT 'name',             COUNT(*) FROM name
UNION ALL SELECT 'person_info',      COUNT(*) FROM person_info
UNION ALL SELECT 'role_type',        COUNT(*) FROM role_type
UNION ALL SELECT 'title',            COUNT(*) FROM title
ORDER BY 1;
