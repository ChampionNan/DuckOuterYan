-- corpus_revision: v1-mixed-graph25-20260925
-- workload_role: retained evaluation control with deterministic mixed joins
-- join_vector: LRF; relation and predicate structure unchanged
SELECT *
FROM customer
    LEFT OUTER JOIN orders   ON c_custkey = o_custkey
    RIGHT OUTER JOIN lineitem ON o_orderkey = l_orderkey
    FULL OUTER JOIN nation   ON c_nationkey = n_nationkey
WHERE c_acctbal > 0;
