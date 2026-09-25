-- corpus_version: v2
-- workload_role: retained evaluation control with deterministic mixed joins
-- join_vector: LRF; relation and predicate structure unchanged
-- corpus_revision: v1-mixed-graph25-20260925
-- workload_role: retained evaluation control with deterministic mixed joins
-- join_vector: FIL; relation and predicate structure unchanged
SELECT n_name, s_name, ps_availqty, p_name
FROM nation
    LEFT OUTER JOIN supplier ON n_nationkey = s_nationkey
    RIGHT OUTER JOIN partsupp  ON s_suppkey = ps_suppkey
    FULL OUTER JOIN part      ON ps_partkey = p_partkey
WHERE s_acctbal > 500;
