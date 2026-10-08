-- aggregate_rewrite: aggregate-count-20261008; replaces: aggregate__tpch__tpch_q08_market_share__right_deep__rrlif__92643cc5__sel_medium__grouped_min; pending cpu9 measurement
-- corpus_revision: balanced-screened-20261002; pending cpu9 measurement
-- source: TPC-H Q8
-- selectivity: medium; base-entity cohort, not joined output
-- policy: historically screened; not an unbiased overall-performance sample
SELECT p.p_partkey AS group_key, COUNT(*) AS row_count
FROM (part p RIGHT OUTER JOIN (region r RIGHT OUTER JOIN (nation n LEFT OUTER JOIN (customer c INNER JOIN (orders o FULL OUTER JOIN lineitem l ON l.l_orderkey = o.o_orderkey) ON o.o_custkey = c.c_custkey) ON c.c_nationkey = n.n_nationkey) ON n.n_regionkey = r.r_regionkey) ON p.p_partkey = l.l_partkey)
WHERE o.o_orderdate BETWEEN DATE '1995-01-01' AND DATE '1996-12-31'
GROUP BY p.p_partkey;
