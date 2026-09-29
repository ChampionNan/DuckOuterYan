-- corpus_version: v2
-- workload_role: retained evaluation control with deterministic mixed joins
-- join_vector: ILRF; relation and predicate structure unchanged
-- corpus_revision: v1-mixed-graph25-20260925
-- workload_role: retained evaluation control with deterministic mixed joins
-- join_vector: ILRF; relation and predicate structure unchanged
SELECT c_custkey, c_name, n_name, o_orderdate, l_quantity, l_extendedprice
FROM customer
    INNER JOIN orders   ON c_custkey = o_custkey
    LEFT OUTER JOIN lineitem ON o_orderkey = l_orderkey
    RIGHT OUTER JOIN nation   ON c_nationkey = n_nationkey
    FULL OUTER JOIN region   ON n_regionkey = r_regionkey
WHERE c_acctbal > 1000;
