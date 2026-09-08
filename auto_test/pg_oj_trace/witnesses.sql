\set ON_ERROR_STOP on

-- Run this in one psql session against a PostgreSQL server started with the
-- research-only PG_OJ_TRACE=1 instrumentation described in README.md.
SET geqo = off;
SET join_collapse_limit = 16;
SET from_collapse_limit = 16;
SET max_parallel_workers_per_gather = 0;

CREATE TEMP TABLE a(k integer);
CREATE TEMP TABLE b(k integer);
CREATE TEMP TABLE c(k integer);
CREATE TEMP TABLE d(k integer);

\echo 'Q0: identity 3, both LEFT-join associations are enumerated'
EXPLAIN (VERBOSE, COSTS OFF)
SELECT a.k AS ak, b.k AS bk, c.k AS ck
FROM (a LEFT OUTER JOIN b ON a.k = b.k)
LEFT OUTER JOIN c ON b.k = c.k;

\echo 'Q1: lower FULL, upper LEFT'
EXPLAIN (VERBOSE, COSTS OFF)
SELECT a.k AS ak, b.k AS bk, c.k AS ck
FROM (a FULL OUTER JOIN b ON a.k = b.k)
LEFT OUTER JOIN c ON a.k = c.k;

\echo 'Q2: all FULL'
EXPLAIN (VERBOSE, COSTS OFF)
SELECT a.k AS ak, b.k AS bk, c.k AS ck
FROM (a FULL OUTER JOIN b ON a.k = b.k)
FULL OUTER JOIN c ON b.k = c.k;

\echo 'Q3: lower RIGHT, upper FULL'
EXPLAIN (VERBOSE, COSTS OFF)
SELECT a.k AS ak, b.k AS bk, c.k AS ck
FROM (a RIGHT OUTER JOIN b ON a.k = b.k)
FULL OUTER JOIN c ON b.k = c.k;

\echo 'Q4: four-relation all-FULL chain'
EXPLAIN (VERBOSE, COSTS OFF)
SELECT a.k AS ak, b.k AS bk, c.k AS ck, d.k AS dk
FROM ((a FULL OUTER JOIN b ON a.k = b.k)
      FULL OUTER JOIN c ON b.k = c.k)
FULL OUTER JOIN d ON c.k = d.k;

-- Data-backed all-FULL witness.  This executes only 10,100 result rows at
-- N=100, but it proves that the missing association has a much smaller first
-- intermediate on the same PostgreSQL engine.  A also contains unmatched
-- key-2 rows, so the FULL joins perform real null extension.
\echo 'Q5: data-backed all-FULL missing-plan witness'
\set full_n 100
CREATE TEMP TABLE full_a(k integer);
CREATE TEMP TABLE full_b(k integer);
CREATE TEMP TABLE full_c(k integer);
INSERT INTO full_a SELECT 1 FROM generate_series(1, :full_n);
INSERT INTO full_a SELECT 2 FROM generate_series(1, :full_n);
INSERT INTO full_b SELECT 1 FROM generate_series(1, :full_n);
INSERT INTO full_c VALUES (1);
ANALYZE full_a;
ANALYZE full_b;
ANALYZE full_c;

WITH written AS
(
    SELECT a.k AS ak, b.k AS bk, c.k AS ck
    FROM (full_a a FULL OUTER JOIN full_b b ON a.k = b.k)
    FULL OUTER JOIN full_c c ON b.k = c.k
),
reassociated AS
(
    SELECT a.k AS ak, b.k AS bk, c.k AS ck
    FROM full_a a
    FULL OUTER JOIN
        (full_b b FULL OUTER JOIN full_c c ON b.k = c.k)
    ON a.k = b.k
),
delta AS
(
    (SELECT * FROM written EXCEPT ALL SELECT * FROM reassociated)
    UNION ALL
    (SELECT * FROM reassociated EXCEPT ALL SELECT * FROM written)
)
SELECT count(*) AS multiset_delta FROM delta;

\echo 'Q5a: PostgreSQL-written grouping: (A FULL B) FULL C'
EXPLAIN (ANALYZE, VERBOSE, COSTS OFF, TIMING OFF)
SELECT a.k AS ak, b.k AS bk, c.k AS ck
FROM (full_a a FULL OUTER JOIN full_b b ON a.k = b.k)
FULL OUTER JOIN full_c c ON b.k = c.k;

\echo 'Q5b: equivalent missing grouping forced by query text: A FULL (B FULL C)'
EXPLAIN (ANALYZE, VERBOSE, COSTS OFF, TIMING OFF)
SELECT a.k AS ak, b.k AS bk, c.k AS ck
FROM full_a a
FULL OUTER JOIN
    (full_b b FULL OUTER JOIN full_c c ON b.k = c.k)
ON a.k = b.k;

-- Control: unlike the FULL-barrier witnesses, this flattened problem really
-- proposes {B,C}.  join_is_legal() rejects it, demonstrating that LEGAL_REJECT
-- is emitted when the legality routine is actually called.
\echo 'Control: actual legality rejection'
EXPLAIN (VERBOSE, COSTS OFF)
SELECT a.k AS ak, b.k AS bk, c.k AS ck
FROM (a LEFT OUTER JOIN b ON a.k = b.k)
CROSS JOIN c;
