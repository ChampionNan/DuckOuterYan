-- source: TPC-H Q5
-- transformation: connected join-subgraph adaptation; balanced INNER/LEFT/RIGHT/FULL connected bushy source-derived form
-- business_semantics: TPC-H Q5 order reporting period
-- corpus_version: v2
-- selectivity_sweep: sel_high; intended band 40–80% of the calibration population
-- semantic_filter: tpch_q05_period; tier=high; TPC-H Q5 order reporting period
-- predicate: o.o_orderdate >= DATE '1992-01-01' AND o.o_orderdate < DATE '1996-01-01'
-- selectivity_scope: base-entity calibration; not a joined-output percentage
SELECT r.r_name, n.n_name, c.c_custkey, o.o_orderkey, l.l_linenumber, l.l_extendedprice
FROM ((region r RIGHT OUTER JOIN nation n ON r.r_regionkey = n.n_regionkey) FULL OUTER JOIN (customer c INNER JOIN (orders o LEFT OUTER JOIN lineitem l ON o.o_orderkey = l.l_orderkey) ON c.c_custkey = o.o_custkey) ON n.n_nationkey = c.c_nationkey)
WHERE o.o_orderdate >= DATE '1992-01-01' AND o.o_orderdate < DATE '1996-01-01';
