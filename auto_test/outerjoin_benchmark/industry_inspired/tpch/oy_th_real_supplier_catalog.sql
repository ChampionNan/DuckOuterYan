-- corpus_revision: v1-mixed-20260922
-- workload_role: retained evaluation control with deterministic mixed joins
-- join_vector: RFIL; relation and predicate structure unchanged
SELECT s_name, n_name, r_name, p_name, ps_availqty
FROM supplier
    RIGHT OUTER JOIN partsupp ON s_suppkey = ps_suppkey
    FULL OUTER JOIN part     ON ps_partkey = p_partkey
    INNER JOIN nation   ON s_nationkey = n_nationkey
    LEFT OUTER JOIN region   ON n_regionkey = r_regionkey
WHERE s_acctbal > 1000;
