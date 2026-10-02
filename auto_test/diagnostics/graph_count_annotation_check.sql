-- Read-only diagnosis for graph_branch5_forward / bushy / rlfi / global_count.
-- Run with: build/release/duckdb -no-init -readonly -bail graph_db < this_file
-- This degree-weighted calculation does not materialize the large join result.
-- It is diagnostic algebra, NOT a replacement for the bare-query equivalence test.
--
-- R3 LEFT JOIN R5 can produce a NULL count annotation for an unmatched R5.
-- At the subsequent INNER JOIN, the other subtree has multiplicity b.multiplicity.
-- COUNT(*) requires b.multiplicity * COALESCE(d5.n, 1), not
-- COALESCE(b.multiplicity * d5.n, 1). The latter loses b.multiplicity - 1.
-- The old bug is fixed by normalizing each factor before multiplication.
-- Bitcoin Alpha expected rows (tier, correct_count, previous_buggy_count, lost):
-- high, 88309370031, 88091106867, 218263164
-- low,   3085879285,  3067788222,  18091063
SET disabled_optimizers TO 'outer_yan';
SET max_execution_time = 10000;

WITH tiers(tier, lim) AS (
    VALUES ('low', 2), ('high', 306)
), a AS (
    SELECT tier, dst, count(*)::HUGEINT AS n
    FROM R1 CROSS JOIN tiers
    WHERE src <= lim
    GROUP BY tier, dst
), d4 AS (
    SELECT src, count(*)::HUGEINT AS n FROM R4 GROUP BY src
), d5 AS (
    SELECT src, count(*)::HUGEINT AS n FROM R5 GROUP BY src
), b AS (
    SELECT a.tier, R2.dst, sum(a.n) * d4.n AS multiplicity
    FROM R2
    INNER JOIN a ON R2.src = a.dst
    INNER JOIN d4 ON R2.dst = d4.src
    GROUP BY a.tier, R2.dst, d4.n
)
SELECT b.tier,
       sum(b.multiplicity * coalesce(d5.n, 1)) AS correct_count,
       sum(coalesce(b.multiplicity * d5.n, 1)) AS previous_buggy_count,
       sum(CASE WHEN d5.n IS NULL THEN b.multiplicity - 1 ELSE 0 END) AS lost_count
FROM R3
INNER JOIN b ON R3.src = b.dst
LEFT JOIN d5 ON R3.dst = d5.src
GROUP BY b.tier
ORDER BY b.tier;
