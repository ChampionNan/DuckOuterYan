-- aggregate_rewrite: aggregate-count-20261008; replaces: aggregate__tpch__tpch_q07_trade_flow__left_deep__lrfi__e001d276__sel_low__grouped_min; pending cpu9 measurement
-- corpus_revision: balanced-screened-20261002; pending cpu9 measurement
-- source: TPC-H Q7
-- selectivity: low; base-entity cohort, not joined output
-- policy: historically screened; not an unbiased overall-performance sample
SELECT s.s_suppkey AS group_key, COUNT(*) AS row_count
FROM ((((supplier s LEFT OUTER JOIN lineitem l ON s.s_suppkey = l.l_suppkey) RIGHT OUTER JOIN orders o ON l.l_orderkey = o.o_orderkey) FULL OUTER JOIN customer c ON o.o_custkey = c.c_custkey) INNER JOIN nation n ON s.s_nationkey = n.n_nationkey)
WHERE l.l_shipdate BETWEEN DATE '1995-01-01' AND DATE '1995-03-15'
GROUP BY s.s_suppkey;
