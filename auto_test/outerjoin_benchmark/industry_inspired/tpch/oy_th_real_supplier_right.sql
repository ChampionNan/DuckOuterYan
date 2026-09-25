-- corpus_revision: v1-mixed-graph25-20260925
-- workload_role: retained evaluation control with deterministic mixed joins
-- join_vector: FIL; relation and predicate structure unchanged
SELECT n_name, s_name, ps_availqty, p_name
FROM nation
    FULL OUTER JOIN supplier ON n_nationkey = s_nationkey
    INNER JOIN partsupp  ON s_suppkey = ps_suppkey
    LEFT OUTER JOIN part      ON ps_partkey = p_partkey
WHERE s_acctbal > 500;
