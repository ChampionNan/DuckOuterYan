-- corpus_revision: balanced-screened-20261002; pending cpu9 measurement
-- source: Industry-inspired synthetic control graph__tpch__th_real_custdist__lrf__sel_medium
-- selectivity: high; base-entity cohort, not joined output
-- policy: historically screened; not an unbiased overall-performance sample
SELECT *
FROM customer
    LEFT OUTER JOIN orders   ON c_custkey = o_custkey
    RIGHT OUTER JOIN lineitem ON o_orderkey = l_orderkey
    FULL OUTER JOIN nation   ON c_nationkey = n_nationkey
WHERE orders.o_orderdate BETWEEN DATE '1994-08-24' AND DATE '1998-08-02';