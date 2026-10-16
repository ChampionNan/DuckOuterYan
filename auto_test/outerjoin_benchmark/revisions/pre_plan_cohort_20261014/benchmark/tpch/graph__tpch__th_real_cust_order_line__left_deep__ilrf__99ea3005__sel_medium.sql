-- corpus_revision: balanced-screened-20261002; pending cpu9 measurement
-- source: Industry-inspired synthetic control graph__tpch__th_real_cust_order_line__ilrf__sel_low
-- selectivity: medium; base-entity cohort, not joined output
-- policy: historically screened; not an unbiased overall-performance sample
SELECT c_custkey, c_name, n_name, o_orderdate, l_quantity, l_extendedprice
FROM customer
    INNER JOIN orders   ON c_custkey = o_custkey
    LEFT OUTER JOIN lineitem ON o_orderkey = l_orderkey
    RIGHT OUTER JOIN nation   ON c_nationkey = n_nationkey
    FULL OUTER JOIN region   ON n_regionkey = r_regionkey
WHERE orders.o_orderdate BETWEEN DATE '1994-03-20' AND DATE '1996-03-09';