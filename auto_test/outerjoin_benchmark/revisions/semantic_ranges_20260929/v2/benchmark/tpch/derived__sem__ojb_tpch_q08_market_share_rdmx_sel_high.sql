-- source: TPC-H Q8
-- transformation: connected join-subgraph adaptation; balanced INNER/LEFT/RIGHT/FULL right-deep source-derived form
-- business_semantics: TPC-H Q8 order reporting period
-- corpus_version: v2
-- selectivity_sweep: sel_high; intended band 40–80% of the calibration population
-- semantic_filter: tpch_q08_period; tier=high; TPC-H Q8 order reporting period
-- predicate: o.o_orderdate BETWEEN DATE '1993-01-01' AND DATE '1996-12-31'
-- selectivity_scope: base-entity calibration; not a joined-output percentage
SELECT *
FROM (region r INNER JOIN (nation n FULL OUTER JOIN (customer c RIGHT OUTER JOIN (orders o LEFT OUTER JOIN (lineitem l INNER JOIN part p ON p.p_partkey = l.l_partkey) ON l.l_orderkey = o.o_orderkey) ON o.o_custkey = c.c_custkey) ON c.c_nationkey = n.n_nationkey) ON n.n_regionkey = r.r_regionkey)
WHERE o.o_orderdate BETWEEN DATE '1993-01-01' AND DATE '1996-12-31';
