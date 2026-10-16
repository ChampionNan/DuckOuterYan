-- aggregate_rewrite: aggregate-count-20261008; replaces: aggregate__tpch__tpch_q07_trade_flow__right_deep__irfl__06dcfc3b__sel_medium__grouped_sum; pending cpu9 measurement
-- corpus_revision: balanced-screened-20261002; pending cpu9 measurement
-- source: TPC-H Q7
-- selectivity: medium; base-entity cohort, not joined output
-- policy: historically screened; not an unbiased overall-performance sample
SELECT s.s_suppkey AS group_key, COUNT(*) AS row_count
FROM (nation n INNER JOIN (supplier s RIGHT OUTER JOIN (customer c FULL OUTER JOIN (orders o LEFT OUTER JOIN lineitem l ON l.l_orderkey = o.o_orderkey) ON o.o_custkey = c.c_custkey) ON s.s_suppkey = l.l_suppkey) ON s.s_nationkey = n.n_nationkey)
WHERE l.l_shipdate BETWEEN DATE '1995-01-01' AND DATE '1996-12-31'
GROUP BY s.s_suppkey;
