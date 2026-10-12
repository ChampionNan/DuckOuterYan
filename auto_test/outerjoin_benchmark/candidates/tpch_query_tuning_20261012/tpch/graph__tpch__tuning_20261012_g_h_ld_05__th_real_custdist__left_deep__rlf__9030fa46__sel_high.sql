-- query_tuning: tpch-query-tuning-20261012; replaces graph__tpch__th_real_custdist__left_deep__lrf__65a983cc__sel_high
-- source: Industry-inspired synthetic control graph__tpch__th_real_custdist__lrf__sel_medium
-- performance-conditioned candidate; fresh CPU9 measurement required
SELECT *
FROM customer
    RIGHT OUTER JOIN orders   ON c_custkey = o_custkey
    LEFT OUTER JOIN lineitem ON o_orderkey = l_orderkey
    FULL OUTER JOIN nation   ON c_nationkey = n_nationkey
WHERE orders.o_orderdate BETWEEN DATE '1994-04-02' AND DATE '1997-01-03';
